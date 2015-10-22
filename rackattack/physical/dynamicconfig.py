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
        return self._hosts[hostID].isOnline()

    def _takenOffline(self, hostData):
        return self._isOnline(hostData["id"]) and hostData.get('offline', False)

    def _takeHostOffline(self, hostData):
        hostInstance = self._hosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        hostInstance.setIsOnline(False)
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

    def _takenOnline(self, hostData):
        return not self._isOnline(hostData["id"]) and not hostData.get('offline', False)

    def _bringHostOnline(self, hostData):
        hostInstance = self._hosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        hostInstance.setIsOnline(True)
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
        if self._takenOffline(hostData):
            logging.info("Host %(host)s has been taken offline", dict(host=hostData['id']))
            self._takeHostOffline(hostData)
        elif self._takenOnline(hostData):
            logging.info("Host %(host)s has been taken back online", dict(host=hostData['id']))
            self._bringHostOnline(hostData)

    def _reload(self):
        logging.info("Reloading configuration")
        rack = self._loadRackYAML()
        with globallock.lock():
            for hostData in rack['HOSTS']:
                if self._registeredHost(hostData["id"]):
                    self._registeredHostConfiguration(hostData)
                else:
                    self._newHostInConfiguration(hostData)

    def _newHostInConfiguration(self, hostData):
        chewed = dict(hostData)
        if 'offline' in chewed:
            isOffline = chewed["offline"]
            if isOffline not in [True, False]:
                logging.error("Invalid value for 'offline'")
                raise ValueError(isOffline)
            chewed["isOnline"] = not isOffline
            del chewed["offline"]
        hostInstance = host.Host(index=self._availableIndex(), **chewed)
        logging.info("Adding host %(id)s - %(ip)s", dict(
            id=hostInstance.id(), ip=hostInstance.ipAddress()))
        if hostData.get('offline', False):
            logging.info('Host %(host)s added in offline state', dict(host=hostInstance.id()))
        else:
            self._dnsmasq.add(hostData['primaryMAC'], hostInstance.ipAddress())
            self._startUsingHost(hostInstance)
            logging.info('Host %(host)s added in online state', dict(host=hostInstance.id()))
        self._hosts[hostData['id']] = hostInstance

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

    def getOfflineHosts(self):
        return {hostID: host for (hostID, host) in self._hosts.iteritems() if not host.isOnline()}

    def getOnlineHosts(self):
        return {hostID: host for (hostID, host) in self._hosts.iteritems() if host.isOnline()}
