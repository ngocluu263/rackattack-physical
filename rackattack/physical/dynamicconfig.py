import signal
from rackattack.common import globallock
from rackattack.physical import config
from rackattack.physical import host
from rackattack.common import hoststatemachine
import yaml
import logging


class DynamicConfig:
    def __init__(self, hosts, dnsmasq, inaugurate, tftpboot, freePool, allocations, reclaimHost):
        self._hostsStateMachines = hosts
        self._dnsmasq = dnsmasq
        self._inaugurate = inaugurate
        self._tftpboot = tftpboot
        self._freePool = freePool
        self._allocations = allocations
        self._reclaimHost = reclaimHost
        self._rack = []
        self._hosts = dict()
        signal.signal(signal.SIGHUP, lambda *args: self._reload())
        self._reload()

    def _loadRackYAML(self):
        logging.info("Reading %(file)s", dict(file=config.RACK_YAML))
        with open(config.RACK_YAML) as f:
            return yaml.load(f.read())

    def _isOnline(self, hostID):
        return self._hosts[hostID].state() == host.STATES.ONLINE

    def _wasHostStateChanged(self, hostData):
        hostID = hostData["id"]
        oldState = self._hosts[hostID].state()
        newState = hostData["state"]
        return oldState != newState

    def _takeHostOffline(self, hostData):
        hostInstance = self._hosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        hostInstance.setState(host.STATES.OFFLINE)
        self._dnsmasq.remove(hostData['primaryMAC'])
        hostInstance.turnOff()
        stateMachine = self._findStateMachine(hostInstance)
        if stateMachine is None:
            logging.info("'%(id)s' which is taken offline is already destroyed.", dict(id=hostData['id']))
        else:
            logging.info("Destroying state machine of host %(id)s", dict(id=hostData['id']))
            stateMachine.destroy()
            for allocation in self._allocations.all():
                if allocation.dead() is None and stateMachine in allocation.allocated().values():
                    logging.error("Allocation %(id)s is not dead although its node was killed",
                                  dict(id=allocation.index()))
                    allocation.withdraw("node %(id)s taken offline" % dict(id=hostData['id']))
            if stateMachine in self._hostsStateMachines.all():
                logging.error("State machine was not removed from hosts pool")
                self._hostsStateMachines.destroy(stateMachine)

    def _bringHostOnline(self, hostData):
        hostInstance = self._hosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        hostInstance.setState(host.STATES.ONLINE)
        try:
            self._dnsmasq.add(hostData['primaryMAC'], hostInstance.ipAddress())
        except AssertionError:
            logging.exception("Failed adding host %(id)s to DNSMasq's list. Perhaps you're waiting for an "
                              "earlier update that hasn't occurred yet? In that case, try adding the host "
                              "again in a few seconds.", dict(id=hostData['id']))
            return
        self._startUsingHost(hostInstance)

    def _registeredHost(self, hostID):
        return hostID in self._hosts

    def _registeredHostConfiguration(self, hostData):
        hostID = hostData["id"]
        if self._wasHostStateChanged(hostData):
            newState = hostData["state"]
            if newState == host.STATES.OFFLINE:
                logging.info("Host %(hostID)s has been taken offline", dict(hostID=hostID))
                self._takeHostOffline(hostData)
            elif newState == host.STATES.ONLINE:
                logging.info("Host %(hostID)s has been taken back online", dict(hostID=hostID))
                self._bringHostOnline(hostData)
        if "pool" in hostData:
            self._hosts[hostID].setPool(hostData["pool"])

    def _normalizeStateCase(self, hostData):
        if "state" in hostData:
            hostData["state"] = hostData["state"].upper()

    def _reload(self):
        logging.info("Reloading configuration")
        rack = self._loadRackYAML()
        with globallock.lock():
            for hostData in rack['HOSTS']:
                self._normalizeStateCase(hostData)
                if self._registeredHost(hostData["id"]):
                    self._registeredHostConfiguration(hostData)
                else:
                    self._newHostInConfiguration(hostData)

    def _newHostInConfiguration(self, hostData):
        chewed = dict(hostData)
        hostInstance = host.Host(index=self._availableIndex(), **chewed)
        hostID = hostInstance.id()
        logging.info("Adding host %(hostID)s - %(ip)s", dict(hostID=hostID, ip=hostInstance.ipAddress()))
        state = hostInstance.state()
        if state == host.STATES.ONLINE:
            self._dnsmasq.add(hostData['primaryMAC'], hostInstance.ipAddress())
            self._startUsingHost(hostInstance)
            logging.info('Host %(hostID)s added in online state', dict(hostID=hostID))
        else:
            logging.info('Host %(hostID)s added in %(state)s state', dict(state=state, hostID=hostID))
        self._hosts[hostID] = hostInstance

    def _startUsingHost(self, hostInstance):
        stateMachine = hoststatemachine.HostStateMachine(
            hostImplementation=hostInstance,
            inaugurate=self._inaugurate,
            tftpboot=self._tftpboot,
            dnsmasq=self._dnsmasq,
            reclaimHost=self._reclaimHost,
            freshVMJustStarted=False)
        self._hostsStateMachines.add(stateMachine)
        self._freePool.put(stateMachine)

    def _findStateMachine(self, hostInstance):
        for stateMachine in self._hostsStateMachines.all():
            if stateMachine.hostImplementation() is hostInstance:
                return stateMachine
        return None

    def _availableIndex(self):
        return 1 + len(self._hosts)

    def _getHostsByState(self, state):
        return {hostID: host for (hostID, host) in self._hosts.iteritems() if
                host.state() == state}

    def getOfflineHosts(self):
        return self._getHostsByState(host.STATES.OFFLINE)

    def getOnlineHosts(self):
        return self._getHostsByState(host.STATES.ONLINE)
