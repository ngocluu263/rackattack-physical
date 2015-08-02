import os
import sys
import time
import random
import threading
import subprocess
from rackattack.physical import pikapatch
from rackattack import clientfactory
from rackattack.api import Requirement, AllocationInfo

import pika
assert "egg" in pika.__file__


class RackattackTestClients(threading.Thread):
    SCENARIOS = dict(few=(1, 4), moreThanFew=(5, 9),  many=(10, 30))
    SCENARIOS_PROBABILITIES = dict(few=0.7, moreThanFew=0.2, many=0.1)

    def __init__(self):
        assert(sum(self.SCENARIOS_PROBABILITIES.values()) == 1)
        super(RackattackTestClients, self).__init__()
        self._client = clientfactory.factory()
        self._label = self._generateLabelName()
        self._nrHosts = self._getNrHosts()
        self._nrAllocatedHosts = 0
        self._profiledAllocation = None
        self._allocations = set()
        self._stop = False

    def run(self):
        while True:
            if self._stop:
                while self._allocations:
                    allocation = self._allocations.pop()
                    allocation.free()
                return
            self._updateNrAllocatedHosts()
            if self._nrAllocatedHosts == self._nrHosts:
                self._free()
            elif not self._allocations:
                self._allocateForBackground()
            elif self._nrAllocatedHosts <= self._nrHosts:
                self._performRandomLoadAction()
            else:
                assert(False)
            interval = 0.5 + random.random() * 1.2
            time.sleep(interval)

    def stop(self):
        self._stop = True

    def _updateNrAllocatedHosts(self):
        stillAlive = set()
        self._nrAllocatedHosts = 0
        for allocation in self._allocations:
            if allocation.dead() is None:
                self._nrAllocatedHosts += len(allocation._requirements)
                stillAlive.add(allocation)
        self._allocations = stillAlive

    def _generateLabelName(self):
        labelName = subprocess.check_output("osmosis listlabels --objectStores=oberon:1010 "
                                            "star | head -n 1", shell=True)
        labelName = labelName.strip()
        return labelName

    def _performRandomLoadAction(self):
        wantedAllocationRatio = 0.65
        allocationRatio = self._nrAllocatedHosts / float(self._nrHosts)
        print "allocationRatio: {}, nrAllocated: {}, nrHosts: {}".format(allocationRatio,
                                                                         self._nrAllocatedHosts,
                                                                         self._nrHosts)
        if allocationRatio < wantedAllocationRatio:
            print "Will most likeliy allocate now..."
            majorityAction = self._allocateForBackground
            minorityAction = self._free
        else:
            print "Reached the wanted ratio..."
            time.sleep(0.5)
            print "Will most likeliy free now..."
            majorityAction = self._free
            minorityAction = self._allocateForBackground
        withinWhatRange = random.random()
        if withinWhatRange < 0.9:
            majorityAction()
        else:
            minorityAction()

    def _generateRequirements(self, nrHosts, forProfiling=False):
        if forProfiling:
            nodeNameBase = "profile"
        else:
            nodeNameBase = "node"
        requirements = dict([("{}{}".format(nodeNameBase, nodeIdx),
                              Requirement(imageLabel=self._label,
                                          imageHint=self._label,
                                          hardwareConstraints=None))
                             for nodeIdx in xrange(nrHosts)])
        return requirements

    def _generateAllocationInfo(self):
        allocationInfo = AllocationInfo(user="johabab", purpose="loadTests")
        return allocationInfo

    def allocateForProfiling(self, nrHosts):
        self._updateNrAllocatedHosts()
        self._allocate(nrHosts, forProfiling=True)

    def _allocateForBackground(self):
        nrHosts = self._getRandomNrHosts()
        self._allocate(nrHosts)

    def _allocate(self, nrHostsToAllocate, forProfiling=False):
        requirements = self._generateRequirements(nrHostsToAllocate, forProfiling=forProfiling)
        allocationInfo = self._generateAllocationInfo()
        print "Trying to allocate %(nrHosts)s hosts" % dict(nrHosts=len(requirements))
        allocation = None
        try:
            allocation = self._client.allocate(requirements, allocationInfo)
            self._allocations.add(allocation)
            print "Allocation succeeded"
        except Exception as e:
            if 'not enough machines' in str(e):
                print "Allocation failed: not enough machines"
            else:
                print str(e)
        return allocation

    def _getRandomNrHosts(self):
        scenarioNames = self.SCENARIOS.keys()
        scenarioNames.sort()
        withinWhichRange = random.random()
        rangeBound = 0
        chosenScenarioName = None
        for scenarioName in scenarioNames:
            rangeBound += self.SCENARIOS_PROBABILITIES[scenarioName]
            if withinWhichRange <= rangeBound:
                chosenScenarioName = scenarioName
                break
        assert chosenScenarioName is not None
        nrHosts = random.randint(*self.SCENARIOS[chosenScenarioName])
        return nrHosts

    def free(self):
        self._updateNrAllocatedHosts()
        self._free()

    def _free(self):
        allocation = self._allocations.pop()
        print "Trying to free an allocation..."
        try:
            allocation.free()
        except Exception as e:
            print "Failed freeing allocation: {}".format(str(e))
        print "Allocation freed."

    def _getNrHosts(self):
        status = self._client.call("admin__queryStatus")
        return len(status["hosts"])


backgroundStressTestClient = None
profilingTestClient = None
client = None
profilingAllocation = False


def bgStress(mode):
    if mode == "on":
        print "Starting test clients..."
        backgroundStressTestClient.start()
    elif mode == "off":
        print "Stopping test clients..."
        backgroundStressTestClient.stop()


def allocate(nrHosts):
    global profilingAllocation
    if profilingAllocation:
        print "An allocation already exists."
    else:
        nrHosts = int(nrHosts)
        profilingTestClient.allocateForProfiling(nrHosts)
        profilingAllocation = True


def free():
    global profilingAllocation
    if profilingAllocation:
        profilingTestClient.free()
        profilingAllocation = False
    else:
        print "An allocation for profiling does not exist."


def main():
    print """Available commands:
        bgstress <on/off>
        \tRuns allocations (and frees them) in the background.
        allocate <nrHosts>
        \tAllocates the given number of hosts (up to 1 allocations concurrently).
        free
        \tFrees the current allocation (which was created with the 'allocate' command, if such allocation
        exists."""
    import pdb
    pdb.set_trace()
    global backgroundStressTestClient, profilingTestClient, client, profilingAllocation
    backgroundStressTestClient = RackattackTestClients()
    profilingTestClient = RackattackTestClients()
    client = clientfactory.factory()
    profilingAllocation = False
    commands = dict(bgstress=bgStress, allocate=allocate, free=free)
    while True:
        cmdline = raw_input()
        cmdline = cmdline.strip()
        if not cmdline:
            continue
        cmdline = cmdline.split(" ")
        cmdline = [item.strip() for item in cmdline]
        commandName = cmdline[0]
        args = cmdline[1:]
        if commandName not in commands:
            print "Invalid command: %(commandName)s" % dict(commandName=commandName)
            continue
        command = commands[commandName]
        try:
            command(*args)
        except Exception as e:
            print "An error has occurred while executing command: %(message)s" % dict(message=e.message)
            continue

if __name__ == '__main__':
    main()
