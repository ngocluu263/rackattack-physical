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


@patch('signal.signal')
@patch('subprocess.check_output', return_value='')
@mock.patch('rackattack.physical.ipmi.IPMI')
class Test(unittest.TestCase):

    def setUp(self):
        self.dnsMasqMock = mock.Mock(spec=dnsmasq.DNSMasq)
        self.inaguratorMock = mock.Mock(spec=inaugurate.Inaugurate)
        self.tftpMock = mock.Mock(spec=tftpboot.TFTPBoot)
        self.freePoolMock = mock.Mock(spec=freepool.FreePool)
        self.allocationsMock = mock.Mock(spec=allocations.Allocations)
        timer.cancelAllByTag = mock.Mock()
        timer.scheduleAt = mock.Mock()
        timer.scheduleIn = mock.Mock()
        hoststatemachine.HostStateMachine = mock.Mock()

    def _setRackConf(self, fixtureFileName):
        config.RACK_YAML = os.path.join(os.path.dirname
                                        (os.path.realpath(__file__)), 'fixtures', fixtureFileName)

    def _init(self, fixtureFileName):
        self._setRackConf(fixtureFileName)
        self.tested = dynamicconfig.DynamicConfig(hosts=hosts.Hosts(),
                                                  dnsmasq=self.dnsMasqMock,
                                                  inaugurate=self.inaguratorMock,
                                                  tftpboot=self.tftpMock,
                                                  freePool=self.freePoolMock,
                                                  allocations=self.allocationsMock)

    def _validateOfflineHosts(self):
        configuration = yaml.load(open(config.RACK_YAML, 'rb'))
        expected_offline_hosts = set([host['id'] for host in
                                      configuration['HOSTS'] if
                                      host.get('offline', False)])
        actual_offline_hosts = set(self.tested.getOfflineHosts().keys())
        self.assertEqual(expected_offline_hosts, actual_offline_hosts)

    def test_addNewHostInOnlineStateDNSMasqAddHostCalled(self, *_args):
        self._init('online_rack_conf.yaml')
        self._validateOfflineHosts()
        self.assertEquals(self.dnsMasqMock.add.call_count, 4)
        self.assertEquals(self.dnsMasqMock.add.call_args_list[0][0], ('00:1e:67:48:20:60', '192.168.1.11'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[1][0], ('00:1e:67:44:40:8e', '192.168.1.12'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[2][0], ('00:1e:67:45:6e:f1', '192.168.1.13'))
        self.assertEquals(self.dnsMasqMock.add.call_args_list[3][0], ('00:1e:67:45:70:6d', '192.168.1.14'))
        self.dnsMasqMock.reset_mock()
        self._setRackConf('offline_rack_conf.yaml')
        self.tested._reload()
        self._validateOfflineHosts()
        self.assertEquals(self.dnsMasqMock.add.call_count, 0)
        self.assertEquals(self.dnsMasqMock.remove.call_count, 1)
        self.assertEquals(self.dnsMasqMock.remove.call_args_list[0][0], ('00:1e:67:45:70:6d',))


if __name__ == '__main__':
    unittest.main()
