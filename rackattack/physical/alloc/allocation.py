from rackattack.common import globallock
from rackattack.common import hoststatemachine
from rackattack.common import timer
import time
import logging
import tempfile


class Allocation:
    _HEARTBEAT_TIMEOUT = 45
    _LIMBO_AFTER_DEATH_DURATION = 60

    def __init__(self, index, requirements, allocationInfo, allocated, broadcaster, freePool, hosts):
        self._index = index
        self._requirements = requirements
        self._allocationInfo = allocationInfo
        self._broadcaster = broadcaster
        self._freePool = freePool
        self._hosts = hosts
        self._waiting = allocated
        self._inaugurated = dict()
        self._forgottenHosts = set()
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
        assert self.dead() is None
        return not self._waiting

    def free(self):
        if self.dead():
            raise Exception("Cant free allocation: its already dead: '%s'" % self._death['reason'])
        self._die("freed")

    def withdraw(self, message):
        self._broadcaster.allocationWithdraw(self._index, message)
        self._die("withdrawn")

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
            if stateMachine.state() == hoststatemachine.STATE_DESTROYED:
                logging.info("State machine %(id)s was destroyed during the allocation's lifetime",
                             dict(id=stateMachine.hostImplementation().id()))
                continue
            self._returnHostToFreePool(stateMachine)
        self._inaugurated = None
        self._death = dict(when=time.time(), reason=reason)
        timer.cancelAllByTag(tag=self)
        self._broadcaster.allocationChangedState(self._index)
        self._broadcaster.cleanupAllocationPublishResources(self._index)
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
        self._hosts.destroy(stateMachine)
        if self.dead() is not None:
            logging.warn('State machine %(id)s self destructed while allocation %(index)s is dead.', dict(
                         id=stateMachine.hostImplementation().id(), index=self._index))
            return
        if stateMachine in self._forgottenHosts:
            logging.info("Allocation %(idx)s ignores destruction of host %(hostID)s",
                         dict(idx=self.index(), hostID=stateMachine.hostImplementation().id()))
        else:
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

    def _detachHostFromCollection(self, hostStateMachine, collection):
        matchingMachines = [name for name, stateMachine in collection.iteritems()
                            if stateMachine == hostStateMachine]
        assert len(matchingMachines) == 1, matchingMachines
        machineName = matchingMachines[0]
        del collection[machineName]

    def _forgetAboutHost(self, hostStateMachine):
        hostID = hostStateMachine.hostImplementation().id()
        if self.dead() is not None:
            msg = "Cannot release a host after death (allocation #%(index)s)" % dict(index=self.index())
            raise Exception(msg)
        if hostStateMachine not in self.allocated().values():
            msg = "Cannot release host %(hostID)s from allocation #%(index)s as it's not allocated to it" \
                % dict(index=self.index(), hostID=hostID)
            raise Exception(msg)
        self._forgottenHosts.add(hostStateMachine)
        if hostStateMachine in self._waiting.values():
            self._detachHostFromCollection(hostStateMachine, self._waiting)
            if self.dead() is None:
                assert hostStateMachine not in self._inaugurated.values()
        elif self.dead() is None and hostStateMachine in self._inaugurated.values():
            self._detachHostFromCollection(hostStateMachine, self._inaugurated)

    def detachHost(self, hostStateMachine):
        self._forgetAboutHost(hostStateMachine)
        hostStateMachine.destroy()
        if not self.allocated():
            self._die("No hosts left in allocation")

    def releaseHost(self, hostStateMachine):
        self._forgetAboutHost(hostStateMachine)
        assert hostStateMachine.state() != hoststatemachine.STATE_DESTROYED
        self._returnHostToFreePool(hostStateMachine)
        if not self.allocated():
            self._die("No hosts left in allocation")

    def _returnHostToFreePool(self, hostStateMachine):
        hostStateMachine.unassign()
        hostStateMachine.setDestroyCallback(None)
        self._freePool.put(hostStateMachine)
