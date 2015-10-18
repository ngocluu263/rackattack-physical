from rackattack.common import globallock


class FreePool:
    def __init__(self, hosts):
        self._hosts = hosts
        self._pool = []

    def put(self, hostStateMachine):
        assert globallock.assertLocked()
        self._pool.append(hostStateMachine)
        hostStateMachine.setDestroyCallback(self._hostSelfDestructed)

    def all(self):
        assert globallock.assertLocked()
        for hostStateMachine in self._pool:
            yield hostStateMachine

    def takeOut(self, hostStateMachine):
        assert globallock.assertLocked()
        self._pool.remove(hostStateMachine)

    def _hostSelfDestructed(self, hostStateMachine):
        assert globallock.assertLocked()
        self._hosts.destroy(hostStateMachine)
        self._pool.remove(hostStateMachine)
