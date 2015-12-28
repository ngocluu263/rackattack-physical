import mock
import unittest
import threading
from rackattack.common import timer
from rackattack.common import globallock
from rackattack.physical import ipcserver
from rackattack.common import baseipcserver
from rackattack.physical.alloc import freepool
from rackattack.common import reclaimhostspooler
from rackattack.physical.alloc import allocations
from rackattack.physical.tests.common import Hosts, HostStateMachine, Host


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.osmosisServerIP = "some-osmosis-server"
        cls.dnsmasq = mock.Mock()
        cls.broadcaster = mock.Mock()
        cls.hosts = Hosts()
        cls.freePool = freepool.FreePool(cls.hosts)
        allocations.sh.run = cls.osmosisListLabelsFoundMock
        cls.allocations = allocations.Allocations(cls.broadcaster,
                                                  cls.hosts,
                                                  cls.freePool,
                                                  cls.osmosisServerIP)
        cls.dynamicConfig = mock.Mock()
        cls.reclaimHost = mock.Mock(spec=reclaimhostspooler.ReclaimHostSpooler)
        baseipcserver.threading.Thread.daemon = mock.Mock()
        baseipcserver.threading.Event = mock.Mock()
        baseipcserver.threading.Thread.start = mock.Mock()
        timer.scheduleIn = mock.Mock()
        timer.cancelAllByTag = mock.Mock()
        cls.currentTimer = None
        cls.currentTimerTag = None
        globallock._lock.acquire()

    @classmethod
    def tearDownClass(cls):
        globallock._lock.release()

    def setUp(self):
        while self.hosts.all():
            self.hosts.destroy(self.hosts.all()[0])
        hosts = list(self.freePool.all())
        for host in hosts:
            self.freePool.takeOut(host)
        self.hostsIDs = ["alpha", "bravo", "charlie", "delta"]
        for hostName in self.hostsIDs:
            stateMachine = HostStateMachine(Host(hostName))
            self.hosts.add(stateMachine)
            self.freePool.put(stateMachine)
        self.requirements = dict(node0=dict(imageLabel="echo-foxtrot", imageHint="golf"),
                                 node1=dict(imageLabel="hotel-india", imageHint="juliet"))
        self.allocationInfo = dict(purpose="racktest",
                                   user="bob",
                                   nice=0.5)
        self.tested = ipcserver.IPCServer(self.osmosisServerIP,
                                          self.dnsmasq,
                                          self.allocations,
                                          self.hosts,
                                          self.dynamicConfig,
                                          self.reclaimHost)

    def test_Allocate(self):
        allocationID = self.tested.cmd_allocate(self.requirements,
                                                self.allocationInfo,
                                                self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        self.assertEquals(allocationID, allocation.index())

    def test_inauguratorIDs(self):
        self.tested.cmd_allocate(self.requirements, self.allocationInfo, self.osmosisServerIP)
        allocation = self.allocations.all()[0]
        actual = self.tested.cmd_allocation__inauguratorsIDs(id=allocation.index(), peer=None)
        actualAllocatedNames = actual.keys()
        expectedAllocatedNames = self.requirements.keys()
        self.assertEquals(set(actualAllocatedNames), set(expectedAllocatedNames))
        self.assertEquals(len(actualAllocatedNames), len(expectedAllocatedNames))
        actualAllocatedIDs = actual.values()
        expectedAllocatedIDs = self.hostsIDs[:len(self.requirements)]
        self.assertEquals(set(actualAllocatedIDs), set(expectedAllocatedIDs))
        self.assertEquals(len(actualAllocatedIDs), len(expectedAllocatedIDs))

    @classmethod
    def osmosisListLabelsFoundMock(cls, cmd):
        if cmd[0:2] == ['osmosis', 'listlabels']:
            return cmd[2]
        raise ValueError("Implement me")

if __name__ == "__main__":
    unittest.main()
