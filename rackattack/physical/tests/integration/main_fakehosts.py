import os
import logging
import threading
from rackattack.physical import pikapatch, config
from rackattack.physical.tests.integration import fakehosts
from rackattack.physical.tests.integration.main import (useFakeRackConf, useFakeIPMITool,
                                                        useFakeGeneralConfiguration)


def configureLogging():
    for loggerName in ("fakeConsumersServer", "pipeListener"):
        _logger = logging.getLogger(loggerName)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(name)s: %(message)s')
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
        _logger.setLevel(logging.DEBUG)
        _logger.propagate = False

if __name__ == "__main__":
    fakeRebootsPipePath = os.environ["FAKE_REBOOTS_PIPE_PATH"]
    useFakeRackConf()
    useFakeIPMITool()
    useFakeGeneralConfiguration()
    configureLogging()
    fakeHostsServer = fakehosts.FakeHosts()
    fakeHostsServer.run()
