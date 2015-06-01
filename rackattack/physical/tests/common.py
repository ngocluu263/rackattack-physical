from rackattack import api


class HostStateMachine:
    def __init__(self, name):
        self.name = name

    def hostImplementation(self):
        return Host(self.name)


class Host:
    def __init__(self, name):
        self.name = name

    def fulfillsRequirement(self, requirement):
        return True


class FreePool:
    def __init__(self):
        self.pool = []

    def all(self):
        return self.pool

    def takeOut(self, stateMachine):
        self.pool.remove(stateMachine)


class Allocation:
    def __init__(self, freePool, nice):
        self._allocationInfo = api.AllocationInfo(user='test', purpose='user', nice=nice).__dict__
        self.freePool = freePool
        self.allocatedHosts = []

    def withdraw(self, ignoredMessage):
        self.freePool.pool += self.allocatedHosts
        self.allocatedHosts = None

    def allocated(self):
        return {str(x): x for x in self.allocatedHosts}

    def allocationInfo(self):
        return self._allocationInfo



