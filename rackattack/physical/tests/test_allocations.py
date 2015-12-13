import time
import mock
import unittest
from rackattack.virtual import sh
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical.alloc import allocation, priority, freepool
from rackattack.physical.alloc.allocations import Allocations
from rackattack.physical.tests.common import (Host, HostStateMachine, Hosts, Publish,
                                              executeCodeWhileAllocationIsDeadOfHeartbeatTimeout)


def osmosisListLabelsFoundMock(cmd):
    if cmd[0:2] == ['osmosis', 'listlabels']:
        return cmd[2]
    raise ValueError("Implement me")


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self.broadcaster = Publish()
        hostNames = ["alpha", "bravo", "charlie", "delta"]
        self.hosts = Hosts()
        self.freePool = freepool.FreePool(self.hosts)
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
        self.expectedCreationBroadcasts = list()
        self.expectedRequestBroadcasts = list()
        self.expectedRejectedBroadcasts = list()

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

        def createCallback():
            self.createAllocation(self.requirements, self.allocationInfo)

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

    def test_RequestBroadcasted(self):
        self.createAllocation(self.requirements, self.allocationInfo)
        self.validateRequestBroadcasts()

    def test_CreationBroadcasted(self):
        self.createAllocation(self.requirements, self.allocationInfo)
        self.validateCreationBroadcasts()

    def test_OutOfResourcesBroadcasted(self):
        tooBigOfRequirements = dict(self.requirements,
                                    node3=dict(imageLabel="kilo-lima", imageHint="mike"),
                                    node4=dict(imageLabel="november-oscar", imageHint="papa"),
                                    node5=dict(imageLabel="quebec-romeo", imageHint="sierra"))
        try:
            self.createAllocation(tooBigOfRequirements, self.allocationInfo, outOfResourcesExpected=True)
        except priority.OutOfResourcesError:
            pass
        self.expectedRejectedBroadcasts.append(dict(reason="noResources"))
        self.validateRejectedBroadcasts()

    def test_OutOfResourcesRaisedWhenOutOfResources(self):
        tooBigOfRequirements = dict(self.requirements,
                                    node3=dict(imageLabel="kilo-lima", imageHint="mike"),
                                    node4=dict(imageLabel="november-oscar", imageHint="papa"),
                                    node5=dict(imageLabel="quebec-romeo", imageHint="sierra"))
        self.assertRaises(priority.OutOfResourcesError,
                          self.createAllocation,
                          tooBigOfRequirements,
                          self.allocationInfo,
                          outOfResourcesExpected=True)

    def test_OutOfResourcesReturnsHostsTooFreePool(self):
        tooBigOfRequirements = dict(self.requirements,
                                    node3=dict(imageLabel="kilo-lima", imageHint="mike"),
                                    node4=dict(imageLabel="november-oscar", imageHint="papa"),
                                    node5=dict(imageLabel="quebec-romeo", imageHint="sierra"))
        nrFreeHostsBefore = len(list(self.freePool.all()))
        self.assertRaises(priority.OutOfResourcesError,
                          self.createAllocation,
                          tooBigOfRequirements,
                          self.allocationInfo,
                          outOfResourcesExpected=True)
        self.assertEquals(len(list(self.freePool.all())), nrFreeHostsBefore)

    def test_AllocationCreationErrorBroadcasted(self):
        origAllocation = allocation.Allocation

        class IgnoreMe(Exception):
            pass

        try:
            allocation.Allocation = mock.Mock(side_effect=IgnoreMe)
            self.createAllocation(self.requirements, self.allocationInfo)
        except IgnoreMe:
            pass
        finally:
            allocation.Allocation = origAllocation
        self.expectedRejectedBroadcasts.append(dict(reason="unknown"))
        self.validateRejectedBroadcasts()

    def test_LabelDoesNotExistInObjectStoreBroadcasted(self):

        def noLabelMock(cmd):
            return ""
        self.assertRaises(Exception, self.createAllocation, self.requirements, self.allocationInfo,
                          listLabelsMock=noLabelMock)
        self.expectedRejectedBroadcasts.append(dict(reason="labelDoesNotExist"))
        self.validateRejectedBroadcasts()

    def createAllocation(self, requirements, allocationInfo, listLabelsMock=osmosisListLabelsFoundMock,
                         outOfResourcesExpected=False):
        origRun = sh.run
        nrFreeHostsBefore = len(list(self.freePool.all()))
        self.expectedRequestBroadcasts.append((requirements, allocationInfo))
        if len(requirements) > len(list(self.freePool.all())):
            self.assertTrue(outOfResourcesExpected)
        try:
            sh.run = listLabelsMock
            _allocation = self.tested.create(requirements, self.allocationInfo)
            self.expectedCreationBroadcasts.append(dict(allocationID=_allocation.index(),
                                                        allocated=_allocation.allocated()))
        except priority.OutOfResourcesError:
            raise
        finally:
            sh.run = origRun
        self.assertEquals(len(list(self.freePool.all())), nrFreeHostsBefore - len(requirements))
        return _allocation

    def validateRequestBroadcasts(self):
        for idx, expectedCall in enumerate(self.expectedRequestBroadcasts):
            actualCall = self.broadcaster.allocationRequested.call_args_list[idx][0]
            self.assertEquals(expectedCall, actualCall)
        self.assertEquals(len(self.expectedRequestBroadcasts),
                          len(self.broadcaster.allocationRequested.call_args_list))

    def validateCreationBroadcasts(self):
        for idx, expectedCall in enumerate(self.expectedCreationBroadcasts):
            actualCall = self.broadcaster.allocationCreated.call_args_list[idx][1]
            self.assertEquals(expectedCall, actualCall)
        self.assertEquals(len(self.expectedCreationBroadcasts),
                          len(self.broadcaster.allocationCreated.call_args_list))

    def validateRejectedBroadcasts(self):
        for idx, expectedCall in enumerate(self.expectedRejectedBroadcasts):
            actualCall = self.broadcaster.allocationRejected.call_args_list[idx][1]
            self.assertEquals(expectedCall, actualCall)
        self.assertEquals(len(self.expectedRejectedBroadcasts),
                          len(self.broadcaster.allocationRejected.call_args_list))

if __name__ == '__main__':
    unittest.main()
