import netaddr


NETMASK = None
LAST_INDEX = None
FIRST_IP = None
LAST_IP = None
_NODES = None
PUBLIC_NAT_IP = None
BOOTSERVER_IP_ADDRESS = None
GATEWAY_IP_ADDRESS = None


def getNodesAddresses(subnet, firstIP):
    firstAddr = netaddr.IPAddress(firstIP)
    subnetAddresses = list(subnet)
    idxOfFirstAddr = subnetAddresses.index(firstAddr)
    ipAddressesObjects = subnet[idxOfFirstAddr:]
    for addressObject in ipAddressesObjects:
        yield str(addressObject)


def ipAddressFromHostIndex(index):
    assert index > 0
    global _NODES
    return _NODES[index - 1]


def sshPortFromHostIndex(index):
    return 2010 + index


def translateSSHCredentials(index, credentials, peer):
    if peer[0] in _NODES:
        return credentials
    if PUBLIC_NAT_IP is None or not PUBLIC_NAT_IP:
        return dict(credentials, port=22)
    assert ipAddressFromHostIndex(index) == credentials['hostname']
    return dict(credentials, hostname=PUBLIC_NAT_IP, port=sshPortFromHostIndex(index))


def initialize_globals(conf):
    global _NODES, NETMASK, LAST_INDEX, FIRST_IP, LAST_IP, PUBLIC_NAT_IP, GATEWAY_IP_ADDRESS, \
        BOOTSERVER_IP_ADDRESS
    FIRST_IP = conf["FIRST_IP"]
    prefixLength = conf["NODES_SUBNET_PREFIX_LENGTH"]
    subnet = netaddr.IPNetwork("%(firstAddr)s/%(prefixLen)s" % dict(firstAddr=FIRST_IP,
                                                                    prefixLen=prefixLength))
    assert FIRST_IP in subnet
    NETMASK = str(subnet.netmask)
    _NODES = list(getNodesAddresses(subnet, FIRST_IP))
    assert FIRST_IP in _NODES
    GATEWAY_IP_ADDRESS = conf["GATEWAY_IP"]
    BOOTSERVER_IP_ADDRESS = conf["BOOTSERVER_IP"]
    assert BOOTSERVER_IP_ADDRESS not in _NODES
    assert BOOTSERVER_IP_ADDRESS in subnet
    LAST_INDEX = len(_NODES)
    LAST_IP = _NODES[LAST_INDEX - 1]
    PUBLIC_NAT_IP = conf.get("PUBLIC_NAT_IP", None)
