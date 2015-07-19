import ipaddr
import unittest
from rackattack.physical import network


class Test(unittest.TestCase):
    def setUp(self):
        self.tested = network
        self.expectedIPAddressFormat = "192.168.{}.{}"
        self.expectedNrRacks = 11

    def test_SetGatewayIP(self):
        self.tested.setGatewayIP("192.168.1.3")
        self.assertEquals(self.tested.GATEWAY_IP_ADDRESS, "192.168.1.3")

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

    def test_TranslateSSHCredentialsForClientInsideSubnet(self):
        hostIndex = 1
        clientHostname = self.tested.ipAddressFromHostIndex(hostIndex + 1)
        clientPort = 2000
        hostname = self.tested.ipAddressFromHostIndex(hostIndex)
        expectedCredentials = dict(hostname=hostname)
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex, expectedCredentials,
                                                                    "somenat", peer=(clientHostname,
                                                                                     clientPort))
        self.assertEquals(translatedCredentials, expectedCredentials)

    def test_TranslateSSHCredentialsForClientOutsideSubnet(self):
        hostIndex = 1
        clientHostname = "200.1.1.1"
        clientPort = 2000
        hostname = self.tested.ipAddressFromHostIndex(hostIndex)
        credentials = dict(hostname=hostname)
        translatedCredentials = self.tested.translateSSHCredentials(hostIndex, credentials, "somenat",
                                                                    peer=(clientHostname, clientPort))
        expectedCredentials = dict(hostname="somenat", port=self.tested.sshPortFromHostIndex(hostIndex))
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

    def test_Constants(self):
        network = ipaddr.IPv4Network("%(firstIP)s/%(netmask)s" % dict(firstIP=self.tested.FIRST_IP,
                                                                      netmask=self.tested.NETMASK))
        for item in (self.tested.BOOTSERVER_IP_ADDRESS,
                     self.tested.GATEWAY_IP_ADDRESS,
                     self.tested.FIRST_IP,
                     self.tested.LAST_IP):
            self.assertIsInstance(item, str)
            self.assertTrue(network.Contains(ipaddr.IPv4Address(item)))
        self.assertIsInstance(self.tested.NETMASK, str)

if __name__ == '__main__':
    unittest.main()
