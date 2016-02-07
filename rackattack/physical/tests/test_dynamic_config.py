import unittest
import mock
import contextlib
from mock import patch
from rackattack.physical import dynamicconfig
from rackattack.common import hosts
from rackattack.common import dnsmasq
from rackattack.common import tftpboot
from rackattack.common import inaugurate
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical import config
import os
from rackattack.common import hoststatemachine
import yaml
from rackattack.physical.tests.common import HostStateMachine, Allocations
from rackattack.physical.host import Host, STATES
from rackattack.physical import reclaimhost, network
from rackattack.physical.alloc import freepool
from rackattack.physical.alloc.allocation import Allocation
from rackattack.common.tests.mockfilesystem import enableMockedFilesystem, disableMockedFilesystem
import netaddr
import threading
import greenlet


configurations = {}


class FakeDNSMasq:
    def __init__(self):
        self.items = dict()
        self.side_effect = None

    def add(self, mac, address):
        if self.side_effect is not None:
            raise self.side_effect
        assert mac not in self.items
        self.items[mac] = address

    def reset(self):
        self.items = dict()
        self.side_effect = None

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
        for filename in configurationFilenames:
            filepath = os.path.join(cls.CONFIG_FILES_DIR, filename)
            with open(filepath) as confFile:
                contents = confFile.read()
            configuration = yaml.load(contents)
            configurations[filename] = configuration

    @classmethod
    def setUpClass(cls):
        cls.fakeFilesystem = enableMockedFilesystem(dynamicconfig)
        cls.loadConfigurationFilesToMemory()
        cls._createFakeFilesystem()
        cls.inaguratorMock = mock.Mock(spec=inaugurate.Inaugurate)
        cls.tftpMock = mock.Mock(spec=tftpboot.TFTPBoot)
        cls.reclaimHost = mock.Mock(spec=reclaimhost.ReclaimHost)
        cls.dnsMasqMock = FakeDNSMasq()
        cls.expectedDNSMasq = FakeDNSMasq()
        cls.mockNetworkConf = {'NODES_SUBNET_PREFIX_LENGTH': 22, 'ALLOW_CLEARING_OF_DISK': False,
                               'OSMOSIS_SERVER_IP': '10.0.0.26',
                               'PUBLIC_NAT_IP': '192.168.1.2',
                               'GATEWAY_IP': '192.168.1.2',
                               'FIRST_IP': '192.168.1.11',
                               'BOOTSERVER_IP': '192.168.1.1',
                               'PUBLIC_INTERFACE': '00:1e:67:44:13:a1'}
        network.initialize_globals(cls.mockNetworkConf)
        timer.cancelAllByTag = mock.Mock()
        timer.scheduleAt = mock.Mock()
        timer.scheduleIn = mock.Mock()

    def setUp(self):
        self.addCleanup(self.releaseLock)
        globallock._lock.acquire()
        self.dnsMasqMock.reset()
        self.expectedDNSMasq.reset()
        self.addresses = [network.ipAddressFromHostIndex(i) for i in xrange(1, 10)]
        self.inaguratorMock.reset_mock()
        self.tftpMock.reset_mock()
        self.allocationsMock = Allocations()
        self.reclaimHost.reset_mock()
        self._hosts = hosts.Hosts()
        self.expectedAddresses = dict()
        self.freePool = freepool.FreePool(self._hosts)
        hoststatemachine.HostStateMachine = HostStateMachine

    @classmethod
    def tearDownClass(cls):
        disableMockedFilesystem(dynamicconfig)

    def releaseLock(self):
        globallock._lock.release()

    @staticmethod
    @contextlib.contextmanager
    def unlock():
        globallock._lock.release()
        yield
        globallock._lock.acquire()

    @classmethod
    def _createFakeFilesystem(cls):
        cls.fakeFilesystem.CreateDirectory(cls.CONFIG_FILES_DIR)
        for _filename, contents in configurations.iteritems():
            contents = yaml.dump(contents)
            cls.fakeFilesystem.CreateFile(_filename, contents=contents)

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
#            if newState == STATES.ONLINE and oldState != STATES.ONLINE:
            if hostID not in self.expectedAddresses:
                address = self.addresses.pop(0)
                self.expectedAddresses[hostID] = address
            if hostNewData["primaryMAC"] not in self.expectedDNSMasq.items:
                self.expectedDNSMasq.add(hostNewData["primaryMAC"],
                                         self.expectedAddresses[hostID])
#            elif newState == STATES.OFFLINE and oldState == STATES.ONLINE:
#                self.expectedDNSMasq.remove(hostNewData["primaryMAC"])
#            elif newState == STATES.DETACHED and oldState == STATES.ONLINE:
#                self.expectedDNSMasq.remove(hostNewData["primaryMAC"])

    def _updateExpectedDnsMasqEntriesUponLoad(self, configuration):
        for hostData in configuration:
            state = self._normalizeState(hostData["state"])
#            if state == STATES.ONLINE:
            address = self.addresses.pop(0)
            self.expectedAddresses[hostData["id"]] = address
            self.expectedDNSMasq.add(hostData["primaryMAC"], address)

    def _reloadRackConf(self, fixtureFileName, failureExpected=False):
        oldConfiguration = configurations[config.RACK_YAML]["HOSTS"]
        config.RACK_YAML = fixtureFileName
        newConfiguration = None
        if not failureExpected:
            newConfiguration = configurations[config.RACK_YAML]["HOSTS"]
            self._updateExpectedDnsMasqEntriesUponReload(oldConfiguration, newConfiguration)
        with self.unlock():
            self.tested._reload()
        self._validateDNSMasqEntries()
        return newConfiguration

    def _threadInitRegisterThreadWrapper(self, *args, **kwargs):
        self._origThreadInit(*args, **kwargs)
        threadInstance = args[0]
        self._threads.add(threadInstance)

    def _generateTestedInstanceWithMockedThreading(self):
        module = dynamicconfig
        self._origThreadInit = threading.Thread.__init__
        origThreadStart = threading.Thread.start
        self._threads = set()
        try:
            module.threading.Thread.__init__ = \
                self._threadInitRegisterThreadWrapper
            module.threading.Thread.daemon = mock.Mock()
            module.threading.Event = mock.Mock()
            threading.Thread.start = mock.Mock()
            dynamicconfig.DynamicConfig.asyncReload = dynamicconfig.DynamicConfig._reload
            instance = dynamicconfig.DynamicConfig(hosts=self._hosts,
                                                   dnsmasq=self.dnsMasqMock,
                                                   inaugurate=self.inaguratorMock,
                                                   tftpboot=self.tftpMock,
                                                   freePool=self.freePool,
                                                   allocations=self.allocationsMock,
                                                   reclaimHost=self.reclaimHost)
        finally:
            threading.Thread.__init__ = self._origThreadInit
            threading.Thread.start = origThreadStart
        assert len(self._threads) == 1
        thread = self._threads.pop()
        return instance

    def _init(self, fixtureFileName):
        config.RACK_YAML = fixtureFileName
        configuration = configurations[fixtureFileName]["HOSTS"]
        self._updateExpectedDnsMasqEntriesUponLoad(configuration)
        with self.unlock():
            self.tested = self._generateTestedInstanceWithMockedThreading()

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
        self.assertEquals(self.dnsMasqMock['00:1e:67:45:70:6d'], '192.168.1.14')
#       self.assertNotIn('00:1e:67:45:70:6d', self.dnsMasqMock.items)

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

    def test_HostGoesToDefaultPoolIfPoolIsRemovedFromConfiguration(self, *args):
        self._init('different_pool_rack_conf.yaml')
        hosts = self.tested.getOnlineHosts()
        hostWithDifferentPool = [_host for _host in configurations['different_pool_rack_conf.yaml']['HOSTS']
                                 if _host.get("pool", Host.DEFAULT_POOL) != Host.DEFAULT_POOL][0]
        for hostID, host in hosts.iteritems():
            if hostID == hostWithDifferentPool["id"]:
                expectedPool = hostWithDifferentPool["pool"]
            else:
                expectedPool = Host.DEFAULT_POOL
            self.assertEquals(host.pool(), expectedPool)
        newConfiguration = self._reloadRackConf('online_rack_conf.yaml')
        changedHost = [host for host in newConfiguration if host['id'] == hostWithDifferentPool["id"]][0]
        # This validates that the test configuration simulates the right condition (no 'pool' field)
        self.assertNotIn("pool", changedHost)
        for host in hosts.values():
            self.assertEquals(host.pool(), Host.DEFAULT_POOL)

    def test_HostGoesToDefaultTargetDeviceIfFieldIsRemovedFromConfiguration(self, *args):
        self._init('different_target_device_rack_conf.yaml')
        hosts = self.tested.getOnlineHosts()
        hostWithDifferentTargetDevice = [_host for _host in
                                         configurations['different_target_device_rack_conf.yaml']['HOSTS']
                                         if _host.get("targetDevice", Host.DEFAULT_TARGET_DEVICE) !=
                                         Host.DEFAULT_TARGET_DEVICE][0]
        for hostID, host in hosts.iteritems():
            if hostID == hostWithDifferentTargetDevice["id"]:
                expectedTargetDevice = hostWithDifferentTargetDevice["targetDevice"]
            else:
                expectedTargetDevice = Host.DEFAULT_TARGET_DEVICE
            self.assertEquals(host.targetDevice(), expectedTargetDevice)
        newConfiguration = self._reloadRackConf('online_rack_conf.yaml')
        changedHost = [host for host in newConfiguration if host['id'] ==
                       hostWithDifferentTargetDevice["id"]][0]
        # This validates that the test configuration simulates the right condition (no 'TargetDevice' field)
        self.assertNotIn("targetDevice", changedHost)
        for host in hosts.values():
            self.assertEquals(host.targetDevice(), Host.DEFAULT_TARGET_DEVICE)

    def test_NICBondings(self, *args):
        self._init('nic_bonding_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('online_rack_conf.yaml')
        self._validate()

    def test_ChangeNICBondings(self, *args):
        self._init('online_rack_conf.yaml')
        self._validate()
        self._reloadRackConf('nic_bonding_rack_conf.yaml')
        self._validate()

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
        idsOfHostsInFreePool = [host.hostImplementation().id() for host in self.freePool.all()]
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

    def _validateNICBondings(self):
        allHosts = self.tested.getOnlineHosts()
        allHosts.update(self.tested.getOfflineHosts())
        allHosts.update(self.tested.getDetachedHosts())
        configuration = configurations[config.RACK_YAML]["HOSTS"]
        for hostID, host in allHosts.iteritems():
            actual = host.getNICBondings()
            expected = [host for host in configuration if hostID == host["id"]][0].get(
                "NICBondings", list())
            self.assertEquals(actual, expected)

    def _validate(self, onlineHostsNotInPool=None):
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._validateOnlineHostsAreInHostsPool(onlineHostsNotInPool)
        self._validateDetachedHosts()
        self._validateDNSMasqEntries()
        self._validateNICBondings()

    def _idsOfHostsInConfiguration(self, state=None):
        configuration = configurations[config.RACK_YAML]
        hosts = configuration['HOSTS']
        if state is None:
            return set([host['id'] for host in hosts])
        return set([host['id'] for host in hosts if host['state'].upper() == state])

    def _allocateHost(self, hostID):
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == hostID][0]
        self.freePool.takeOut(stateMachine)
        allocated = {"node0": stateMachine}
        requirements = {"node0": dict(imageHint="theCoolstLabel", imageLabel="theCoolstLabel")}
        allocation = Allocation(index=0,
                                requirements=requirements,
                                allocationInfo=None,
                                allocated=allocated,
                                broadcaster=mock.Mock(),
                                freePool=self.freePool,
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
