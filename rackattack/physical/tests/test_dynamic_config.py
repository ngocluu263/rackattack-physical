import unittest
import mock
from mock import patch
from rackattack.physical import ipmi
import subprocess
from rackattack.physical import dynamicconfig
from rackattack.common import hosts
from rackattack.common import dnsmasq
from rackattack.common import globallock
from rackattack.common import tftpboot
from rackattack.common import inaugurate
from rackattack.common import timer
from rackattack.physical.alloc import freepool
from rackattack.physical.alloc import allocations
import io
from rackattack.physical import config
import os
from rackattack.common import hoststatemachine
from rackattack.physical.ipmi import IPMI
import yaml
from rackattack.physical.tests.common import HostStateMachine, Allocations, FreePool, Allocation
from rackattack.physical.host import Host, STATES
from rackattack.physical import reclaimhost, network


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
        self._validateConfiguration()
        self._setRackConf('online_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

    def test_BringOnlineHostsOfflineWhileNotAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateConfiguration()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

    def test_BringHostOfflineWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == self.HOST_THAT_WILL_BE_TAKEN_OFFLINE][0]
        self.freePoolMock.takeOut(stateMachine)
        allocated = [stateMachine]
        allocation = Allocation(allocated, self.freePoolMock, self._hosts, nice=0)
        self.allocationsMock.allocations.append(allocation)
        self._validateConfiguration()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

    def test_BringHostOfflineWhileAllocatedAndAllocationIsDead(self, *_args):
        self._init('online_rack_conf.yaml')
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == self.HOST_THAT_WILL_BE_TAKEN_OFFLINE][0]
        self.freePoolMock.takeOut(stateMachine)
        allocated = [stateMachine]
        allocation = Allocation(allocated, self.freePoolMock, self._hosts, nice=0)
        self.allocationsMock.allocations.append(allocation)
        allocation.withdraw("Made up reason")
        self._validateConfiguration()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

    def test_BringHostOfflineAfterDestroyed(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateConfiguration()
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == self.HOST_THAT_WILL_BE_TAKEN_OFFLINE][0]
        stateMachine.destroy()
        destroyedID = stateMachine.hostImplementation().id()
        self._validateConfiguration(onlineHostsNotInPool=[destroyedID])
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

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
        self._validateConfiguration()
        self._setRackConf('online_rack_conf.yaml')
        self.dnsMasqMock.add.side_effect = AssertionError('Ignore this error')
        self.tested._reload()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateConfiguration()

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

    def _validateOfflineHosts(self):
        expectedOfflineHosts = self._idsOfHostsInConfiguration(state=STATES.OFFLINE)
        actualOfflineHosts = self.tested.getOfflineHosts().keys()
        self.assertItemsEqual(expectedOfflineHosts, actualOfflineHosts)
        idsOfHostsInFreePool = [host.hostImplementation().id() for host in self.freePoolMock.all()]
        for hostID in actualOfflineHosts:
            self.assertNotIn(hostID, idsOfHostsInFreePool)

    def _validateConfiguration(self, onlineHostsNotInPool=None):
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._validateOnlineHostsAreInHostsPool(onlineHostsNotInPool)

    def _idsOfHostsInConfiguration(self, state=None):
        configuration = yaml.load(open(config.RACK_YAML, 'rb'))
        hosts = configuration['HOSTS']
        if state is None:
            return set([host['id'] for host in hosts])
        return set([host['id'] for host in hosts if host['state'].upper() == state])


if __name__ == '__main__':
    unittest.main()
