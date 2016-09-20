import time
import mock
import pika
from rackattack import api
from rackattack.tcp import publish
from rackattack.common import timer
from rackattack.common import hoststatemachine
from rackattack.physical.alloc import allocation


class HostStateMachine:
    def __init__(self, hostImplementation, *args, **kwargs):
        self._hostImplementation = hostImplementation
        self._destroyCallback = None
        self._state = hoststatemachine.STATE_CHECKED_IN
        self.stateChangeCallback = None
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
        self.stateChangeCallback = stateChangeCallback
        self._imageLabel = imageLabel
        self._imageHint = imageHint

    def unassign(self):
        self.stateChangeCallback = None

    def isAssigned(self):
        return self.stateChangeCallback is not None

    def fakeInaugurationDone(self):
        self._state = hoststatemachine.STATE_INAUGURATION_DONE
        if self.stateChangeCallback is not None:
            self.stateChangeCallback(self)


class Host:
    def __init__(self, id):
        self._id = id

    def id(self):
        return self._id

    def ipAddress(self):
        return "%(id)s's ip address" % dict(id=self.id())

    def fulfillsRequirement(self, requirement):
        return True

    def truncateSerialLogEveryNCalls(self):
        pass

    def primaryMACAddress(self):
        return "fake primary MAC"

    def secondaryMACAddress(self):
        return "fake secondary MAC"

    def getNICBondings(self):
        return ["fake list", "of MAC", "addresses"]

    def getOtherMACAddresses(self):
        return None


class Hosts:
    def __init__(self):
        self._stateMachines = []

    def destroy(self, stateMachine):
        self._stateMachines.remove(stateMachine)

    def add(self, stateMachine):
        self._stateMachines.append(stateMachine)

    def all(self):
        return self._stateMachines


nrAllocations = 0


def Allocation(allocated, freePool, hosts, nice):

    currentTimer = None
    currentTimerTag = None

    def scheduleTimerIn(timeout, callback, tag):
        global currentTimer, currentTimerTag
        assert currentTimer is None
        assert currentTimerTag is tag
        currentTimer = callback
        currentTimerTag = tag

    def cancelAllTimersByTag(tag):
        global currentTimer, currentTimerTag
        if currentTimerTag is not None:
            assert currentTimer is not None
            assert currentTimerTag is tag
        currentTimer = None
        currentTimerTag = None

    def mockTimer():
        timer.scheduleIn = mock.Mock()
        timer.cancelAllByTag = mock.Mock()

    broadcaster = mock.Mock()
    allocatedDict = dict()
    for idx, host in enumerate(allocated):
        allocatedDict["yuvu%d" % (idx)] = host
    requirements = dict()
    for idx, host in enumerate(allocated):
        requirements["yuvu%d" % (idx)] = dict(imageLabel="someLabel", imageHint="someLabel")
    allocationInfo = dict(nice=nice, purpose="user")
    global nrAllocations
    mockTimer()
    fakeAllocation = allocation.Allocation(nrAllocations,
                                           requirements=requirements,
                                           allocationInfo=allocationInfo,
                                           allocated=allocatedDict,
                                           broadcaster=broadcaster,
                                           freePool=freePool,
                                           hosts=hosts)
    nrAllocations += 1
    return fakeAllocation


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


# The autospec invocation is put in the global scope since it is damn slow (few milliseconds...)
fakePublish = mock.create_autospec(publish.Publish)


def Publish():
    fakePublishInstance = fakePublish("amqp://guest:guest@localhost:1234")
    return fakePublish
