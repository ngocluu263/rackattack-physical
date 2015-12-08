import collections


Host = collections.namedtuple('Host', 'stateMachine allocation')


class OutOfResourcesError(Exception):
    pass


class Priority:
    _NICE = {'user': (0, 1), 'racktest': (0.2, 1.2), 'dirbalak': (0.1, 1.1), 'default': (1, 2)}

    def __init__(self, requirements, allocationInfo, freePool, allocations):
        assert len(requirements) > 0
        self._requirements = requirements
        self._allocationInfo = allocationInfo
        self._freePool = freePool
        self._allocations = allocations
        self._allocated = self._allocate()

    def allocated(self):
        return self._allocated

    def _absoluteNice(self, allocationInfo):
        range = self._NICE.get(allocationInfo['purpose'], self._NICE['default'])
        return (range[1] - range[0]) * allocationInfo['nice'] + range[0]

    def _allocationsSortedByAscendingAge(self):
        allocationsFromOldestToYoungest = list(self._allocations)
        allocationsFromYoungestToOldest = reversed(allocationsFromOldestToYoungest)
        return allocationsFromYoungestToOldest

    def _allocationsStableSortedByDescendingNice(self, allocations):
        allocations = list(allocations)
        allocations.sort(key=lambda x: -self._absoluteNice(x.allocationInfo()))
        return allocations

    def _freeAndNicer(self):
        result = [Host(s, None) for s in self._freePool.all()]
        myNice = self._absoluteNice(self._allocationInfo)
        allocationsFromYoungestToOldest = self._allocationsSortedByAscendingAge()
        nicerAllocationsFromYoungestToOldest = \
            [allocation for allocation in allocationsFromYoungestToOldest if
             self._absoluteNice(allocation.allocationInfo()) > myNice]
        nicerAllocationsSortedByDescendingNiceAndByAscendingAge = \
            self._allocationsStableSortedByDescendingNice(nicerAllocationsFromYoungestToOldest)
        for allocation in nicerAllocationsSortedByDescendingNiceAndByAscendingAge:
            result += [Host(s, allocation) for s in allocation.allocated().values()]
        return result

    def _allocate(self):
        freeAndNicer = self._freeAndNicer()
        allocated = []
        for name, requirement in self._requirements.iteritems():
            fulfilled = False
            for host in freeAndNicer:
                if host.stateMachine.hostImplementation().fulfillsRequirement(requirement):
                    allocated.append((name, host))
                    freeAndNicer.remove(host)
                    fulfilled = True
                    break
            if not fulfilled:
                raise OutOfResourcesError(
                    "Not enough machines free or busy doing lower priority tasks to allocate "
                    "requested machines")
        self._withdrawExistingAllocations(allocated)
        self._takeOutOfFreePool(allocated)
        return {name: h.stateMachine for name, h in allocated}

    def _withdrawExistingAllocations(self, allocated):
        toWithdraw = set([h[1].allocation for h in allocated if h[1].allocation is not None])
        for allocation in toWithdraw:
            allocation.withdraw("An allocation with higher priority needs resources")

    def _takeOutOfFreePool(self, allocated):
        for name, host in allocated:
            self._freePool.takeOut(host.stateMachine)
