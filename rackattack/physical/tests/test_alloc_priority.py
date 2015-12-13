import unittest
import mock
from rackattack import api
from rackattack.common import hosts
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
        self.hosts = hosts.Hosts()

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
        self.assertIsNotNone(self.allocations[0].dead())

    def test_DoesNotTakeMachinesFromHigherPriority(self):
        stateMachine = self._generateStateMachine('host1')
        allocated = [stateMachine]
        self.allocations.append(Allocation(allocated, self.freePool, self.hostsStateMachines, 0.1))
        self.requirements['yuvu'] = 'spec'
        with self.assertRaises(priority.OutOfResourcesError):
            self.construct()
        self.assertEquals(len(self.allocations[0].allocated()), 1)

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
        self.assertEquals(len(self.allocations[0].allocated()), 1)
        self.assertEquals(self.allocations[0].allocated()['yuvu0'], stateMachineWhichIsAlreadyAllocated)

    def test_PreemptFromYoungestOfTheNicestAllocations(self):
        niceValues = [0.6, 0.9, 0.8, 0.9, 0.85, 0.9, 0.6, 0.5, 0.6, 0.5]
        nicest = max(niceValues)
        nicestAllocations = []
        machines = []
        for idx, nice in enumerate(niceValues):
            stateMachine = self._generateStateMachine('stateMachine_%(idx)s' % dict(idx=idx))
            allocated = [stateMachine]
            allocation = Allocation(allocated, self.freePool, self.hostsStateMachines, nice)
            self.allocations.append(allocation)
            if nice == nicest:
                nicestAllocations.append(allocation)
            machines.append(stateMachine)
        # This validates that we actually test the two-criteria sort (by nice and then by age)
        self.assertGreater(len(nicestAllocations), 1)
        youngestOfNicestAllocations = nicestAllocations[-1]
        allocationExpectedToBePreempted = youngestOfNicestAllocations
        machineExpectedToBePreempted = allocationExpectedToBePreempted.allocated()['yuvu0']
        self.requirements['yuvu'] = 'spec'
        self.construct()
        self.assertEquals(len(self.tested.allocated()), 1)
        self.assertIs(self.tested.allocated()['yuvu'], machineExpectedToBePreempted)
        self.assertEquals(len(self.freePool.all()), 0)
        self.assertIsNotNone(allocationExpectedToBePreempted.dead())
        for idx, allocation in enumerate(self.allocations):
            if allocation == allocationExpectedToBePreempted:
                continue
            self.assertEquals(len(allocation.allocated()), 1)
            self.assertIs(allocation.allocated()['yuvu0'], machines[idx])

    def test_DoesNotAttemptToWithdrawADeadAllocation(self):
        stateMachine = self._generateStateMachine('host1')
        allocated = [stateMachine]
        allocationNotToTakeHostsFrom = Allocation(allocated, self.freePool, self.hostsStateMachines, 0.9)
        self.allocations.append(allocationNotToTakeHostsFrom)
        allocationNotToTakeHostsFrom.withdraw("some reason")
        self.assertIsNotNone(self.allocations[0].dead())
        self.assertEquals(self.freePool.all()[0], stateMachine)
        self.assertEquals(len(self.freePool.all()), 1)
        self.requirements['yuvu1'] = 'spec'
        self.requirements['yuvu2'] = 'spec'
        with self.assertRaises(priority.OutOfResourcesError):
            self.construct()
        self.assertEquals(len(self.freePool.all()), 1)
        self.assertIsNotNone(self.allocations[0].dead())

    def _generateStateMachine(self, name):
        stateMachine = HostStateMachine(Host(name))
        self.hosts.add(stateMachine)
        return stateMachine

if __name__ == '__main__':
    unittest.main()
