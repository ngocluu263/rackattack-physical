from rackattack.common import globallock
from rackattack.common import hoststatemachine
from rackattack.common import timer
import time
import logging
import tempfile


class Allocation:
    _HEARTBEAT_TIMEOUT = 15
    _LIMBO_AFTER_DEATH_DURATION = 60

    def __init__(self, index, requirements, allocationInfo, allocated, broadcaster, freePool):
        self._index = index
        self._requirements = requirements
        self._allocationInfo = allocationInfo
        self._broadcaster = broadcaster
        self._freePool = freePool
        self._waiting = allocated
        self._inaugurated = dict()
        self._death = None
        self._broadcastAllocationCreation()
        for name, stateMachine in self._waiting.iteritems():
            stateMachine.hostImplementation().truncateSerialLog()
            self._assign(name, stateMachine)
        self.heartbeat()

    def index(self):
        return self._index

    def allocationInfo(self):
        return self._allocationInfo

    def inaugurated(self):
        assert self.done()
        return self._inaugurated

    def allocated(self):
        result = dict(self._waiting)
        if self._inaugurated is not None:
            result.update(self._inaugurated)
        return result

    def done(self):
        done = len(self._inaugurated) == len(self._requirements)
        assert not done or len(self._waiting) == 0
        return done

    def free(self):
        if self.dead():
            raise Exception("Cant free allocation: its already dead: '%s'" % self._death['reason'])
        self._die("freed")

    def withdraw(self, message):
        self._die("withdrawn")
        self._broadcaster.allocationWithdraw(self._index, message)

    def heartbeat(self):
        if self.dead():
            return
        timer.cancelAllByTag(tag=self)
        timer.scheduleIn(timeout=self._HEARTBEAT_TIMEOUT, callback=self._heartbeatTimeout, tag=self)

    def dead(self):
        assert self._death is None or self._inaugurated is None
        if self._death is None:
            return None
        return self._death['reason']

    def deadForAWhile(self):
        if not self.dead():
            return False
        return self._death['when'] < time.time() - self._LIMBO_AFTER_DEATH_DURATION

    def createPostMortemPack(self):
        contents = []
        for name, stateMachine in self.allocated().iteritems():
            contents.append("\n\n\n****************\n%s == %s\n******************" % (
                stateMachine.hostImplementation().id(), name))
            with open(stateMachine.hostImplementation().serialLogFilename(), "rb") as f:
                contents.append(f.read())
        filename = tempfile.mktemp()
        with open(filename, "wb") as f:
            f.write("\n".join(contents))
        return filename

    def _heartbeatTimeout(self):
        self._die("heartbeat timeout")

    def _die(self, reason):
        assert not self.dead()
        logging.info("Allocation %(idx)s dies of '%(reason)s'", dict(idx=self._index, reason=reason))
        for stateMachine in list(self._waiting.values()) + list(self._inaugurated.values()):
            stateMachine.unassign()
            stateMachine.setDestroyCallback(None)
            self._freePool.put(stateMachine)
        self._inaugurated = None
        self._death = dict(when=time.time(), reason=reason)
        timer.cancelAllByTag(tag=self)
        self._broadcaster.allocationChangedState(self._index)
        logging.info("Allocation %(idx)s died.", dict(idx=self._index))

    def _stateMachineChangedState(self, name, stateMachine):
        if stateMachine.state() == hoststatemachine.STATE_INAUGURATION_DONE:
            self._broadcaster.allocationProviderMessage(
                allocationID=self._index,
                message="host %s/%s inaugurated successfully" % (
                    stateMachine.hostImplementation().id(),
                    stateMachine.hostImplementation().ipAddress()))
            logging.info("Host %(id)s inaugurated successfully", dict(
                id=stateMachine.hostImplementation().id()))
            if name in self._waiting:
                del self._waiting[name]
                self._inaugurated[name] = stateMachine
            else:
                logging.warn('Got an unexpected inauguration-done msg for name: %(name)s hostID=%(hostID)s.'
                             'waiting: %(waiting)s, inaugurated: %(inaugurated)s',
                             dict(name=name, waiting=self._waiting, inaugurated=self._inaugurated,
                                  hostID=stateMachine.hostImplementation().id()))
            if self.done():
                self._broadcaster.allocationChangedState(self._index)

    def _stateMachineSelfDestructed(self, stateMachine):
        if self._inaugurated is None:
            logging.error('State machine self destructed more than once - %(id)s', dict(
                          id=stateMachine.hostImplementation().id()))
            return
        else:
            for k, v in self._waiting.iteritems():
                if v is stateMachine:
                    del self._waiting[k]
                    break
            for k, v in self._inaugurated.iteritems():
                if v is stateMachine:
                    del self._inaugurated[k]
                    break
        self._die("Unable to inaugurate Host %s" % stateMachine.hostImplementation().id())

    def _assign(self, name, stateMachine):
        stateMachine.setDestroyCallback(self._stateMachineSelfDestructed)
        stateMachine.assign(
            stateChangeCallback=lambda x: self._stateMachineChangedState(name, stateMachine),
            imageLabel=self._requirements[name]['imageLabel'],
            imageHint=self._requirements[name]['imageHint'])

    def _broadcastAllocationCreation(self):
        self._broadcaster.allocationCreated(allocationID=self._index, requirements=self._requirements,
                                            allocationInfo=self._allocationInfo, allocated=self._waiting)
