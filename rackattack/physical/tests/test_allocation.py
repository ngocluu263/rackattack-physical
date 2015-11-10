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
        allocated = dict((hostName, HostStateMachine(Host(hostName)))
                         for hostName in requirements.keys())
        self.originalAllocated = copy.copy(allocated)
        self.expectedStates = dict(allocatedButNotInaugurated=set(allocated.values()),
                                   inaugurated=set())
        self.expectedDestroyed = set()
        self.expectedDetached = set()
        self.expectedReleased = set()
        self.broadcaster = Publish()
        self.hosts = Hosts()
        self.freepool = FreePool(self.hosts)
        for stateMachine in allocated.values():
            self.hosts.add(stateMachine)
        self.tested = allocation.Allocation(self.index, requirements, self.allocationInfo, allocated,
                                            self.broadcaster, self.freepool, self.hosts)

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
        expected = {stateMachine.hostImplementation().id(): stateMachine for stateMachine in
                    self.expectedStates["inaugurated"]}
        self.assertEquals(expected, self.tested.inaugurated())

    def test_Allocated(self):
        self.assertEquals(self.originalAllocated, self.tested.allocated())

    def test_Free(self):
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.validate()

    def test_CantFreeDeadAllocation(self):
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.assertRaises(Exception, self.tested.free)
        self.validate()

    def test_Withdraw(self):
        self.tested.withdraw("Don't want this allocation anymore")
        self.assertEquals(self.tested.dead(), "withdrawn")
        self.validate()

    def test_HeartBeatWhenDeadDoesNothing(self):
        self.assertIsNotNone(self.currentTimer)
        self.tested.free()
        self.assertIsNone(self.currentTimer)
        self.tested.heartbeat()
        self.assertIsNone(self.currentTimer)
        self.validate()

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
        self.validate()

    def test_DieUponSelfDestructionOfMachine(self):
        self.destroyMachineByName('node0')
        self.assertIn("Unable to inaugurate ", self.tested.dead())
        self.validate()

    def test_NoCrashIfStateMachineSelfDestructedWhileAllocationIsDead(self):
        machine = self.originalAllocated['node0']
        destroyCallback = machine._destroyCallback
        stateChangeCallback = self.originalAllocated['node0']._destroyCallback
        self.tested.free()
        self.assertEquals(self.tested.dead(), "freed")
        self.validate()
        machine.setDestroyCallback(destroyCallback)
        self.destroyMachineByName('node0')
        machine.setDestroyCallback(None)
        self.freepool.takeOut(machine)
        # todo: fix the following (which is a bug); The state machine should unassign in case it deetroys
        # itself.
        machine.assign(stateChangeCallback, None, None)
        self.validate()

    def test_DetachHostBeforeInaugurated(self):
        machine = self.originalAllocated['node0']
        self.detachHost(machine)
        self.validate()
        self.fakeInaugurationDoneForAll()
        self.validate()

    def test_DetachHostAfterInaugurated(self):
        machine = self.originalAllocated['node0']
        self.fakeInaugurationDoneForAll()
        self.validate()
        self.detachHost(machine)
        self.validate()

    def test_CannotDetachHostAfterDestroyed(self):
        machine = self.originalAllocated['node0']
        self.destroyMachineByName('node0')
        self.validate()
        self.assertRaises(Exception, self.tested.detachHost, machine)
        self.validate()

    def test_CannotDetachHostAfterInauguratedAndDestroyed(self):
        machine = self.originalAllocated['node0']
        self.fakeInaugurationDoneForAll()
        self.assertIn(machine, self.tested.allocated().values())
        self.destroyMachineByName('node0')
        self.validate()
        self.assertRaises(Exception, self.tested.detachHost, machine)
        self.validate()

    def test_CannotDetachUnAllocatedHost(self):
        machine = HostStateMachine("whatIsThisMachine")
        self.assertRaises(Exception, self.detachHost, machine)

    def test_DetachingLastHostKillsAllocation(self):
        for machine in self.originalAllocated.values():
            self.detachHost(machine)
            self.validate()
        isDead = self.tested.dead() is not None
        self.assertTrue(isDead)

    def test_ReleaseHostBeforeInaugurated(self):
        machine = self.originalAllocated['node0']
        self.releaseHost(machine)
        self.validate()
        self.fakeInaugurationDoneForAll()
        self.validate()

    def fakeInaugurationDoneForAll(self):
        collection = self.expectedStates["allocatedButNotInaugurated"]
        while collection:
            stateMachine = collection.pop()
            stateMachine.fakeInaugurationDone()
            self.expectedStates["inaugurated"].add(stateMachine)

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

    def _validateFreePool(self):
        isDead = self.tested.dead() is not None
        expectedHostsInFreePool = set()
        if isDead:
            expectedHostsInFreePool = self.expectedStates["allocatedButNotInaugurated"].union(
                self.expectedStates["inaugurated"]).union(self.expectedReleased)
        else:
            expectedHostsInFreePool = self.expectedReleased 
        expectedHostsInFreePool = [host for host in expectedHostsInFreePool if host not in \
                                   self.expectedDestroyed and host not in self.expectedDetached]
        for stateMachine in expectedHostsInFreePool:
            self.assertIn(stateMachine, self.freepool.all())
        expectedHostsNotInFreePool = [stateMachine for stateMachine in self.originalAllocated.values() if
                                      stateMachine not in expectedHostsInFreePool]
        for stateMachine in expectedHostsNotInFreePool:
            self.assertNotIn(stateMachine, self.freepool.all())

    def _validateAllocated(self):
        actual = self.tested.allocated()
        expected = self.expectedStates["allocatedButNotInaugurated"]
        isDead = self.tested.dead() is not None
        if not isDead:
            expected = expected.union(self.expectedStates["inaugurated"])
        expected = {stateMachine.hostImplementation().id(): stateMachine for stateMachine in expected
                    if stateMachine not in self.expectedDetached}
        self.assertEquals(expected, actual)

    def _validateInaugurated(self):
        isDead = self.tested.dead() is not None
        if isDead:
            self.assertRaises(AssertionError, self.tested.inaugurated)
        else:
            if self.tested.done():
                expected = {stateMachine.hostImplementation().id(): stateMachine for stateMachine in
                            self.expectedStates["inaugurated"] if stateMachine not in self.expectedDetached}
                self.assertEquals(self.tested.inaugurated(), expected)
            else:
                self.assertRaises(AssertionError, self.tested.inaugurated)

    def validateAllocationResourcesAreDeallocated(self):
        self.assertIn(self.index, self.broadcaster.removedExchanges)
        self.assertNotIn(self.tested.index(), self.broadcaster.declaredExchanges)

    def _validateDone(self):
        isDead = self.tested.dead() is not None
        if isDead:
            self.assertRaises(AssertionError, self.tested.done)
        else:
            allowedNotToBeInaugurated = self.expectedDetached
            expected = \
                self.expectedStates["allocatedButNotInaugurated"].issubset(allowedNotToBeInaugurated)
            actual = self.tested.done()
            self.assertEquals(expected, actual)

    def _validateHosts(self):
        hosts = self.hosts.all()
        for host in self.expectedDestroyed:
            self.assertNotIn(host, hosts)
        for host in self.expectedDetached:
            self.assertNotIn(host, hosts)

    def validateAllocationIsNotEmpty(self):
        self.assertTrue(self.tested.allocated())

    def validate(self):
        self._validateAllocated()
        self._validateInaugurated()
        self._validateFreePool()
        self._validateHosts()
        self._validateDone()
        isDead = self.tested.dead() is not None
        if isDead:
            self.validateAllocationResourcesAreDeallocated()
        else:
            self.validateAllocationIsNotEmpty()

    def destroyMachineByName(self, name):
        stateMachine = self.originalAllocated[name]
        stateMachine.destroy()
        self.expectedDestroyed.add(stateMachine)

    def detachHost(self, machine):
        self.tested.detachHost(machine)
        self.expectedDetached.add(machine)

    def releaseHost(self, machine):
        self.tested.releaseHost(machine)
        self.expectedReleased.add(machine)
        for collection in self.expectedStates.values():
            if machine in collection:
                collection.remove(machine)

if __name__ == '__main__':
    unittest.main()
