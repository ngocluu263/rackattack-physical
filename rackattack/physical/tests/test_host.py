import sys
import yaml
import mock
import random
import netaddr
import unittest
from rackattack.physical import ipmi
from rackattack.physical import config
from rackattack.physical import network
from rackattack.physical import host
from rackattack.physical import serialoverlan


class Test(unittest.TestCase):
    def setUp(self):
        self.index = random.randint(1, 255)
        self.id = 'rack01-server49'
        self.ipmiLogin = dict(username='johabab', password='12345679', hostname='192.168.100.100')
        self.primaryMAC = 'alpha'
        self.secondaryMAC = 'bravo'
        self.topology = 'whatisthisfield?'
        self.ipmiInstanceMock = mock.Mock()
        self.ipmiMock = mock.Mock(return_value=self.ipmiInstanceMock)
        ipmi.IPMI = self.ipmiMock
        self.tested = host.Host(index=self.index, id=self.id, ipmiLogin=self.ipmiLogin,
                                primaryMAC=self.primaryMAC, secondaryMAC=self.secondaryMAC,
                                topology=self.topology, state=host.STATES.ONLINE, pool="thePool")
        with open(config.EXAMPLE_CONF_YAML) as f:
            self.conf = yaml.load(f.read())
        network.initialize_globals(self.conf)

    def test_Fields(self):
        self.assertEquals(self.index, self.tested.index())
        self.assertEquals(self.id, self.tested.id())
        self.assertEquals(self.primaryMAC, self.tested.primaryMACAddress())
        self.assertEquals(self.secondaryMAC, self.tested.secondaryMACAddress())
        ipAddress = self.tested.ipAddress()
        netaddr.IPAddress(ipAddress)
        del ipAddress
        rootCredentials = self.tested.rootSSHCredentials()
        self.assertEquals(rootCredentials['username'], 'root')
        self.assertEquals(rootCredentials['password'], config.ROOT_PASSWORD)
        self.assertEquals(rootCredentials['hostname'], self.tested.ipAddress())
        self.assertEquals(self.ipmiLogin, self.tested.ipmiLoginCredentials())
        self.assertEquals("thePool", self.tested.pool())
        self.assertEquals(None, self.tested.targetDevice())

    def test_DestroyDoesNotRaiseAnException(self):
        self.tested.destroy()

    def test_ValidateSOLStarted(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.validateSOLStarted()
        self.assertEquals(self.tested.serialLogFilename(), "zoolootango")

    def test_TurnOff(self):
        self.tested.turnOff()
        self.ipmiInstanceMock.off.assert_called_once_with()

    def test_TurnOffAfterSOLStarted(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.validateSOLStarted()
        self.tested.turnOff()
        self.ipmiInstanceMock.off.assert_called_once_with()
        solInstance.stop.assert_called_once_with()
        self.assertEquals(self.tested.serialLogFilename(), "zoolootango")

    def test_FulfillsRequirement(self):
        requirement = dict(pool="thePool")
        self.assertTrue(self.tested.fulfillsRequirement(requirement))
        requirement = dict(pool="notThePool")
        self.assertFalse(self.tested.fulfillsRequirement(requirement))
        requirement = dict(pool=host.Host.DEFAULT_POOL)
        self.assertFalse(self.tested.fulfillsRequirement(requirement))
        requirement = dict()
        self.assertFalse(self.tested.fulfillsRequirement(requirement))
        requirement = dict(pool=None)
        self.assertFalse(self.tested.fulfillsRequirement(requirement))
        hostInDefault = host.Host(index=self.index, id=self.id, ipmiLogin=self.ipmiLogin,
                                  primaryMAC=self.primaryMAC, secondaryMAC=self.secondaryMAC,
                                  topology=self.topology, state=host.STATES.ONLINE,
                                  pool=host.Host.DEFAULT_POOL)
        requirement = dict(pool="thePool")
        self.assertFalse(hostInDefault.fulfillsRequirement(requirement))
        requirement = dict(pool=host.Host.DEFAULT_POOL)
        self.assertTrue(hostInDefault.fulfillsRequirement(requirement))
        requirement = dict()
        self.assertTrue(hostInDefault.fulfillsRequirement(requirement))
        requirement = dict(pool=None)
        self.assertTrue(hostInDefault.fulfillsRequirement(requirement))

    def test_fulfillsWildcardSearchTermRequirement(self):
        requirement = dict(pool="thePool")
        termsThatMatch = ["", "rack01-server49", "rack01-*", "*-server49", "*", "**", "rack*-server*",
                          "*rack*"]
        for term in termsThatMatch:
            requirement["serverIDWildcard"] = term
            self.assertTrue(self.tested.fulfillsRequirement(requirement), term)
        termsThatDontMatch = ["rack01-server20", "rack02-*", "*-server20", "rack*-client*", "foo*"]
        for term in termsThatDontMatch:
            requirement["serverIDWildcard"] = term
            self.assertFalse(self.tested.fulfillsRequirement(requirement), term)

    def test_SerialLogFilenameRaisesExceptionWhenSOLNotStarted(self):
        self.assertRaises(Exception, self.tested.serialLogFilename)

    def test_TruncateSerialLog(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.truncateSerialLog()
        self.assertFalse(solInstance.called)
        self.tested.validateSOLStarted()
        self.tested.truncateSerialLog()
        self.assertTrue(solInstance.truncateSerialLog.called)

    def test_TruncateSerialLogEveryNCalls(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.validateSOLStarted()
        for i in range(1):
            for _ in range(host.Host.NR_TRUNCATION_CALLS_BEFORE_ACTUAL_TRUNCATION):
                self.assertFalse(solInstance.truncateSerialLog.called)
                self.tested.truncateSerialLogEveryNCalls()
            self.tested.truncateSerialLogEveryNCalls()
            self.assertTrue(solInstance.truncateSerialLog.called)
            solInstance.truncateSerialLog.reset_mock()

    def test_ReconfigureBIOSDoesNotRaisesAnException(self):
        self.tested.reconfigureBIOS()

    def test_changePool(self):
        self.tested.setPool("anotherpool")
        self.assertEquals(self.tested.pool(), "anotherpool")


if __name__ == '__main__':
    unittest.main()
