import unittest
import mock
from rackattack import api
from rackattack.common import globallock
from rackattack.physical.alloc import priority
from rackattack.physical.tests.common import HostStateMachine, FreePool, Allocation, Host


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self.freePool = FreePool()
        self.hostsStateMachines = mock.Mock()
        self.allocationInfo = api.AllocationInfo(user='test', purpose='user', nice=0.5).__dict__
        self.allocations = []
        self.requirements = {}

    def tearDown(self):
        globallock._lock.release()

    def construct(self):
        self.tested = priority.Priority(
            self.requirements, self.allocationInfo, self.freePool, self.allocations)

    def test_NoHostsAllocationFailes(self):
        self.requirements['yuvu'] = 'spec'
        with self.assertRaises(priority.OutOfResourcesError):
            self.construct()

    def test_AllocateOneFromFreePool(self):
        stateMachine = self._generateStateMachine('host1')
        self.freePool.put(stateMachine)
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachine)
        self.assertEquals(len(self.freePool.all()), 0)

    def test_AllocateOneByWithdrawingAnAllocation(self):
        stateMachine = self._generateStateMachine('host1')
        allocated = [stateMachine]
        self.allocations.append(Allocation(allocated, self.freePool, self.hostsStateMachines, 0.9))
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachine)
        self.assertEquals(len(self.freePool.all()), 0)
        self.assertEquals(self.allocations[0].allocatedHosts, [])

    def test_DoesNotTakeMachinesFromHigherPriority(self):
        stateMachine = self._generateStateMachine('host1')
        allocated = [stateMachine]
        self.allocations.append(Allocation(allocated, self.freePool, self.hostsStateMachines, 0.1))
        self.requirements['yuvu'] = 'spec'
        with self.assertRaises(priority.OutOfResourcesError):
            self.construct()
        self.assertEquals(len(self.allocations[0].allocatedHosts), 1)

    def test_AllocateOneFromFreePool_DontTouchExisting(self):
        stateMachineWhichIsAlreadyAllocated = self._generateStateMachine('busyHost')
        allocated = [stateMachineWhichIsAlreadyAllocated]
        self.allocations.append(Allocation(allocated, self.freePool, self.hostsStateMachines, 0.9))
        stateMachineExpectedToBeAllocated = self._generateStateMachine('freeHost')
        self.freePool.put(stateMachineExpectedToBeAllocated)
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachineExpectedToBeAllocated)
        self.assertEquals(len(self.freePool.all()), 0)
        self.assertEquals(len(self.allocations[0].allocatedHosts), 1)
        self.assertEquals(self.allocations[0].allocatedHosts[0], stateMachineWhichIsAlreadyAllocated)

    def _generateStateMachine(self, name):
        return HostStateMachine(Host(name))

if __name__ == '__main__':
    unittest.main()
