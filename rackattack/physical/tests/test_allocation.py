import sys
import copy
import time
import mock
import random
import unittest
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical.alloc import allocation
from rackattack.physical.alloc.freepool import FreePool
from rackattack.physical.tests.common import (HostStateMachine, Host, Hosts, Publish,
                                              executeCodeWhileAllocationIsDeadOfHeartbeatTimeout)


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self.currentTimer = None
        self.currentTimerTag = None
        timer.scheduleIn = self.scheduleTimerIn
        timer.cancelAllByTag = self.cancelAllTimersByTag
        requirements = dict(node0=dict(imageHint='alpha-bravo', imageLabel='tango-lima'),
                            node1=dict(imageHint='charlie-delta', imageLabel='kilo-juliet'),
                            node2=dict(imageHint='echo-foxtrot', imageLabel='zooloo-papa'))
        self.index = random.randint(1, sys.maxint)
        self.allocationInfo = 'This allocation has got swag.'
        self.allocated = dict((hostName, HostStateMachine(Host(hostName)))
                              for hostName in requirements.keys())
        self.originalAllocated = copy.copy(self.allocated)
        self.expectedAllocatedAtTheEnd = copy.copy(self.allocated)
        self.broadcaster = Publish()
        hosts = Hosts()
        self.freepool = FreePool(hosts)
        for stateMachine in self.allocated.values():
            hosts.add(stateMachine)
        self.tested = allocation.Allocation(self.index, requirements, self.allocationInfo, self.allocated,
                                            self.broadcaster, self.freepool, hosts)

    def tearDown(self):
        globallock._lock.release()

    def test_Index(self):
        self.assertEquals(self.tested.index(), self.index)

    def test_AllocationInfo(self):
        self.assertEquals(self.allocationInfo, self.tested.allocationInfo())

    def test_InauguratedWhenNotDoneRaisesAssertionError(self):
        self.assertRaises(AssertionError, self.tested.inaugurated)

    def test_InauguratedWhenDone(self):
        self.fakeInaugurationDoneForAll()
        self.assertEquals(self.expectedAllocatedAtTheEnd, self.tested.inaugurated())
        self.assertFalse(self.allocated)

    def test_Allocated(self):
        self.assertEquals(self.allocated, self.tested.allocated())

    def test_Free(self):
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.validateDeathResult()

    def test_CantFreeDeadAllocation(self):
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.assertRaises(Exception, self.tested.free)
        self.validateDeathResult()

    def test_Withdraw(self):
        self.tested.withdraw("Don't want this allocation anymore")
        self.assertEquals(self.tested.dead(), "withdrawn")
        self.validateDeathResult()

    def test_HeartBeatWhenDeadDoesNothing(self):
        self.assertIsNotNone(self.currentTimer)
        self.tested.free()
        self.assertIsNone(self.currentTimer)
        self.tested.heartbeat()
        self.assertIsNone(self.currentTimer)
        self.validateDeathResult()

    def test_NotDeadForAWhileIfNotDead(self):
        self.assertFalse(self.tested.deadForAWhile())

    def test_NoCrashWhenGotMoreThanOneInaugurationDoneForSameMachine(self):
        self.fakeInaugurationDoneForAll()
        self.fakeInaugurationDoneForAll()
        self.fakeInaugurationDoneForAll()
        self.fakeInaugurationDoneForAll()
        self.fakeInaugurationDoneForAll()

    def test_DeadForAWhile(self):
        self.tested.free()
        executeCodeWhileAllocationIsDeadOfHeartbeatTimeout(self.tested, lambda: None)

    def test_NotDeadForAWhile(self):
        orig_time = time.time
        self.tested.free()
        timeInWhichAllocationIsDeadNotForAWhile = \
            time.time() + self.tested._LIMBO_AFTER_DEATH_DURATION * 0.9
        try:
            time.time = mock.Mock(return_value=timeInWhichAllocationIsDeadNotForAWhile)
            self.assertFalse(self.tested.deadForAWhile())
        finally:
            time.time = orig_time

    def test_HeartBeatTimeout(self):
        self.currentTimer()
        self.assertEquals(self.tested.dead(), "heartbeat timeout")
        self.validateDeathResult()

    def test_DieUponSelfDestructionOfMachine(self):
        self.destroyMachineByName('node0')
        self.assertIn("Unable to inaugurate ", self.tested.dead())
        self.validateDeathResult()

    def test_NoCrashIfAllocationFindsOutAboutDestroyedStateMachineWithoutDestroyedCallback(self):
        self.destroyMachineByName('node0', forgetCallback=True)
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.validateDeathResult()

    def test_NoCrashIfStateMachineSelfDestructedWhileAllocationIsDead(self):
        machine = self.allocated['node0']
        destroyCallback = machine._destroyCallback
        stateChangeCallback = self.allocated['node0']._destroyCallback
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.validateDeathResult()
        machine.setDestroyCallback(destroyCallback)
        self.destroyMachineByName('node0')
        machine.setDestroyCallback(None)
        self.freepool.takeOut(machine)
        # todo: fix the following (which is a bug); The state machine should unassign in case it deetroys
        # itself.
        machine.assign(stateChangeCallback, None, None)
        self.validateDeathResult()

    def test_DetachHost(self):
        machine = self.allocated['node0']
        self.tested.detachHost(machine)
        self.assertNotIn(machine, self.tested.allocated().values())

    def test_DetachHostAfterDestroyed(self):
        machine = self.allocated['node0']
        self.destroyMachineByName('node0')
        self.validateDeathResult()
        self.tested.detachHost(machine)
        self.assertNotIn(machine, self.tested.allocated().values())

    def test_DetachHostAfterInaugurated(self):
        machine = self.allocated['node0']
        self.fakeInaugurationDoneForAll()
        self.tested.detachHost(machine)
        self.assertNotIn(machine, self.tested.allocated().values())

    def test_DetachHostAfterInauguratedAndDestroyed(self):
        machine = self.allocated['node0']
        self.fakeInaugurationDoneForAll()
        self.assertIn(machine, self.tested.allocated().values())
        self.destroyMachineByName('node0')
        self.assertNotIn(machine, self.tested.allocated().values())
        self.tested.detachHost(machine)
        self.assertNotIn(machine, self.tested.allocated().values())
        self.expectedAllocatedAtTheEnd.clear()
        self.validateDeathResult()

    def test_DestroyHostAfterDetached(self):
        machine = self.allocated['node0']
        self.tested.detachHost(machine)
        self.assertNotIn(machine, self.tested.allocated().values())
        self.destroyMachineByName('node0')
        self.validateDeathResult()

    def fakeInaugurationDoneForAll(self):
        for stateMachine in self.expectedAllocatedAtTheEnd.values():
            stateMachine.fakeInaugurationDone()

    def scheduleTimerIn(self, timeout, callback, tag):
        self.assertIs(self.currentTimer, None)
        self.assertIs(self.currentTimerTag, None)
        self.currentTimer = callback
        self.currentTimerTag = tag

    def cancelAllTimersByTag(self, tag):
        if self.currentTimerTag is not None:
            self.assertIsNot(self.currentTimer, None)
            self.assertIs(self.currentTimerTag, tag)
        self.currentTimer = None
        self.currentTimerTag = None

    def validateDeathResult(self):
        self.assertEquals(self.expectedAllocatedAtTheEnd, self.allocated)
        freePoolStateMachines = list(self.freepool.all())
        for stateMachine in self.allocated.values():
            if stateMachine.isDestroyed():
                self.assertNotIn(stateMachine, freePoolStateMachines)
                self.assertTrue(stateMachine.isAssigned())
            else:
                self.assertIn(stateMachine, freePoolStateMachines)
                self.assertFalse(stateMachine.isAssigned())
        self.validateAllocationResourcesAreDeallocated(self.index)

    def validateAllocationResourcesAreDeallocated(self, allocationID):
        self.assertIn(self.index, self.broadcaster.removedExchanges)
        self.assertNotIn(allocationID, self.broadcaster.declaredExchanges)

    def destroyMachineByName(self, name, forgetCallback=False):
        self.originalAllocated[name].destroy(forgetCallback=forgetCallback)
        if not forgetCallback:
            self.expectedAllocatedAtTheEnd.pop(name)


if __name__ == '__main__':
    unittest.main()
