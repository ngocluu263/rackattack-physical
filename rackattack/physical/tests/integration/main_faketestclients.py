import yaml
import time
import random
import threading
import subprocess
from rackattack.physical import pikapatch
from rackattack import clientfactory
from rackattack.physical import config
from rackattack.api import Requirement, AllocationInfo
from rackattack.physical.tests.integration.main import useFakeGeneralConfiguration

import pika
assert "egg" in pika.__file__


class RackattackTestClients(threading.Thread):
    SCENARIOS = dict(few=(1, 4), moreThanFew=(5, 9),  many=(10, 30))
    SCENARIOS_PROBABILITIES = dict(few=0.7, moreThanFew=0.2, many=0.1)

    def __init__(self, nodeBaseName="node"):
        assert(sum(self.SCENARIOS_PROBABILITIES.values()) == 1)
        super(RackattackTestClients, self).__init__()
        self._nodeBaseName = nodeBaseName
        self._client = clientfactory.factory()
        with open(config.CONFIGURATION_FILE) as f:
            conf = yaml.load(f.read())
        self._osmosisServerIP = conf["OSMOSIS_SERVER_IP"]
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
        cmd = "osmosis listlabels --objectStores=%(osmosisServerIP)s:1010 star | head -n 1" % \
            dict(osmosisServerIP=self._osmosisServerIP)
        print "Running %(cmd)s" % dict(cmd=cmd)
        labelName = subprocess.check_output(cmd, shell=True)
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

    def _generateRequirements(self, nrHosts, pool):
        requirements = dict([("{}{}".format(self._nodeBaseName, nodeIdx),
                              Requirement(imageLabel=self._label,
                                          imageHint=self._label,
                                          hardwareConstraints=None,
                                          pool=pool))
                             for nodeIdx in xrange(nrHosts)])
        return requirements

    def _generateAllocationInfo(self):
        allocationInfo = AllocationInfo(user="johabab", purpose="loadTests")
        return allocationInfo

    def allocate(self, nrHosts, pool="default"):
        self._updateNrAllocatedHosts()
        self._allocate(nrHosts, pool)

    def _allocateForBackground(self):
        nrHosts = self._getRandomNrHosts()
        self._allocate(nrHosts)

    def _allocate(self, nrHostsToAllocate, pool="default"):
        requirements = self._generateRequirements(nrHostsToAllocate, pool=pool)
        allocationInfo = self._generateAllocationInfo()
        print "Trying to allocate %(nrHosts)s hosts from %(pool)s" % dict(nrHosts=len(requirements),
                                                                          pool=pool)
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


def bgStress(mode):
    if mode == "on":
        print "Starting test clients..."
        backgroundStressTestClient.start()
    elif mode == "off":
        print "Stopping test clients..."
        backgroundStressTestClient.stop()


def allocate(nrHosts, pool="default"):
    nrHosts = int(nrHosts)
    profilingTestClient.allocate(nrHosts, pool=pool)
    profilingAllocation = True


def free():
    profilingTestClient.free()


def main():
    print """Available commands:
        bgstress on/off
        \tRuns allocations (and frees them) in the background.
        allocate nrHosts [pool=default]
        \tAllocates the given number of hosts from the given pool.
        free
        \tFrees the current allocation (which was created with the 'allocate' command, if such allocation
        exists."""
    useFakeGeneralConfiguration()
    import pdb
    pdb.set_trace()
    global backgroundStressTestClient, profilingTestClient, profilingAllocation
    backgroundStressTestClient = RackattackTestClients("background-stress")
    profilingTestClient = RackattackTestClients("profiling")
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
