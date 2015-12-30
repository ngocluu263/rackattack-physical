import mock
import unittest
import threading
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical import ipcserver
from rackattack.common import baseipcserver
from rackattack.physical.alloc import freepool
from rackattack.common import reclaimhostspooler
from rackattack.physical.alloc import allocations
from rackattack.physical.tests.common import Hosts, HostStateMachine, Host


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.osmosisServerIP = "some-osmosis-server"
        cls.dnsmasq = mock.Mock()
        cls.broadcaster = mock.Mock()
        cls.hosts = Hosts()
        cls.freePool = freepool.FreePool(cls.hosts)
        allocations.sh.run = cls.osmosisListLabelsFoundMock
        cls.dynamicConfig = mock.Mock()
        cls.reclaimHost = mock.Mock(spec=reclaimhostspooler.ReclaimHostSpooler)
        baseipcserver.threading.Thread.daemon = mock.Mock()
        baseipcserver.threading.Event = mock.Mock()
        baseipcserver.threading.Thread.start = mock.Mock()
        timer.scheduleIn = mock.Mock()
        timer.cancelAllByTag = mock.Mock()
        cls.currentTimer = None
        cls.currentTimerTag = None
        globallock._lock.acquire()

    @classmethod
    def tearDownClass(cls):
        globallock._lock.release()

    def setUp(self):
        self.allocations = allocations.Allocations(self.broadcaster,
                                                   self.hosts,
                                                   self.freePool,
                                                   self.osmosisServerIP)
        while self.hosts.all():
            self.hosts.destroy(self.hosts.all()[0])
        hosts = list(self.freePool.all())
        for host in hosts:
            self.freePool.takeOut(host)
        self.hostsIDs = ["alpha", "bravo", "charlie", "delta"]
        for hostName in self.hostsIDs:
            stateMachine = HostStateMachine(Host(hostName))
            self.hosts.add(stateMachine)
            self.freePool.put(stateMachine)
        self.requirements = dict(node0=dict(imageLabel="echo-foxtrot", imageHint="golf"),
                                 node1=dict(imageLabel="hotel-india", imageHint="juliet"))
        self.allocationInfo = dict(purpose="racktest",
                                   user="bob",
                                   nice=0.5)
        self.tested = ipcserver.IPCServer(self.osmosisServerIP,
                                          self.dnsmasq,
                                          self.allocations,
                                          self.hosts,
                                          self.dynamicConfig,
                                          self.reclaimHost)

    def test_Allocate(self):
        allocationID = self.tested.cmd_allocate(self.requirements,
                                                self.allocationInfo,
                                                self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        self.assertEquals(allocationID, allocation.index())

    def test_InauguratorIDs(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        actual = self.tested.cmd_allocation__inauguratorsIDs(id=allocation.index(), peer=None)
        actualAllocatedNames = actual.keys()
        expectedAllocatedNames = self.requirements.keys()
        self.assertEquals(set(actualAllocatedNames), set(expectedAllocatedNames))
        self.assertEquals(len(actualAllocatedNames), len(expectedAllocatedNames))
        actualAllocatedIDs = actual.values()
        expectedAllocatedIDs = self.hostsIDs[:len(self.requirements)]
        self.assertEquals(set(actualAllocatedIDs), set(expectedAllocatedIDs))
        self.assertEquals(len(actualAllocatedIDs), len(expectedAllocatedIDs))

    def test_InauguratorIDsCrashesWhenAllocationIsDead(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        allocation.withdraw("goodbye, allocation")
        self.assertRaises(Exception,
                          self.tested.cmd_allocation__inauguratorsIDs,
                          id=allocation.index(),
                          peer=None)

    def test_AllocationNodesFailsWhenAllocationIsNotDone(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        self.assertRaises(Exception, self.tested.cmd_allocation__nodes, id=allocation.index(), peer=None)

    def test_AllocationNodesFailsWhenAllocationIsDead(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        allocation.withdraw("goodbye, allocation")
        self.assertRaises(Exception, self.tested.cmd_allocation__nodes, id=allocation.index(), peer=None)

    def test_AllocationNodes(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        self.fakeDoneForAllocation(allocation)
        actual = self.tested.cmd_allocation__nodes(id=allocation.index(), peer=None)
        actualAllocatedNames = actual.keys()
        expectedAllocatedNames = self.requirements.keys()
        self.assertEquals(set(actualAllocatedNames), set(expectedAllocatedNames))
        self.assertEquals(len(actualAllocatedNames), len(expectedAllocatedNames))
        actualAllocatedIDs = [node["id"] for node in actual.values()]
        expectedAllocatedIDs = self.hostsIDs[:len(self.requirements)]
        self.assertEquals(set(actualAllocatedIDs), set(expectedAllocatedIDs))
        self.assertEquals(len(actualAllocatedIDs), len(expectedAllocatedIDs))

    def test_AllocationFree(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        self.tested.cmd_allocation__free(id=allocation.index(), peer=None)
        self.assertEquals("freed", allocation.dead())

    def test_AllocationDone(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        actual = self.tested.cmd_allocation__done(id=allocation.index(), peer=None)
        self.assertEquals(actual, False)
        self.fakeDoneForAllocation(allocation)
        actual = self.tested.cmd_allocation__done(id=allocation.index(), peer=None)
        self.assertEquals(actual, True)

    def test_AllocationDead(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        actual = self.tested.cmd_allocation__dead(id=allocation.index(), peer=None)
        self.assertEquals(actual, None)
        allocation.withdraw("goodbye, allocation")
        actual = self.tested.cmd_allocation__dead(id=allocation.index(), peer=None)
        self.assertEquals(actual, "withdrawn")

    @classmethod
    def osmosisListLabelsFoundMock(cls, cmd):
        if cmd[0:2] == ['osmosis', 'listlabels']:
            return cmd[2]
        raise ValueError("Implement me")

    @staticmethod
    def fakeDoneForAllocation(allocation):
        for machine in allocation.allocated().values():
            machine.fakeInaugurationDone()
            machine.stateChangeCallback(machine)

if __name__ == "__main__":
    unittest.main()
