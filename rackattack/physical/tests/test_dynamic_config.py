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
        timer.cancelAllByTag = mock.Mock()
        timer.scheduleAt = mock.Mock()
        timer.scheduleIn = mock.Mock()
        self._hosts = hosts.Hosts()
        self.freePoolMock = FreePool(self._hosts)
        hoststatemachine.HostStateMachine = HostStateMachine

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
                                                  allocations=self.allocationsMock)

    def _validateOnlineHosts(self):
        configuration = yaml.load(open(config.RACK_YAML, 'rb'))
        expectedOnlineHosts = set([host['id'] for host in configuration['HOSTS'] if
                                   not host.get('offline', False)])
        actualOnineHosts = set(self.tested.getOnlineHosts().keys())
        self.assertEqual(expectedOnlineHosts, actualOnineHosts)

    def test_BringHostsOnline(self, *_args):
        self._init('offline_rack_conf.yaml')
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._setRackConf('online_rack_conf.yaml')
        self.tested._reload()
        self._validateOnlineHosts()
        self._validateOfflineHosts()

    def test_BringHostsOffline(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateOnlineHosts()
        self._validateOfflineHosts()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateOnlineHosts()
        self._validateOfflineHosts()

    def test_BringHostOfflineWhileAllocated(self, *_args):
        self._init('online_rack_conf.yaml')
        allocation = Allocation(self.freePoolMock, nice=0)
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == self.HOST_THAT_WILL_BE_TAKEN_OFFLINE][0]
        allocation.allocatedHosts.append(stateMachine)
        self.allocationsMock.allocations.append(allocation)
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()

    def _validateOfflineHosts(self):
        configuration = yaml.load(open(config.RACK_YAML, 'rb'))
        expectedOfflineHosts = set([host['id'] for host in configuration['HOSTS'] if
                                    host.get('offline', False)])
        actualOfflineHosts = set(self.tested.getOfflineHosts().keys())
        self.assertEqual(expectedOfflineHosts, actualOfflineHosts)

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

    def test_takeDestroyedHostOffline(self, *_args):
        self._init('online_rack_conf.yaml')
        stateMachine = [stateMachine for stateMachine in self._hosts.all() if
                        stateMachine.hostImplementation().id() == self.HOST_THAT_WILL_BE_TAKEN_OFFLINE][0]
        self._hosts.destroy(stateMachine)
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()

if __name__ == '__main__':
    unittest.main()
