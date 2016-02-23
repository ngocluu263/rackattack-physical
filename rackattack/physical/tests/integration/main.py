import os
import sys
import yaml
import random
import tempfile
import threading
from rackattack.physical.tests.integration import use_local_inaugurator
import rackattack.physical.config
from rackattack.physical.ipmi import IPMI


use_local_inaugurator.verify()


VAR_DIRPATH = os.path.join("/var", "lib", "rackattackphysical")
RACK_CONFIG_FILE_PATH = os.path.join(VAR_DIRPATH, "integration-test.rack.yaml")
FAKE_REBOOTS_PIPE_NAME = os.path.join(VAR_DIRPATH, "fake-reboots-pipe")
GENERAL_CONFIG_FILE_PATH = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..",
                                                         rackattack.physical.config.EXAMPLE_YAML))


def useFakeRackConf():
    assert hasattr(rackattack.physical.config, "RACK_YAML")
    rackattack.physical.config.RACK_YAML = RACK_CONFIG_FILE_PATH


def useFakeIPMITool():
    assert hasattr(IPMI, "IPMITOOL_FILENAME")
    IPMI.IPMITOOL_FILENAME = "sh/ipmitool_mock"


def useFakeGeneralConfiguration():
    rackattack.physical.config.CONFIGURATION_FILE = GENERAL_CONFIG_FILE_PATH

if __name__ == "__main__":
    if not os.path.exists(VAR_DIRPATH):
        os.makedirs(VAR_DIRPATH)
    useFakeRackConf()
    useFakeIPMITool()
    useFakeGeneralConfiguration()
    nrRacks = 1
    nrHostsInRack = 8
    hosts = [dict(id="rack%02d-server%02d" % (rackIdx, hostIdx),
                  ipmiLogin=dict(username="root",
                                 password="strato",
                                 hostname="rack%02d-server%02d-fake-ipmi" % (rackIdx, hostIdx)),
                  primaryMAC="rack%02d-server%02d-primary-mac" % (rackIdx, hostIdx),
                  secondaryMAC="rack%02d-server%02d-secondary-mac" % (rackIdx, hostIdx),
                  topology=dict(rackID="rack%02d" % (rackIdx,)),
                  state="online") for hostIdx in xrange(1, nrHostsInRack + 1)
             for rackIdx in xrange(1, nrRacks + 1)]
    rackConf = dict(HOSTS=hosts)
    with open(rackattack.physical.config.RACK_YAML, "w") as configFile:
        yaml.dump(rackConf, configFile)
    # Cannot import main since python does not support spwaning threads from an import context
    mainPath = os.path.join(os.curdir, "rackattack", "physical", "main.py")
    execfile(mainPath)
    neverEnds = threading.Event()
    neverEnds.wait()
