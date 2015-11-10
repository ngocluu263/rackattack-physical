import time
import mock
import pika
from rackattack import api
from rackattack.common import hoststatemachine


class HostStateMachine:
    def __init__(self, hostImplementation, *args, **kwargs):
        self._hostImplementation = hostImplementation
        self._destroyCallback = None
        self._state = hoststatemachine.STATE_CHECKED_IN
        self._stateChangeCallback = None
        self._imageLabel = None
        self._imageHint = None

    def hostImplementation(self):
        return self._hostImplementation

    def setDestroyCallback(self, callback):
        self._destroyCallback = callback

    def destroy(self):
        self._state = hoststatemachine.STATE_DESTROYED
        self._destroyCallback(self)

    def isDestroyed(self):
        return self._state == hoststatemachine.STATE_DESTROYED

    def state(self):
        return self._state

    def assign(self, stateChangeCallback, imageLabel, imageHint):
        self._stateChangeCallback = stateChangeCallback
        self._imageLabel = imageLabel
        self._imageHint = imageHint

    def unassign(self):
        self._stateChangeCallback = None

    def isAssigned(self):
        return self._stateChangeCallback is not None

    def fakeInaugurationDone(self):
        self._state = hoststatemachine.STATE_INAUGURATION_DONE
        if self._stateChangeCallback is not None:
            self._stateChangeCallback(self)


class Host:
    def __init__(self, id):
        self._id = id

    def id(self):
        return self._id

    def ipAddress(self):
        return "%(id)s's ip address" % dict(id=self.id())

    def fulfillsRequirement(self, requirement):
        return True

    def truncateSerialLog(self):
        pass


class Hosts:
    def __init__(self):
        self._stateMachines = []

    def destroy(self, stateMachine):
        self._stateMachines.remove(stateMachine)

    def add(self, stateMachine):
        self._stateMachines.append(stateMachine)

    def all(self):
        return self._stateMachines


class FreePool:
    def __init__(self, hosts=None):
        self._pool = []
        self._hosts = hosts

    def all(self):
        return self._pool

    def takeOut(self, stateMachine):
        self._pool.remove(stateMachine)

    def put(self, hostStateMachine):
        self._pool.append(hostStateMachine)
        hostStateMachine.setDestroyCallback(self._hostSelfDestructed)

    def _hostSelfDestructed(self, hostStateMachine):
        self._hosts.destroy(hostStateMachine)
        self._pool.remove(hostStateMachine)


class Allocation:
    def __init__(self, allocated, freePool, hosts, nice):
        self._allocationInfo = api.AllocationInfo(user='test', purpose='user', nice=nice).__dict__
        self.freePool = freePool
        self.hosts = hosts
        self.allocatedHosts = list()
        for hostStateMachine in allocated:
            self.allocatedHosts.append(hostStateMachine)
            hostStateMachine.setDestroyCallback(self._stateMachineSelfDestructed)
        self.isDead = None

    def index(self):
        return 1

    def _die(self, message):
        assert not self.dead()
        while self.allocatedHosts:
            hostStateMachine = self.allocatedHosts.pop()
            if hostStateMachine.state() != hoststatemachine.STATE_DESTROYED:
                self.freePool.put(hostStateMachine)
        self.isDead = message

    def withdraw(self, ignoredMessage):
        self._die(ignoredMessage)

    def dead(self):
        return self.isDead

    def allocated(self):
        return {str(x): x for x in self.allocatedHosts}

    def allocationInfo(self):
        return self._allocationInfo

    def _stateMachineSelfDestructed(self, stateMachine):
        if self.dead() is not None:
            return
        self._die("Unable to inaugurate Host %s" % stateMachine.hostImplementation().id())
        self.hosts.destroy(stateMachine)


class Allocations:
    def __init__(self, **kwargs):
        self.allocations = []

    def all(self):
        return self.allocations


def executeCodeWhileAllocationIsDeadOfHeartbeatTimeout(_allocation, callback):
    orig_time = time.time
    timeInWhichAllocationIsDeadForAWhile = time.time() + _allocation._LIMBO_AFTER_DEATH_DURATION + 1
    try:
        time.time = mock.Mock(return_value=timeInWhichAllocationIsDeadForAWhile)
        assert _allocation.deadForAWhile()
        callback()
    finally:
        time.time = orig_time


class Publish:
    def __init__(self):
        self.removedExchanges = set()
        self.declaredExchanges = set()

    def allocationChangedState(self, allocationID):
        assert allocationID not in self.removedExchanges
        self.declaredExchanges.add(allocationID)

    def cleanupAllocationPublishResources(self, allocationID):
        self.declaredExchanges.remove(allocationID)
        self.removedExchanges.add(allocationID)

    def allocationProviderMessage(self, allocationID, message):
        assert allocationID not in self.removedExchanges
        self.declaredExchanges.add(allocationID)

    def allocationWithdraw(self, allocationID, message):
        assert allocationID not in self.removedExchanges
        self.declaredExchanges.add(allocationID)

    def allocationRequested(self, requirements, allocationInfo):
        pass

    def allocationCreated(self, allocationID, requirements, allocationInfo, allocated):
        pass
