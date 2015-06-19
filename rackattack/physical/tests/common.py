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

    def destroy(self, forgetCallback=False):
        self._state = hoststatemachine.STATE_DESTROYED
        if not forgetCallback:
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
    def __init__(self, freePool, nice):
        self._allocationInfo = api.AllocationInfo(user='test', purpose='user', nice=nice).__dict__
        self.freePool = freePool
        self.allocatedHosts = []
        self.isDead = None

    def index(self):
        return 1

    def withdraw(self, ignoredMessage):
        assert not self.dead()
        self.freePool._pool += self.allocatedHosts
        self.allocatedHosts = []
        self.isDead = ignoredMessage

    def dead(self):
        return self.isDead

    def allocated(self):
        return {str(x): x for x in self.allocatedHosts}

    def allocationInfo(self):
        return self._allocationInfo


class Allocations:
    def __init__(self, **kwargs):
        self.allocations = []

    def all(self):
        return self.allocations
