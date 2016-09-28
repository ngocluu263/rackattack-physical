import sys
import logging
from rackattack.physical import pikapatch
from rackattack.physical import logconfig
import argparse
from rackattack.physical import config
from rackattack.physical import network
from rackattack.physical import dynamicconfig
import rackattack.virtual.handlekill
from rackattack.common import dnsmasq
from rackattack.common import globallock
from rackattack.common import tftpboot
from rackattack.common import inaugurate
from rackattack.common import timer
from rackattack.common import hosts
from rackattack.physical.alloc import freepool
from rackattack.physical.alloc import allocations
from rackattack.physical import ipcserver
from rackattack.tcp import publish
from rackattack.tcp import transportserver
from twisted.internet import reactor
from twisted.web import server
from twisted.python import log
from rackattack.common import httprootresource
import inaugurator.server.config
import yaml
from rackattack.physical import reclaimhost
from rackattack.common import hoststatemachine

parser = argparse.ArgumentParser()
parser.add_argument("--requestPort", default=1014, type=int)
parser.add_argument("--subscribePort", default=1015, type=int)
parser.add_argument("--httpPort", default=1016, type=int)
parser.add_argument("--rackYAML")
parser.add_argument("--serialLogsDirectory")
parser.add_argument("--managedPostMortemPacksDirectory")
parser.add_argument("--configurationFile")
args = parser.parse_args()

if args.rackYAML:
    config.RACK_YAML = args.rackYAML
if args.serialLogsDirectory:
    config.SERIAL_LOGS_DIRECTORY = args.serialLogsDirectory
if args.configurationFile:
    config.CONFIGURATION_FILE = args.configurationFile
if args.managedPostMortemPacksDirectory:
    config.MANAGED_POST_MORTEM_PACKS_DIRECTORY = args.managedPostMortemPacksDirectory

with open(config.CONFIGURATION_FILE) as f:
    conf = yaml.load(f.read())
network.initialize_globals(conf)
hoststatemachine.HostStateMachine.ALLOW_CLEARING_OF_DISK = conf["ALLOW_CLEARING_OF_DISK"]
config.ARE_IPMI_COMMANDS_SYNCHRONOUS = conf["ARE_IPMI_COMMANDS_SYNCHRONOUS"]
logging.info("IPMI commands synchronous mode: %(syncMode)s",
             dict(syncMode=config.ARE_IPMI_COMMANDS_SYNCHRONOUS))

timer.TimersThread()
withLocalObjectStore = config.WITH_LOCAL_OBJECT_STORE
tftpbootInstance = tftpboot.TFTPBoot(
    netmask=network.NETMASK,
    inauguratorServerIP=network.BOOTSERVER_IP_ADDRESS,
    inauguratorServerPort=inaugurator.server.config.PORT,
    inauguratorGatewayIP=network.GATEWAY_IP_ADDRESS,
    osmosisServerIP=conf['OSMOSIS_SERVER_IP'],
    rootPassword=config.ROOT_PASSWORD,
    withLocalObjectStore=withLocalObjectStore)
dnsmasq.DNSMasq.eraseLeasesFile()
dnsmasq.DNSMasq.killAllPrevious()
dnsmasqInstance = dnsmasq.DNSMasq(
    tftpboot=tftpbootInstance,
    serverIP=network.BOOTSERVER_IP_ADDRESS,
    netmask=network.NETMASK,
    firstIP=network.FIRST_IP,
    lastIP=network.LAST_IP,
    gateway=network.GATEWAY_IP_ADDRESS,
    nameserver=network.BOOTSERVER_IP_ADDRESS)
inaugurateInstance = inaugurate.Inaugurate(config.RABBIT_MQ_DIRECTORY)
publishInstance = publish.Publish("ampq://localhost:%d/%%2F" % inaugurator.server.config.PORT)
hostsInstance = hosts.Hosts()
freePool = freepool.FreePool(hostsInstance)
allocationsInstance = allocations.Allocations(
    broadcaster=publishInstance, hosts=hostsInstance, freePool=freePool,
    osmosisServer=conf['OSMOSIS_SERVER_IP'])
reclaimHost = reclaimhost.ReclaimHost(hostsInstance,
                                      config.RECLAMATION_REQUESTS_FIFO_PATH,
                                      config.SOFT_RECLAMATION_FAILURE_MSG_FIFO_PATH)
dynamicConfig = dynamicconfig.DynamicConfig(
    hosts=hostsInstance,
    dnsmasq=dnsmasqInstance,
    inaugurate=inaugurateInstance,
    tftpboot=tftpbootInstance,
    freePool=freePool,
    allocations=allocationsInstance,
    reclaimHost=reclaimHost)
ipcServer = ipcserver.IPCServer(
    osmosisServerIP=conf['OSMOSIS_SERVER_IP'],
    dnsmasq=dnsmasqInstance,
    allocations=allocationsInstance,
    hosts=hostsInstance,
    dynamicConfig=dynamicConfig,
    reclaimHost=reclaimHost)


def serialLogFilename(vmID):
    with globallock.lock():
        return hostsInstance.byID(vmID).hostImplementation().serialLogFilename()


def createPostMortemPackForAllocationID(allocationID):
    with globallock.lock():
        return allocationsInstance.byIndex(int(allocationID)).createPostMortemPack()


log.startLogging(sys.stderr)
root = httprootresource.HTTPRootResource(
    serialLogFilename, createPostMortemPackForAllocationID,
    config.MANAGED_POST_MORTEM_PACKS_DIRECTORY)
reactor.listenTCP(args.httpPort, server.Site(root))
reactor.listenTCP(args.requestPort, transportserver.TransportFactory(ipcServer.handle))
logging.info("Physical RackAttack up and running")
reactor.run()
