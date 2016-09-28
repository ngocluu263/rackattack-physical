import os
import sys
import yaml
import logging
import subprocess
from rackattack.physical import config
from rackattack.physical import network


def runCmd(cmd, canFail):
    if canFail:
        subprocess.call(cmd, close_fds=True)
    else:
        result = subprocess.check_output(cmd, close_fds=True)
        if result:
            logging.info(result)


def deleteRules(interface):
    for index in xrange(1, 4):
        cmd = ["iptables", '-D', 'PREROUTING', '-t', 'nat', '-i', interface,
               "-p", "tcp", "--dport", str(network.sshPortFromHostIndex(index)), "-j", "DNAT",
               "--to-destination", "%s:22" % network.ipAddressFromHostIndex(index)]
        runCmd(cmd, canFail=True)
    cmd = ["iptables", "-t", "nat", "-D", "POSTROUTING", "-o", interface, "-j",
           "MASQUERADE"]
    runCmd(cmd, canFail=True)


def writeRules(interface):
    for index in xrange(1, 4):
        cmd = ["iptables", "-A", "PREROUTING", "-t", "nat", "-i", interface,
               "-p", "tcp", "--dport", str(network.sshPortFromHostIndex(index)), "-j", "DNAT",
               "--to", "%s:22" % network.ipAddressFromHostIndex(index)]
        print " ".join(cmd)
        runCmd(cmd, canFail=False)
    cmd = ["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", interface, "-j",
           "MASQUERADE"]
    runCmd(cmd, canFail=True)


def enablePortForwarding(inteface):
    confPath = os.path.join("/proc/sys/net/ipv4/conf/", interface, "forwarding")
    with open(confPath, "w") as confFile:
        confFile.write("1")


def configureNat(interface):
    enablePortForwarding(interface)
    deleteRules(interface)
    writeRules(interface)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "Usage: python %(filename)s <test_client_side_interface>" % dict(filename=__file__)
        sys.exit(1)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    with open(config.CONFIGURATION_FILE) as f:
        conf = yaml.load(f.read())
    network.initialize_globals(conf)
    interface = sys.argv[1]
    configureNat(interface)
