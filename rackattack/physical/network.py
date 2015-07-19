import netaddr


_NETMASK_PREFIX_LENGTH = 22
_NR_RESERVED_HOSTS = 10
_IP_ADDRESS_FORMAT = "192.168.%d.%d"
GATEWAY_IP_ADDRESS = _IP_ADDRESS_FORMAT % (1, 1)
_HOSTS = None
NETMASK = None
BOOTSERVER_IP_ADDRESS = None
LAST_INDEX = None
FIRST_IP = None
LAST_IP = None


def getHostsAddresses(subnet):
    global _NR_RESERVER_HOSTS
    for address in subnet:
        if address.words[2] > 1 or (address.words[2] == 1 and address.words[3] > _NR_RESERVED_HOSTS):
            yield str(address)


def setGatewayIP(ip):
    global GATEWAY_IP_ADDRESS
    GATEWAY_IP_ADDRESS = ip


def ipAddressFromHostIndex(index):
    assert index > 0
    global _HOSTS
    return _HOSTS[index - 1]


def sshPortFromHostIndex(index):
    return 2010 + index


def translateSSHCredentials(index, credentials, publicNATIP, peer):
    global _HOSTS
    if peer[0] in _HOSTS:
        return credentials
    assert ipAddressFromHostIndex(index) == credentials['hostname']
    return dict(credentials, hostname=publicNATIP, port=sshPortFromHostIndex(index))


def initialize_globals():
    global _HOSTS, NETMASK, GATEWAY_IP_ADDRESS, BOOTSERVER_IP_ADDRESS, LAST_INDEX, FIRST_IP, LAST_IP
    firstAddrInSubnet = _IP_ADDRESS_FORMAT % (0, 0)
    subnet = netaddr.IPNetwork("%(firstAddr)s/%(prefixLen)s" % dict(firstAddr=firstAddrInSubnet,
                                                                    prefixLen=_NETMASK_PREFIX_LENGTH))
    NETMASK = str(subnet.netmask)
    _HOSTS = list(getHostsAddresses(subnet))
    GATEWAY_IP_ADDRESS = _IP_ADDRESS_FORMAT % (1, 1)
    assert GATEWAY_IP_ADDRESS not in _HOSTS
    BOOTSERVER_IP_ADDRESS = _IP_ADDRESS_FORMAT % (1, 1)
    assert BOOTSERVER_IP_ADDRESS not in _HOSTS
    LAST_INDEX = len(_HOSTS)
    FIRST_IP = _HOSTS[0]
    LAST_IP = _HOSTS[LAST_INDEX - 1]

initialize_globals()
