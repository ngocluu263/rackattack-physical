import sys
import logging
import subprocess
from rackattack.physical.network import sshPortFromHostIndex, ipAddressFromHostIndex, LAST_INDEX


def runCmd(cmd, canFail):
    if canFail:
        subprocess.call(cmd, close_fds=True)
    else:
        result = subprocess.check_output(cmd, close_fds=True)
        if result:
            logging.info(result)


def deleteRules(deviceName):
    for index in xrange(1, LAST_INDEX):
        cmd = ["iptables", '-D', 'PREROUTING', '-t', 'nat', '-i', deviceName,
               "-p", "tcp", "--dport", str(sshPortFromHostIndex(index)), "-j", "DNAT",
               "--to-destination", "%s:22" % ipAddressFromHostIndex(index)]
        runCmd(cmd, canFail=True)
    cmd = ["iptables", "-t", "nat", "-D", "POSTROUTING", "-o", deviceName, "-j", 'MASQUERADE']
    runCmd(cmd, canFail=True)


def writeRules(deviceName):
    for index in xrange(1, LAST_INDEX + 1):
        cmd = ["iptables", "-A", "PREROUTING", "-t", "nat", "-i", deviceName,
               "-p", "tcp", "--dport", str(sshPortFromHostIndex(index)), "-j", "DNAT",
               "--to", "%s:22" % ipAddressFromHostIndex(index)]
        runCmd(cmd, canFail=False)
    cmd = ["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", deviceName, "-j", 'MASQUERADE']
    runCmd(cmd, canFail=True)


def configureNat(deviceName):
    deleteRules(deviceName)
    writeRules(deviceName)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "Usage: python %(filename)s <interface_name>" % dict(filename=__file__)
        sys.exit(1)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    interfaceName = sys.argv[1]
    print "Configuring NAT locally for %(interfaceName)s" % dict(interfaceName=interfaceName)
    configureNat(interfaceName)
