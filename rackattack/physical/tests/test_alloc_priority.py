import unittest
from rackattack import api
from rackattack.common import globallock
from rackattack.physical.alloc import priority
from rackattack.physical.tests.common import HostStateMachine, FreePool, Allocation, Host


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self.freePool = FreePool()
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
        self.freePool._pool.append(stateMachine)
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachine)
        self.assertEquals(len(self.freePool._pool), 0)

    def test_AllocateOneByWithdrawingAnAllocation(self):
        self.allocations.append(Allocation(self.freePool, 0.9))
        stateMachine = self._generateStateMachine('host1')
        self.allocations[0].allocatedHosts.append(stateMachine)
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachine)
        self.assertEquals(len(self.freePool._pool), 0)
        self.assertIs(self.allocations[0].allocatedHosts, None)

    def test_DoesNotTakeMachinesFromHigherPriority(self):
        self.allocations.append(Allocation(self.freePool, 0.1))
        self.allocations[0].allocatedHosts.append(self._generateStateMachine('host1'))
        self.requirements['yuvu'] = 'spec'
        with self.assertRaises(priority.OutOfResourcesError):
            self.construct()
        self.assertEquals(len(self.allocations[0].allocatedHosts), 1)

    def test_AllocateOneFromFreePool_DontTouchExisting(self):
        self.allocations.append(Allocation(self.freePool, 0.9))
        stateMachine = self._generateStateMachine('host1')
        self.allocations[0].allocatedHosts.append(stateMachine)
        self.freePool._pool.append(stateMachine)
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], stateMachine)
        self.assertEquals(len(self.freePool._pool), 0)
        self.assertEquals(len(self.allocations[0].allocatedHosts), 1)

    def _generateStateMachine(self, name):
        return HostStateMachine(Host(name))

if __name__ == '__main__':
    unittest.main()
