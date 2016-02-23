import time
import yaml
import ipaddr
import unittest
from rackattack.physical import config
from rackattack.physical import network


class Test(unittest.TestCase):
    CONFIGURATION_FILE = config.EXAMPLE_CONF_YAML

    @classmethod
    def setUpClass(cls):
        with open(cls.CONFIGURATION_FILE) as f:
            cls.exampleConf = yaml.load(f.read())

    def setUp(self):
        self.conf = dict(self.exampleConf)
        network.initialize_globals(self.conf)
        self.tested = network
        self.tested.initialize_globals(self.conf)
        self.expectedIPAddressFormat = "192.168.{}.{}"
        self.expectedNrRacks = 11

    def test_IpAddressFromHostIndex(self):
        self.expectedNrRacks = 11
        nrServersPerRack = 64
        expectedIPAddressParts = [1, 11]
        hostIndex = 1
        for rack in xrange(1, self.expectedNrRacks + 1):
            for server in xrange(nrServersPerRack + 1):
                expected = self.expectedIPAddressFormat.format(*expectedIPAddressParts)
                actual = self.tested.ipAddressFromHostIndex(hostIndex)
                self.assertNotEqual(actual, self.tested.BOOTSERVER_IP_ADDRESS)
                self.assertNotEqual(actual, self.tested.GATEWAY_IP_ADDRESS)
                self.assertEquals(actual, expected)
                hostIndex += 1
                expectedIPAddressParts[1] += 1
                if expectedIPAddressParts[1] > 255:
                    expectedIPAddressParts[1] = 0
                    expectedIPAddressParts[0] += 1
                    self.assertLess(expectedIPAddressParts[0], 255)

    def test_TranslateSSHCredentialsForClientInsideSubnetWithNAT(self):
        self.assertNotEqual("", self.conf["PUBLIC_NAT_IP"])
        hostIndex = 1
        clientHostname = self.tested.ipAddressFromHostIndex(hostIndex + 1)
        clientPort = 2000
        hostnameBeforeTranslation = self.tested.ipAddressFromHostIndex(hostIndex)
        credentialsBeforeTranslation = dict(hostname=hostnameBeforeTranslation)
        expectedCredentials = credentialsBeforeTranslation
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex,
                                                                    credentialsBeforeTranslation,
                                                                    peer=(clientHostname, clientPort))
        self.assertEquals(translatedCredentials, expectedCredentials)

    def test_TranslateSSHCredentialsForClientOutsideSubnetWithNAT(self):
        self.assertNotEqual("", self.conf["PUBLIC_NAT_IP"])
        hostIndex = 1
        clientHostname = "200.1.1.1"
        clientPort = 2000
        hostnameBeforeTranslation = self.tested.ipAddressFromHostIndex(hostIndex)
        credentialsBeforeTranslation = dict(hostname=hostnameBeforeTranslation)
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex,
                                                                    credentialsBeforeTranslation,
                                                                    peer=(clientHostname, clientPort))
        expectedCredentials = dict(hostname=self.conf["PUBLIC_NAT_IP"],
                                   port=self.tested.sshPortFromHostIndex(hostIndex))
        self.assertEquals(translatedCredentials, expectedCredentials)

    def test_TranslateSSHCredentialsForClientInsideSubnetWithoutNAT(self):
        self.conf["PUBLIC_NAT_IP"] = ""
        network.initialize_globals(self.conf)
        hostIndex = 1
        clientHostname = self.tested.ipAddressFromHostIndex(hostIndex + 1)
        clientPort = 2000
        hostnameBeforeTranslation = self.tested.ipAddressFromHostIndex(hostIndex)
        credentialsBeforeTranslation = dict(hostname=hostnameBeforeTranslation, port=22)
        expectedCredentials = credentialsBeforeTranslation
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex,
                                                                    credentialsBeforeTranslation,
                                                                    peer=(clientHostname, clientPort))
        self.assertEquals(translatedCredentials, expectedCredentials)

    def test_TranslateSSHCredentialsForClientOutsideSubnetWithoutNAT(self):
        self.conf["PUBLIC_NAT_IP"] = ""
        network.initialize_globals(self.conf)
        hostIndex = 1
        clientHostname = "200.1.1.1"
        clientPort = 2000
        hostnameBeforeTranslation = self.tested.ipAddressFromHostIndex(hostIndex)
        credentialsBeforeTranslation = dict(hostname=hostnameBeforeTranslation, port=22)
        expectedCredentials = credentialsBeforeTranslation
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex,
                                                                    credentialsBeforeTranslation,
                                                                    peer=(clientHostname, clientPort))
        self.assertEquals(translatedCredentials, expectedCredentials)

    def test_LotsOfHosts(self):
        self.MinNrRacksRequired = 11
        nrServersPerRack = 64
        indexLowerBound = self.expectedNrRacks * nrServersPerRack + 1
        self.assertLessEqual(indexLowerBound, self.tested.LAST_INDEX)
        self.assertEquals(self.tested.FIRST_IP, self.tested.ipAddressFromHostIndex(1))
        self.assertEquals(self.tested.LAST_IP, self.tested.ipAddressFromHostIndex(self.tested.LAST_INDEX))

    def test_AddressesConformWithNetmask(self):
        firstIP = self.expectedIPAddressFormat.format(0, 0)
        networkStringRepr = "%(firstIP)s/%(netmask)s" % dict(firstIP=firstIP, netmask=self.tested.NETMASK)
        network = ipaddr.IPv4Network(networkStringRepr)
        for addrIdx in xrange(1, self.tested.LAST_INDEX + 1):
            ipAddr = self.tested.ipAddressFromHostIndex(addrIdx)
            self.assertTrue(network.Contains(ipaddr.IPv4Address(ipAddr)))

if __name__ == '__main__':
    unittest.main()
