from rackattack.tcp import heartbeat
from rackattack.common import baseipcserver
from rackattack.physical import network
from rackattack.common.hoststatemachine import STATE_DESTROYED
import logging


class IPCServer(baseipcserver.BaseIPCServer):
    def __init__(self, osmosisServerIP, dnsmasq, allocations, hosts, dynamicConfig,
                 reclaimHost):
        self._osmosisServerIP = osmosisServerIP
        self._dnsmasq = dnsmasq
        self._allocations = allocations
        self._hosts = hosts
        self._dynamicConfig = dynamicConfig
        self._reclaimHost = reclaimHost
        baseipcserver.BaseIPCServer.__init__(self)

    def cmd_allocate(self, requirements, allocationInfo, peer):
        allocation = self._allocations.create(requirements, allocationInfo)
        return allocation.index()

    def cmd_allocation__inauguratorsIDs(self, id, peer):
        allocation = self._allocations.byIndex(id)
        if allocation.dead():
            raise Exception("Must not fetch nodes from a dead allocation")
        result = {}
        for name, stateMachine in allocation.allocated().iteritems():
            host = stateMachine.hostImplementation()
            result[name] = host.id()
        return result

    def cmd_allocation__nodes(self, id, peer):
        allocation = self._allocations.byIndex(id)
        if allocation.dead():
            raise Exception("Must not fetch nodes from a dead allocation")
        if not allocation.done():
            raise Exception("Must not fetch nodes from a not done allocation")
        result = {}
        for name, stateMachine in allocation.allocated().iteritems():
            host = stateMachine.hostImplementation()
            result[name] = dict(
                id=host.id(),
                primaryMACAddress=host.primaryMACAddress(),
                secondaryMACAddress=host.secondaryMACAddress(),
                ipAddress=host.ipAddress(),
                netmask=network.NETMASK,
                inauguratorServerIP=network.GATEWAY_IP_ADDRESS,
                gateway=network.GATEWAY_IP_ADDRESS,
                osmosisServerIP=self._osmosisServerIP)
        return result

    def cmd_allocation__free(self, id, peer):
        allocation = self._allocations.byIndex(id)
        allocation.free()

    def cmd_allocation__done(self, id, peer):
        allocation = self._allocations.byIndex(id)
        return allocation.done()

    def cmd_allocation__dead(self, id, peer):
        allocation = self._allocations.byIndex(id)
        return allocation.dead()

    def cmd_heartbeat(self, ids, peer):
        for id in ids:
            allocation = self._allocations.byIndex(id)
            allocation.heartbeat()
        return heartbeat.HEARTBEAT_OK

    def _findNode(self, allocationID, nodeID):
        allocation = self._allocations.byIndex(allocationID)
        for stateMachine in allocation.inaugurated().values():
            if stateMachine.hostImplementation().id() == nodeID:
                return stateMachine
        raise Exception("Node with id '%s' was not found in this allocation" % nodeID)

    def cmd_node__rootSSHCredentials(self, allocationID, nodeID, peer):
        stateMachine = self._findNode(allocationID, nodeID)
        credentials = stateMachine.hostImplementation().rootSSHCredentials()
        return network.translateSSHCredentials(
            index=stateMachine.hostImplementation().index(),
            credentials=credentials,
            peer=peer)

    def cmd_node__coldRestart(self, allocationID, nodeID, peer):
        stateMachine = self._findNode(allocationID, nodeID)
        logging.info("Cold restarting node %(node)s by allocator request", dict(node=nodeID))
        host = stateMachine.hostImplementation()
        self._reclaimHost.cold(host)
        host.validateSOLStarted()

    def cmd_node__answerDHCP(self, allocationID, nodeID, shouldAnswer, peer):
        stateMachine = self._findNode(allocationID, nodeID)
        logging.info("Should answer DHCP: %(should)s node %(node)s", dict(node=nodeID, should=shouldAnswer))
        if shouldAnswer:
            self._dnsmasq.addIfNotAlready(
                stateMachine.hostImplementation().primaryMACAddress(),
                stateMachine.hostImplementation().ipAddress())
        else:
            self._dnsmasq.remove(stateMachine.hostImplementation().primaryMACAddress())

    def cmd_node__releaseFromAllocation(self, allocationID, nodeID, peer):
        allocation = self._allocations.byIndex(allocationID)
        if allocation.dead() is not None:
            logging.info("Got an invalid request to release a host from a dead allocation %(allocationID)s",
                         dict(allocationID=allocationID))
            raise Exception("Cannot release a host from a dead allocation")
        stateMachine = self._findNode(allocationID, nodeID)
        hostID = stateMachine.hostImplementation().id()
        logging.info("Attempting to release host %(hostID)s from allocation %(allocationID)s...",
                     dict(hostID=hostID, allocationID=allocationID))
        allocation.releaseHost(stateMachine)

    def cmd_admin__queryStatus(self, peer):
        allocations = [dict(
            index=a.index(),
            allocationInfo=a.allocationInfo(),
            allocated={k: v.hostImplementation().index() for k, v in a.allocated().iteritems()},
            done=a.dead() or a.done(),
            dead=a.dead(),
            duration=int(a.getDuration())
            ) for a in self._allocations.all()]
        hosts = self._onlineHosts() + self._offlineHosts() + self._detachedHosts()
        return dict(allocations=allocations, hosts=hosts)

    def cmd_admin__asyncReloadConfiguration(self, peer):
        self._dynamicConfig.asyncReload()

    def _detachedHosts(self):
        return [dict(index=host.index(),
                     id=host_id,
                     primaryMACAddress=host.primaryMACAddress(),
                     secondaryMACAddress=host.secondaryMACAddress(),
                     ipAddress=host.ipAddress(),
                     state="DETACHED",
                     pool=host.pool())
                for host_id, host in self._dynamicConfig.getDetachedHosts().iteritems()]

    def _offlineHosts(self):
        return [dict(index=host.index(),
                     id=host_id,
                     primaryMACAddress=host.primaryMACAddress(),
                     secondaryMACAddress=host.secondaryMACAddress(),
                     ipAddress=host.ipAddress(),
                     state="OFFLINE",
                     pool=host.pool())
                for host_id, host in self._dynamicConfig.getOfflineHosts().iteritems()]

    def _onlineHosts(self):
        STATE = {
            1: "QUICK_RECLAIMATION_IN_PROGRESS",
            2: "SLOW_RECLAIMATION_IN_PROGRESS",
            3: "CHECKED_IN",
            4: "INAUGURATION_LABEL_PROVIDED",
            5: "INAUGURATION_DONE",
            6: "DESTROYED"}
        statesOfHostsThatHaveMachines = dict([(machine.hostImplementation().id(), machine.state())
                                             for machine in self._hosts.all()])
        return [dict(index=host.index(),
                     id=hostID,
                     primaryMACAddress=host.primaryMACAddress(),
                     secondaryMACAddress=host.secondaryMACAddress(),
                     ipAddress=host.ipAddress(),
                     state=STATE[statesOfHostsThatHaveMachines.get(hostID, STATE_DESTROYED)],
                     pool=host.pool())
                for hostID, host in self._dynamicConfig.getOnlineHosts().iteritems()]
