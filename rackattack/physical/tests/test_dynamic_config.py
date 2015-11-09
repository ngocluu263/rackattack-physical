import unittest
import mock
from mock import patch
from rackattack.physical import dynamicconfig
from rackattack.common import hosts
from rackattack.common import dnsmasq
from rackattack.common import tftpboot
from rackattack.common import inaugurate
from rackattack.common import timer
from rackattack.physical import config
import os
from rackattack.common import hoststatemachine
import yaml
from rackattack.physical.tests.common import HostStateMachine, Allocations, FreePool
from rackattack.physical.host import Host, STATES
from rackattack.physical import reclaimhost, network
from rackattack.physical.alloc.allocation import Allocation
from rackattack.common.tests.mockfilesystem import enableMockedFilesystem, disableMockedFilesystem
import netaddr


configurationFiles = {}


class FakeDNSMasq:
    def __init__(self):
        self.items = dict()
        self.side_effect = None

    def add(self, mac, address):
        if self.side_effect is not None:
            raise self.side_effect
        assert mac not in self.items
        self.items[mac] = address

    def remove(self, mac):
        del self.items[mac]

    def __getitem__(self, key):
        return self.items[key]

    def __len__(self):
        return len(self.items)


@patch('signal.signal')
@patch('subprocess.check_output', return_value='')
@mock.patch('rackattack.physical.ipmi.IPMI')
class Test(unittest.TestCase):
    HOST_THAT_WILL_BE_TAKEN_OFFLINE = 'rack01-server44'
    CONFIG_FILES_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fixtures')

    @classmethod
    def loadConfigurationFilesToMemory(cls):
        configurationFilenames = os.listdir(cls.CONFIG_FILES_DIR)
        for _file in configurationFilenames:
            _filepath = os.path.join(cls.CONFIG_FILES_DIR, _file)
            with open(_filepath) as confFile:
                contents = confFile.read()
            configuration = yaml.load(contents)
            configurationFiles[_filepath] = configuration

    def setUp(self):
        if not configurationFiles:
            self.loadConfigurationFilesToMemory()
        self.fakeFilesystem = enableMockedFilesystem(dynamicconfig)
        self._createFakeFilesystem()
        mockNetworkConf = {'NODES_SUBNET_PREFIX_LENGTH': 22, 'ALLOW_CLEARING_OF_DISK': False,
                           'OSMOSIS_SERVER_IP': '10.0.0.26',
                           'PUBLIC_NAT_IP': '192.168.1.2',
                           'GATEWAY_IP': '192.168.1.2',
                           'FIRST_IP': '192.168.1.11',
                           'BOOTSERVER_IP': '192.168.1.1',
                           'PUBLIC_INTERFACE': '00:1e:67:44:13:a1'}
        self.dnsMasqMock = FakeDNSMasq()
        self.expectedDNSMasq = FakeDNSMasq()
        self._loadAddresses(firstIP=mockNetworkConf["FIRST_IP"],
                            prefixLength=int(mockNetworkConf["NODES_SUBNET_PREFIX_LENGTH"]))
        self.inaguratorMock = mock.Mock(spec=inaugurate.Inaugurate)
        self.tftpMock = mock.Mock(spec=tftpboot.TFTPBoot)
        self.allocationsMock = Allocations()
        self.reclaimHost = mock.Mock(spec=reclaimhost.ReclaimHost)
        timer.cancelAllByTag = mock.Mock()
        timer.scheduleAt = mock.Mock()
        timer.scheduleIn = mock.Mock()
        self._hosts = hosts.Hosts()
        self.expectedAddresses = dict()
        self.freePoolMock = FreePool(self._hosts)
        hoststatemachine.HostStateMachine = HostStateMachine
        network.initialize_globals(mockNetworkConf)

    def tearDown(self):
        disableMockedFilesystem(dynamicconfig)

    def _loadAddresses(self, firstIP, prefixLength):
        subnet = netaddr.IPNetwork("%(firstAddr)s/%(prefixLen)s" % dict(firstAddr=firstIP,
                                                                        prefixLen=prefixLength))
        firstAddr = netaddr.IPAddress(firstIP)
        subnet = list(subnet)
        idxOfFirstAddr = subnet.index(firstAddr)
        self.addresses = [str(addr) for addr in subnet[idxOfFirstAddr:]]

    def _createFakeFilesystem(self):
        self.fakeFilesystem.CreateDirectory(self.CONFIG_FILES_DIR)
        for _filename, contents in configurationFiles.iteritems():
            contents = yaml.dump(contents)
            self.fakeFilesystem.CreateFile(_filename, contents=contents)

    def _setRackConf(self, fixtureFileName):
        config.RACK_YAML = os.path.join(self.CONFIG_FILES_DIR, fixtureFileName)

    def _normalizeState(self, state):
        return state.strip().upper()

    def _updateExpectedDnsMasqEntriesUponReload(self, oldConfiguration, newConfiguration):
        for hostNewData in newConfiguration:
            hostID = hostNewData["id"]
            hostOldDataPotentials = [host for host in oldConfiguration if host["id"] == hostID]
            self.assertEquals(len(hostOldDataPotentials), 1)
            hostOldData = hostOldDataPotentials[0]
            newState = self._normalizeState(hostNewData["state"])
            oldState = self._normalizeState(hostOldData["state"])
            if newState == STATES.ONLINE and oldState != STATES.ONLINE:
                if hostID not in self.expectedAddresses:
                    address = self.addresses.pop(0)
                    self.expectedAddresses[hostID] = address
                self.expectedDNSMasq.add(hostNewData["primaryMAC"],
                                         self.expectedAddresses[hostID])
            elif newState == STATES.OFFLINE and oldState == STATES.ONLINE:
                self.expectedDNSMasq.remove(hostNewData["primaryMAC"])
            elif newState == STATES.DETACHED and oldState == STATES.ONLINE:
                self.expectedDNSMasq.remove(hostNewData["primaryMAC"])

    def _updateExpectedDnsMasqEntriesUponLoad(self, configuration):
        for hostData in configuration:
            state = self._normalizeState(hostData["state"])
            if state == STATES.ONLINE:
                address = self.addresses.pop(0)
                self.expectedAddresses[hostData["id"]] = address
                self.expectedDNSMasq.add(hostData["primaryMAC"], address)

    def _reloadRackConf(self, fixtureFileName, failureExpected=False):
        oldConfiguration = configurationFiles[config.RACK_YAML]["HOSTS"]
        self._setRackConf(fixtureFileName)
        if not failureExpected:
            newConfiguration = configurationFiles[config.RACK_YAML]["HOSTS"]
            self._updateExpectedDnsMasqEntriesUponReload(oldConfiguration, newConfiguration)
        self.tested._reload()
        self._validateDNSMasqEntries()

    def _init(self, fixtureFileName):
        self._setRackConf(fixtureFileName)
        configuration = configurationFiles[config.RACK_YAML]["HOSTS"]
        self._updateExpectedDnsMasqEntriesUponLoad(configuration)
        self.tested = dynamicconfig.DynamicConfig(hosts=self._hosts,
                                                  dnsmasq=self.dnsMasqMock,
                                                  inaugurate=self.inaguratorMock,
                                                  tftpboot=self.tftpMock,
                                                  freePool=self.freePoolMock,
                                                  allocations=self.allocationsMock,
                                                  reclaimHost=self.reclaimHost)

    def test_BringHostsOnline(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('online_rack_conf.yaml')
        self._validate()

    def test_BringOnlineHostsOfflineWhileNotAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('offline_rack_conf.yaml')
        self._validate()

    def test_BringHostOfflineWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        self._validate()
        self._reloadRackConf('offline_rack_conf.yaml')
        self._validate()

    def test_BringHostOfflineWhileAllocatedAndAllocationIsDead(self, *_args):
        self._init('online_rack_conf.yaml')
        allocation = self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        allocation.withdraw("Made up reason")
        self._validate()
        self._reloadRackConf('offline_rack_conf.yaml')
        self._validate()

    def test_BringHostOfflineAfterDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._destroyHost(hostID)
        self._validate(onlineHostsNotInPool=[hostID])
        self._reloadRackConf('offline_rack_conf.yaml')
        self._validate()

    def test_DetachOnlineHostWhileNotAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_DetachOnlineHostWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._allocateHost("rack01-server41")
        self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_DetachOnlineHostWhileAllocatedAndAllocationIsDead(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        allocation = self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        allocation.withdraw("Made up reason")
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_DetachHostAfterDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._destroyHost(hostID)
        self._validate(onlineHostsNotInPool=[hostID])
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_DetachHostAfterAllocatedAndDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._allocateHost(hostID)
        self._destroyHost(hostID)
        self._validate(onlineHostsNotInPool=[hostID])
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_BringHostOnlineAfterDetached(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('online_rack_conf.yaml')
        self._validate()

    def test_DetachOfflineHost(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()

    def test_BringHostOfflineAfterDetached(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('detached_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('offline_rack_conf.yaml')
        self._validate()

    def test_DetachHostAtTheBeginning(self, *_args):
        self._init('detached_rack_conf.yaml')
        self._validate()

    def test_addNewHostInOnlineStateDNSMasqAddHostCalled(self, *_args):
        self._init('online_rack_conf.yaml')
        self.assertEquals(len(self.dnsMasqMock.items), 4)
        self.assertEquals(self.dnsMasqMock['00:1e:67:48:20:60'], '192.168.1.11')
        self.assertEquals(self.dnsMasqMock['00:1e:67:44:40:8e'], '192.168.1.12')
        self.assertEquals(self.dnsMasqMock['00:1e:67:45:6e:f1'], '192.168.1.13')
        self.assertEquals(self.dnsMasqMock['00:1e:67:45:70:6d'], '192.168.1.14')
        self._reloadRackConf('offline_rack_conf.yaml')
        self.assertEquals(self.dnsMasqMock['00:1e:67:48:20:60'], '192.168.1.11')
        self.assertEquals(self.dnsMasqMock['00:1e:67:44:40:8e'], '192.168.1.12')
        self.assertEquals(self.dnsMasqMock['00:1e:67:45:6e:f1'], '192.168.1.13')
        self.assertNotIn('00:1e:67:45:70:6d', self.dnsMasqMock.items)

    def test_BringHostsOnlineFailedSinceDNSMasqAddFailed(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validate()
        try:
            self.dnsMasqMock.side_effect = AssertionError('Ignore this error')
            self._reloadRackConf('online_rack_conf.yaml', failureExpected=True)
            self._reloadRackConf('offline_rack_conf.yaml', failureExpected=True)
        finally:
            self.dnsMasqMock.side_effect = None
        self._validate()

    def test_NotPoweringOffHostsWhenReoadingYaml(self, *_args):
        origTurnOff = Host.turnOff
        Host.turnOff = mock.Mock()
        try:
            self._init('offline_rack_conf.yaml')
            actualOfflineHosts = self.tested.getOfflineHosts()
            for host in actualOfflineHosts.values():
                host.turnOff.assert_not_called()
        finally:
            Host.turnOff = origTurnOff

    def _validateOnlineHostsAreInHostsPool(self, exceptForIDs=None):
        if exceptForIDs is None:
            exceptForIDs = []
        actualIDs = [host.hostImplementation().id() for host in self._hosts.all()]
        expectedIDs = [host for host in self._idsOfHostsInConfiguration(state=STATES.ONLINE)
                       if host not in exceptForIDs]
        self.assertItemsEqual(actualIDs, expectedIDs)

    def _validateOnlineHosts(self):
        expectedOnlineHosts = self._idsOfHostsInConfiguration(state=STATES.ONLINE)
        actualOnlineHosts = self.tested.getOnlineHosts().keys()
        self.assertItemsEqual(expectedOnlineHosts, actualOnlineHosts)

    def _validateStateMachineIsDestroyed(self, hostID):
        idsOfHostsInFreePool = [host.hostImplementation().id() for host in self.freePoolMock.all()]
        idsOfHostsInHostsPool = [host.hostImplementation().id() for host in self._hosts.all()]
        self.assertEquals([type(_id) for _id in idsOfHostsInFreePool][0], str)
        self.assertEquals([type(_id) for _id in idsOfHostsInHostsPool][0], str)
        self.assertTrue(isinstance(hostID, str))
        self.assertNotIn(hostID, idsOfHostsInFreePool)
        self.assertNotIn(hostID, idsOfHostsInHostsPool)

    def _validateOfflineHosts(self):
        expectedOfflineHosts = self._idsOfHostsInConfiguration(state=STATES.OFFLINE)
        actualOfflineHosts = self.tested.getOfflineHosts()
        idsOfActualOfflineHosts = actualOfflineHosts.keys()
        self.assertItemsEqual(expectedOfflineHosts, idsOfActualOfflineHosts)
        for hostID in idsOfActualOfflineHosts:
            self._validateStateMachineIsDestroyed(hostID)

    def _validateDetachedHosts(self):
        expectedDetachedHosts = self._idsOfHostsInConfiguration(state=STATES.DETACHED)
        actualOnlineHosts = self.tested.getOnlineHosts().keys()
        actualOfflineHosts = self.tested.getOfflineHosts().keys()
        actualDetachedHosts = self.tested.getDetachedHosts().keys()
        for hostID in expectedDetachedHosts:
            self.assertNotIn(hostID, actualOnlineHosts)
            self.assertNotIn(hostID, actualOfflineHosts)
            self.assertIn(hostID, actualDetachedHosts)
            self._validateStateMachineIsDestroyed(hostID)
            for allocation in self.allocationsMock.all():
                if allocation.dead() is not None:
                    continue
                idsOfAllocatedHosts = [host.hostImplementation().id() for host in
                                       allocation.allocated().values()]
                self.assertNotIn(hostID, idsOfAllocatedHosts)

    def _validateDNSMasqEntries(self):
        actual = self.dnsMasqMock.items
        expected = self.expectedDNSMasq.items
        self.assertEquals(actual, expected)

    def _validate(self, onlineHostsNotInPool=None):
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._validateOnlineHostsAreInHostsPool(onlineHostsNotInPool)
        self._validateDetachedHosts()
        self._validateDNSMasqEntries()

    def _idsOfHostsInConfiguration(self, state=None):
        configuration = configurationFiles[config.RACK_YAML]
        hosts = configuration['HOSTS']
        if state is None:
            return set([host['id'] for host in hosts])
        return set([host['id'] for host in hosts if host['state'].upper() == state])

    def _allocateHost(self, hostID):
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == hostID][0]
        self.freePoolMock.takeOut(stateMachine)
        allocated = {"node0": stateMachine}
        requirements = {"node0": dict(imageHint="theCoolstLabel", imageLabel="theCoolstLabel")}
        allocation = Allocation(index=0,
                                requirements=requirements,
                                allocationInfo=None,
                                allocated=allocated,
                                broadcaster=mock.Mock(),
                                freePool=self.freePoolMock,
                                hosts=self._hosts)
        self.allocationsMock.allocations.append(allocation)
        self._validate()
        return allocation

    def _destroyHost(self, hostID):
        onlineHosts = self.tested.getOnlineHosts()
        host = onlineHosts[hostID]
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == hostID][0]
        stateMachine.destroy()

if __name__ == '__main__':
    unittest.main()
