import mock
import unittest
from rackattack.common import globallock
from rackattack.physical.alloc.freepool import FreePool
from rackattack.physical.tests.common import HostStateMachine, Allocation, Hosts


class Test(unittest.TestCase):
    def setUp(self):
        globallock._lock.acquire()
        self._hosts = Hosts()
        self.tested = FreePool(self._hosts)

    def tearDown(self):
        globallock._lock.release()

    def test_OneHost(self):
        host = HostStateMachine('host1')
        self.tested.put(host)
        self.assertIn(host, self.tested.all())
        self.tested.takeOut(host)
        self.assertNotIn(host, self.tested.all())

    def test_DestroyCallback(self):
        host = HostStateMachine('host1')
        self._hosts.add(host)
        self.tested.put(host)
        host._destroyCallback(host)
        self.assertNotIn(host, self.tested.all())

    def test_All(self):
        hosts = [HostStateMachine(str(i)) for i in xrange(10)]
        for host in hosts:
            self._hosts.add(host)

        for host in hosts:
            self.tested.put(host)

        actualAll = self.tested.all()
        self.assertEquals(set(actualAll), set(hosts))


if __name__ == '__main__':
    unittest.main()
