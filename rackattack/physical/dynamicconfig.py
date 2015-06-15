import signal
from rackattack.common import globallock
from rackattack.physical import config
from rackattack.physical import host
from rackattack.common import hoststatemachine
import yaml
import logging


class DynamicConfig:
    def __init__(self, hosts, dnsmasq, inaugurate, tftpboot, freePool, allocations):
        self._hosts = hosts
        self._dnsmasq = dnsmasq
        self._inaugurate = inaugurate
        self._tftpboot = tftpboot
        self._freePool = freePool
        self._allocations = allocations
        self._rack = []
        self._offlineHosts = dict()
        self._onlineHosts = dict()
        signal.signal(signal.SIGHUP, lambda *args: self._reload())
        self._reload()

    def _loadRackYAML(self):
        logging.info("Reading %(file)s", dict(file=config.RACK_YAML))
        with open(config.RACK_YAML) as f:
            return yaml.load(f.read())

    def _takenOffline(self, hostData):
        return hostData['id'] in self._onlineHosts and hostData.get('offline', False)

    def _takeHostOffline(self, hostData):
        hostInstance = self._onlineHosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        del self._onlineHosts[hostInstance.id()]
        self._offlineHosts[hostInstance.id()] = hostInstance
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
            if stateMachine in self._hosts.all():
                logging.error("State machine was not removed from hosts pool")
                self._hosts.destroy(stateMachine)

    def _broughtOnLineHost(self, hostData):
        return hostData['id'] in self._offlineHosts and not hostData.get('offline', False)

    def _bringHostOnline(self, hostData):
        hostInstance = self._offlineHosts[hostData['id']]
        assert hostInstance.id() == hostData['id']
        try:
            self._dnsmasq.add(hostData['primaryMAC'], hostInstance.ipAddress())
        except AssertionError:
            logging.exception("Failed adding host %(id)s to DNSMasq's list. Perhaps you're waiting for an "
                              "earlier update that hasn't occurred yet? In that case, try adding the host "
                              "again in a few seconds.", dict(id=hostData['id']))
            return
        del self._offlineHosts[hostInstance.id()]
        self._onlineHosts[hostInstance.id()] = hostInstance
        self._startUsingHost(hostInstance)

    def _registeredHost(self, hostData):
        return hostData['id'] in self._offlineHosts or hostData['id'] in self._onlineHosts

    def _registeredHostConfiguration(self, hostData):
        if self._takenOffline(hostData):
            logging.info("Host %(host)s has been taken offline", dict(host=hostData['id']))
            self._takeHostOffline(hostData)
        elif self._broughtOnLineHost(hostData):
            logging.info("Host %(host)s has been taken back online", dict(host=hostData['id']))
            self._bringHostOnline(hostData)

    def _reload(self):
        logging.info("Reloading configuration")
        rack = self._loadRackYAML()
        with globallock.lock():
            for hostData in rack['HOSTS']:
                if self._registeredHost(hostData):
                    self._registeredHostConfiguration(hostData)
                else:
                    self._newHostInConfiguration(hostData)

    def _newHostInConfiguration(self, hostData):
        chewed = dict(hostData)
        if 'offline' in chewed:
            del chewed['offline']
        hostInstance = host.Host(index=self._availableIndex(), **chewed)
        logging.info("Adding host %(id)s - %(ip)s", dict(
            id=hostInstance.id(), ip=hostInstance.ipAddress()))
        if hostData.get('offline', False):
            self._offlineHosts[hostData['id']] = hostInstance
            hostInstance.turnOff()
            logging.info('Host %(host)s added in offline state', dict(host=hostInstance.id()))
        else:
            self._dnsmasq.add(hostData['primaryMAC'], hostInstance.ipAddress())
            self._onlineHosts[hostData['id']] = hostInstance
            self._startUsingHost(hostInstance)
            logging.info('Host %(host)s added in online state', dict(host=hostInstance.id()))

    def _startUsingHost(self, hostInstance):
        stateMachine = hoststatemachine.HostStateMachine(
            hostImplementation=hostInstance,
            inaugurate=self._inaugurate,
            tftpboot=self._tftpboot,
            dnsmasq=self._dnsmasq,
            freshVMJustStarted=False)
        self._hosts.add(stateMachine)
        self._freePool.put(stateMachine)

    def _findStateMachine(self, hostInstance):
        for stateMachine in self._hosts.all():
            if stateMachine.hostImplementation() is hostInstance:
                return stateMachine
        return None

    def _availableIndex(self):
        return 1 + len(self._onlineHosts) + len(self._offlineHosts)

    def getOfflineHosts(self):
        return self._offlineHosts

    def getOnlineHosts(self):
        return self._onlineHosts
