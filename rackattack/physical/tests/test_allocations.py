import mock
import unittest
from rackattack.physical.alloc.allocations import Allocations
from rackattack.physical.tests.common import Host, HostStateMachine, FreePool, Hosts


class Test(unittest.TestCase):
    def setUp(self):
        self.broadcaster = mock.Mock()
        hostNames = ["alpha", "bravo", "charlie", "delta"]
        self.hosts = Hosts()
        self.freePool = FreePool(self.hosts)
        self.osmosisServer = mock.Mock()
        for hostName in hostNames:
            stateMachine = HostStateMachine(Host(hostName))
            self.hosts.add(stateMachine)
        self.tested = Allocations(self.broadcaster, self.hosts, self.freePool, self.osmosisServer)

    def test_create(self):
        pass
