import time
import mock
import unittest
from rackattack.virtual import sh
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical.alloc import allocation
from rackattack.physical.alloc.allocations import Allocations
from rackattack.physical.tests.common import (Host, HostStateMachine, FreePool, Hosts, FreePool,
                                              executeCodeWhileAllocationIsDeadOfHeartbeatTimeout)


def osmosisListLabelsFoundMock(cmd):
    if cmd[0:2] == ['osmosis', 'listlabels']:
        return cmd[2]
    raise ValueError("Implement me")


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self.broadcaster = mock.Mock()
        hostNames = ["alpha", "bravo", "charlie", "delta"]
        self.hosts = Hosts()
        self.freePool = FreePool(self.hosts)
        self.osmosisServer = 'what-a-cool-osmosis-server'
        self.allocationInfo = dict(purpose='forfun', nice=0)
        timer.scheduleIn = mock.Mock()
        timer.cancelAllByTag = mock.Mock()
        self.currentTimer = None
        self.currentTimerTag = None
        for hostName in hostNames:
            stateMachine = HostStateMachine(Host(hostName))
            self.hosts.add(stateMachine)
            self.freePool.put(stateMachine)
        self.tested = Allocations(self.broadcaster, self.hosts, self.freePool, self.osmosisServer)
        self.requirements = dict(node0=dict(imageLabel="echo-foxtrot", imageHint="golf"),
                                 node1=dict(imageLabel="hotel-india", imageHint="juliet"))

    def tearDown(self):
        globallock._lock.release()

    def test_Create(self):
        _allocation = self.createAllocation(self.requirements, self.allocationInfo)
        self.assertEquals(_allocation, self.tested.byIndex(_allocation.index()))
        self.assertEquals(self.allocationInfo, _allocation.allocationInfo())

    def test_AllocationCreationFails(self):
        origAllocation = allocation.Allocation
        try:
            allocation.Allocation = mock.Mock(side_effect=ValueError("don't wanna"))
            self.assertRaises(ValueError, self.createAllocation, self.requirements, self.allocationInfo)
        finally:
            allocation.Allocation = origAllocation

    def test_NoSuchAllocation(self):
        self.assertRaises(IndexError, self.tested.byIndex, 1)

    def test_OsmosisListLabelsReturnsAnotherLabel(self):
        abused = False

        def anotherLabelMock(cmd):
            if cmd[0:2] == ['osmosis', 'listlabels']:
                return cmd[2] + "_not"
            abused = True
        self.assertRaises(Exception, self.createAllocation, self.requirements, self.allocationInfo,
                          listLabelsMock=anotherLabelMock)
        self.assertFalse(abused)

    def test_CreateCleansUp(self):
        _allocation = self.createAllocation(self.requirements, self.allocationInfo)
        _allocation.free()
        createCallback = lambda: self.createAllocation(self.requirements, self.allocationInfo)
        executeCodeWhileAllocationIsDeadOfHeartbeatTimeout(_allocation, createCallback)
        self.assertNotIn(_allocation, self.tested.all())

    def test_byIndexCleansUp(self):
        _allocation = self.createAllocation(self.requirements, self.allocationInfo)
        _allocation.free()
        idx = _allocation.index()
        self.assertRaises(IndexError, executeCodeWhileAllocationIsDeadOfHeartbeatTimeout, _allocation,
                          lambda: self.tested.byIndex(idx))

    def test_AllCleansUp(self):
        _allocation = self.createAllocation(self.requirements, self.allocationInfo)
        _allocation.free()

        def validateNotInAll():
            self.assertNotIn(_allocation, self.tested.all())
        executeCodeWhileAllocationIsDeadOfHeartbeatTimeout(_allocation, validateNotInAll)

    def test_All(self):
        _allocation = self.createAllocation(self.requirements, self.allocationInfo)
        self.assertEquals(self.tested.all(), [_allocation])

    def createAllocation(self, requirements, allocationInfo, listLabelsMock=osmosisListLabelsFoundMock):
        origRun = sh.run
        nrFreeHostsBefore = len(self.freePool.all())
        try:
            sh.run = listLabelsMock
            _allocation = self.tested.create(requirements, self.allocationInfo)
        finally:
            sh.run = origRun
        self.assertEquals(len(self.freePool.all()), nrFreeHostsBefore - len(requirements))
        return _allocation


if __name__ == '__main__':
    unittest.main()
