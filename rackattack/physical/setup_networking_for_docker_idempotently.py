import os
import re
import sys
import json
import yaml
import subprocess
from rackattack.physical import config


BRIDGE_NAME = "brrackattacklxc"


class InvalidConfigurationFile(Exception):
    pass


def printExampleConfigurationFileDetails():
    print "A descriptive example configuration file can be found in '%(exampleConfigFilePath)s'" % \
        dict(exampleConfigFilePath=config.EXAMPLE_CONF_YAML)


def execCommand(command):
    return subprocess.check_output(command, stderr=sys.stdout)


def deleteIPAddressFromInterface(interface):
    print "Clearing the IP address from the interface '%(interface)s'..." % dict(interface=interface)
    cmd = ["ifconfig", interface, "0.0.0.0"]
    execCommand(cmd)


def validateConfiguration(configuration):
    if configuration["INNER_INTERFACE_IP_IN_DOCKER_HOST"] == configuration["BOOTSERVER_IP"]:
        print "Invalid configuration file: The chosen IP server for the container (BOOTSERVER_IP) " \
              "cannot be identical to that of the docker host (INNER_INTERFACE_IP_IN_DOCKER_HOST)."
        printExampleConfigurationFileDetails()


def parseConfiguration(configFilePath):
    if not os.path.exists(configFilePath):
        print "Please put a configuration file for Rackattack in: '%(configFilePath)s'." % \
              dict(configFilePath=configFilePath)
        raise InvalidConfigurationFile()
    try:
        with open(configFilePath, "r") as configFile:
            configuration = yaml.load(configFile)
    except yaml.scanner.ScannerError:
        print "Invalid YAML structure in configuration file. Cannot continue."
        raise InvalidConfigurationFile()
    for parameter in ("INNER_INTERFACE_NAME_IN_DOCKER_HOST", "INNER_INTERFACE_IP_IN_DOCKER_HOST"):
        if parameter not in configuration or configuration[parameter] == "UNDEFINED":
            print "Please set the '%(parameter)s' parameter in the configuration file " \
                  "'%(configFilePath)s' an try again." % \
                  dict(parameter=parameter, configFilePath=configFilePath)
            raise InvalidConfigurationFile()
    validateConfiguration(configuration)
    return configuration


def createBridgeToContainer(containerID, configuration, pipeWorkScriptPath):
    print "Creating a second bridge by the name of '%(bridge)s' to Rackattack's container..." % \
          dict(bridge=BRIDGE_NAME)
    providerIPAddressCIDRNotation = "%(bootServerIP)s/%(prefixLength)s" % \
                                    dict(bootServerIP=configuration["BOOTSERVER_IP"],
                                         prefixLength=configuration["NODES_SUBNET_PREFIX_LENGTH"])
    cmd = [pipeWorkScriptPath, BRIDGE_NAME, containerID, providerIPAddressCIDRNotation]
    try:
        execCommand(cmd)
    except:
        print "An error has occurred while creating a bridge to the container using the pipework script."
        raise


def isInterfaceAssociatedWithBridge(interface, bridge):
    cmd = ["brctl", "show", bridge]
    info = execCommand(cmd)
    lines = info.splitlines()[1:]
    match = [line for line in lines if line.endswith("\t" + interface)]
    return bool(match)


def associateInterfaceWithBridge(interface, bridge):
    print "Associating the interface '%(interface)s to the network bridge '%(bridge)s'..." % \
          dict(interface=interface, bridge=bridge)
    if isInterfaceAssociatedWithBridge(interface, bridge):
        print "The interface is already associated with the bridge."
        return
    cmd = ["brctl", "addif", bridge, interface]
    execCommand(cmd)


def associateAddressWithBridge(ipAddress, bridge):
    print "Associating IP address %(ipAddress)s with the bridge '%(bridge)s..." % \
          dict(ipAddress=ipAddress, bridge=bridge)
    cmd = ["ifconfig", bridge, ipAddress]
    execCommand(cmd)


def validateContainerIsRunning(containerID):
    cmd = ["docker", "inspect", containerID]
    try:
        stats = execCommand(cmd)
    except:
        print "Could get info about a container with an ID of %(containerID)s. Cannot continue. " \
              "Please validate that the docker daemon and such a container are running." % \
              dict(containerID=containerID)
        sys.exit(1)
    try:
        info = json.loads(stats)
    except:
        print "Invalid JSON format received from the docker daemon about the container %(containerID)s. " \
              "Cannot continue." % dict(containerID=containerID)
        sys.exit(1)
    if not info:
        print "A container by the given ID %(containerID)s is currently not running. Cannot continue." % \
              dict(containerID=containerID)
        sys.exit(1)
    if len(info) > 1:
        print "It seems that multiple containers with the ID %(containerID)s are present. Cannot ." \
              "continue." % dict(containerID=containerID)
        sys.exit(1)
    containerInfo = info[0]
    try:
        isRunning = containerInfo["State"]["Running"]
    except:
        print "Unrecognized JSON format received from the docker daemon about the container " \
              "%(containerID)s. Cannot continue." % dict(containerID=containerID)
        sys.exit(1)
    if not isRunning:
        print "A container by the given ID is not running. Cannot continue."
        sys.exit(1)


def main():
    _, containerID, pipeWorkScriptPath = sys.argv
    validateContainerIsRunning(containerID)
    try:
        configuration = parseConfiguration(config.CONFIGURATION_FILE)
    except InvalidConfigurationFile:
        printExampleConfigurationFileDetails()
        sys.exit(1)
    deleteIPAddressFromInterface(configuration["INNER_INTERFACE_NAME_IN_DOCKER_HOST"])
    createBridgeToContainer(containerID, configuration, pipeWorkScriptPath)
    associateInterfaceWithBridge(configuration["INNER_INTERFACE_NAME_IN_DOCKER_HOST"], BRIDGE_NAME)
    associateAddressWithBridge(configuration["INNER_INTERFACE_IP_IN_DOCKER_HOST"], BRIDGE_NAME)

if __name__ == "__main__":
    main()
