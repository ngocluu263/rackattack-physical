from rackattack.tcp import heartbeat
from rackattack.common import baseipcserver
from rackattack.physical import network
import logging


class IPCServer(baseipcserver.BaseIPCServer):
    def __init__(self, publicNATIP, osmosisServerIP, dnsmasq, allocations, hosts):
        self._publicNATIP = publicNATIP
        self._osmosisServerIP = osmosisServerIP
        self._dnsmasq = dnsmasq
        self._allocations = allocations
        self._hosts = hosts
        baseipcserver.BaseIPCServer.__init__(self)

    def cmd_allocate(self, requirements, allocationInfo, peer):
        allocation = self._allocations.create(requirements, allocationInfo)
        return allocation.index()

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
            publicNATIP=self._publicNATIP,
            peer=peer)

    def cmd_node__coldRestart(self, allocationID, nodeID, peer):
        stateMachine = self._findNode(allocationID, nodeID)
        logging.info("Cold restarting node %(node)s by allocator request", dict(node=nodeID))
        stateMachine.hostImplementation().coldRestart()

    def cmd_node__answerDHCP(self, allocationID, nodeID, shouldAnswer, peer):
        stateMachine = self._findNode(allocationID, nodeID)
        logging.info("Should answer DHCP: %(should)s node %(node)s", dict(node=nodeID, should=shouldAnswer))
        if shouldAnswer:
            self._dnsmasq.addIfNotAlready(
                stateMachine.hostImplementation().primaryMACAddress(),
                stateMachine.hostImplementation().ipAddress())
        else:
            self._dnsmasq.remove(stateMachine.hostImplementation().primaryMACAddress())
        stateMachine.hostImplementation().coldRestart()

    def cmd_admin__queryStatus(self, peer):
        allocations = [dict(
            index=a.index(),
            allocationInfo=a.allocationInfo(),
            allocated={k: v.hostImplementation().index() for k, v in a.allocated().iteritems()},
            done=a.dead() or a.done(),
            dead=a.dead()
            ) for a in self._allocations.all()]
        STATE = {
            1: "QUICK_RECLAIMATION_IN_PROGRESS",
            2: "SLOW_RECLAIMATION_IN_PROGRESS",
            3: "CHECKED_IN",
            4: "INAUGURATION_LABEL_PROVIDED",
            5: "INAUGURATION_DONE",
            6: "DESTROYED"}
        hosts = [dict(
            index=s.hostImplementation().index(),
            id=s.hostImplementation().id(),
            primaryMACAddress=s.hostImplementation().primaryMACAddress(),
            secondaryMACAddress=s.hostImplementation().secondaryMACAddress(),
            ipAddress=s.hostImplementation().ipAddress(),
            state=STATE[s.state()]
            ) for s in self._hosts.all()]
        return dict(allocations=allocations, hosts=hosts)
