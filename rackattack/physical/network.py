from rackattack.virtual import sh
import subprocess
import os

_IP_ADDRESS_FORMAT = "192.168.1.%d"
GATEWAY_IP_ADDRESS = _IP_ADDRESS_FORMAT % 1
BOOTSERVER_IP_ADDRESS = _IP_ADDRESS_FORMAT % 1
NETMASK = '255.255.255.0'
_NETWORK_PREFIX = "192.168.1."
LAST_INDEX = 200


def setGatewayIP(ip):
    global GATEWAY_IP_ADDRESS
    GATEWAY_IP_ADDRESS = ip


def ipAddressFromHostIndex(index):
    return _IP_ADDRESS_FORMAT % (10 + index)


FIRST_IP = ipAddressFromHostIndex(0)
LAST_IP = ipAddressFromHostIndex(LAST_INDEX)


def sshPortFromHostIndex(index):
    return 2010 + index


def translateSSHCredentials(index, credentials, publicNATIP, peer):
    if peer[0].startswith(_NETWORK_PREFIX):
        return credentials
    assert ipAddressFromHostIndex(index) == credentials['hostname']
    return dict(credentials, hostname=publicNATIP, port=sshPortFromHostIndex(index))
