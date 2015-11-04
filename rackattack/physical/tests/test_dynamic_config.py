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


@patch('signal.signal')
@patch('subprocess.check_output', return_value='')
@mock.patch('rackattack.physical.ipmi.IPMI')
class Test(unittest.TestCase):
    HOST_THAT_WILL_BE_TAKEN_OFFLINE = 'rack01-server44'

    def setUp(self):
        self.dnsMasqMock = mock.Mock(spec=dnsmasq.DNSMasq)
        self.inaguratorMock = mock.Mock(spec=inaugurate.Inaugurate)
        self.tftpMock = mock.Mock(spec=tftpboot.TFTPBoot)
        self.allocationsMock = Allocations()
        self.reclaimHost = mock.Mock(spec=reclaimhost.ReclaimHost)
        timer.cancelAllByTag = mock.Mock()
        timer.scheduleAt = mock.Mock()
        timer.scheduleIn = mock.Mock()
        self._hosts = hosts.Hosts()
        self.freePoolMock = FreePool(self._hosts)
        hoststatemachine.HostStateMachine = HostStateMachine
        configurationFile = "etc.rackattack.physical.conf.example"
        with open(configurationFile) as f:
            self.conf = yaml.load(f.read())
        network.initialize_globals(self.conf)

    def _setRackConf(self, fixtureFileName):
        config.RACK_YAML = os.path.join(os.path.dirname
                                        (os.path.realpath(__file__)), 'fixtures', fixtureFileName)

    def _init(self, fixtureFileName):
        self._setRackConf(fixtureFileName)
        self.tested = dynamicconfig.DynamicConfig(hosts=self._hosts,
                                                  dnsmasq=self.dnsMasqMock,
                                                  inaugurate=self.inaguratorMock,
                                                  tftpboot=self.tftpMock,
                                                  freePool=self.freePoolMock,
                                                  allocations=self.allocationsMock,
                                                  reclaimHost=self.reclaimHost)

    def test_BringHostsOnline(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('online_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringOnlineHostsOfflineWhileNotAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringHostOfflineWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringHostOfflineWhileAllocatedAndAllocationIsDead(self, *_args):
        self._init('online_rack_conf.yaml')
        allocation = self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        allocation.withdraw("Made up reason")
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringHostOfflineAfterDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._destroyHost(hostID)
        self._validateThatConfigurationMatchesActualDataStructures(onlineHostsNotInPool=[hostID])
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachOnlineHostWhileNotAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachOnlineHostWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachOnlineHostWhileAllocatedAndAllocationIsDead(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        allocation = self._allocateHost(self.HOST_THAT_WILL_BE_TAKEN_OFFLINE)
        allocation.withdraw("Made up reason")
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachHostAfterDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._destroyHost(hostID)
        self._validateThatConfigurationMatchesActualDataStructures(onlineHostsNotInPool=[hostID])
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachHostAfterAllocatedAndDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        hostID = self.HOST_THAT_WILL_BE_TAKEN_OFFLINE
        self._allocateHost(hostID)
        self._destroyHost(hostID)
        self._validateThatConfigurationMatchesActualDataStructures(onlineHostsNotInPool=[hostID])
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringHostOnlineAfterDetached(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('online_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachOfflineHost(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_BringHostOfflineAfterDetached(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('detached_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_DetachHostAtTheBeginning(self, *_args):
        self._init('detached_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()

    def test_addNewHostInOnlineStateDNSMasqAddHostCalled(self, *_args):
        self._init('online_rack_conf.yaml')
        self.assertEquals(self.dnsMasqMock.add.call_count, 4)
        self.assertEquals(self.dnsMasqMock.add.call_args_list[0][0], ('00:1e:67:48:20:60', '192.168.1.11'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[1][0], ('00:1e:67:44:40:8e', '192.168.1.12'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[2][0], ('00:1e:67:45:6e:f1', '192.168.1.13'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[3][0], ('00:1e:67:45:70:6d', '192.168.1.14'))
        self.dnsMasqMock.reset_mock()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self.assertEquals(self.dnsMasqMock.add.call_count, 0)
        self.assertEquals(self.dnsMasqMock.remove.call_count, 1)
        self.assertEquals(self.dnsMasqMock.remove.call_args_list[0][0], ('00:1e:67:45:70:6d',))

    def test_BringHostsOnlineFailedSinceDNSMasqAddFailed(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validateThatConfigurationMatchesActualDataStructures()
        self._setRackConf('online_rack_conf.yaml')
        self.dnsMasqMock.add.side_effect = AssertionError('Ignore this error')
        self.tested._reload()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateThatConfigurationMatchesActualDataStructures()

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
                idsOfAllocatedHosts = [host.hostImplementation().id() for host in
                                       allocation.allocated().values()]
                self.assertNotIn(hostID, idsOfAllocatedHosts)

    def _validateThatConfigurationMatchesActualDataStructures(self, onlineHostsNotInPool=None):
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._validateOnlineHostsAreInHostsPool(onlineHostsNotInPool)
        self._validateDetachedHosts()

    def _idsOfHostsInConfiguration(self, state=None):
        configuration = yaml.load(open(config.RACK_YAML, 'rb'))
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
        self._validateThatConfigurationMatchesActualDataStructures()
        return allocation

    def _destroyHost(self, hostID):
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == hostID][0]
        stateMachine.destroy()

if __name__ == '__main__':
    unittest.main()
