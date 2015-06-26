import sys
import mock
import random
import unittest
from rackattack.physical import ipmi
from rackattack.physical import config
from rackattack.physical import network
from rackattack.physical.host import Host
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
        self.tested = Host(index=self.index, id=self.id, ipmiLogin=self.ipmiLogin,
                           primaryMAC=self.primaryMAC, secondaryMAC=self.secondaryMAC,
                           topology=self.topology)

    def test_Fields(self):
        self.assertEquals(self.index, self.tested.index())
        self.assertEquals(self.id, self.tested.id())
        self.assertEquals(self.primaryMAC, self.tested.primaryMACAddress())
        self.assertEquals(self.secondaryMAC, self.tested.secondaryMACAddress())
        self.assert_(self.tested.ipAddress().endswith("." + str(self.index + 10)))
        rootCredentials = self.tested.rootSSHCredentials()
        self.assertEquals(rootCredentials['username'], 'root')
        self.assertEquals(rootCredentials['password'], config.ROOT_PASSWORD)
        self.assertEquals(rootCredentials['hostname'], self.tested.ipAddress())

    def test_DestroyDoesNotRaiseAnException(self):
        self.tested.destroy()

    def test_ColdRestart(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.coldRestart()
        self.assertEquals(self.tested.serialLogFilename(), "zoolootango")
        self.ipmiInstanceMock.powerCycle.assert_called_once_with()

    def test_TurnOff(self):
        self.tested.turnOff()
        self.ipmiInstanceMock.off.assert_called_once_with()

    def test_TurnOffAfterColdRestart(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.coldRestart()
        self.tested.turnOff()
        self.ipmiInstanceMock.off.assert_called_once_with()
        solInstance.stop.assert_called_once_with()
        self.assertEquals(self.tested.serialLogFilename(), "zoolootango")

    def test_FulfillsRequirement(self):
        self.assertTrue(self.tested.fulfillsRequirement('iwanticecream'))

    def test_SerialLogFilenameRaisesExceptionWhenSOLNotStarted(self):
        self.assertRaises(Exception, self.tested.serialLogFilename)

    def test_TruncateSerialLog(self):
        solInstance = mock.Mock()
        solInstance.serialLogFilename.return_value = "zoolootango"
        serialoverlan.SerialOverLan = mock.Mock(return_value=solInstance)
        self.tested.truncateSerialLog()
        self.assertFalse(solInstance.called)
        self.tested.coldRestart()
        self.tested.truncateSerialLog()
        self.assertTrue(solInstance.truncateSerialLog.called)

    def test_ReconfigureBIOSDoesNotRaisesAnException(self):
        self.tested.reconfigureBIOS()


if __name__ == '__main__':
    unittest.main()
