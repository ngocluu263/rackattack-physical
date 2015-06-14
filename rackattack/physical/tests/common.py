from rackattack import api
from rackattack.common import hoststatemachine


class HostStateMachine:
    def __init__(self, hostImplementation, *args, **kwargs):
        self._hostImplementation = hostImplementation
        self.destroyCallback = None
        self._state = hoststatemachine.STATE_CHECKED_IN

    def hostImplementation(self):
        return self._hostImplementation

    def setDestroyCallback(self, callback):
        self.destroyCallback = callback

    def destroy(self):
        self._state = hoststatemachine.STATE_DESTROYED

    def state(self):
        return self._state


class Host:
    def __init__(self, name):
        self.name = name

    def fulfillsRequirement(self, requirement):
        return True


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

    def withdraw(self, ignoredMessage):
        self.freePool._pool += self.allocatedHosts
        self.allocatedHosts = None

    def allocated(self):
        return {str(x): x for x in self.allocatedHosts}

    def allocationInfo(self):
        return self._allocationInfo


class Allocations:
    def __init__(self, **kwargs):
        self.allocations = []

    def all(self):
        return self.allocations
