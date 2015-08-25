import os
import yaml
import logging
import multiprocessing
import inaugurator.server.config
from rackattack.physical import config
from rackattack.physical import network
from rackattack.physical.coldreclaim import ColdReclaim
from rackattack.common.reclamationserver import ReclamationServer
from rackattack.physical.config import (RECLAMATION_REQUESTS_FIFO_PATH,
                                        SOFT_RECLAMATION_FAILURE_MSG_FIFO_PATH)


def configureLogger():
    logger = logging.getLogger("reclamation")
    logger.setLevel(logging.INFO)
    streamHandler = logging.StreamHandler()
    streamHandler.setLevel(logging.INFO)
    logger.addHandler(streamHandler)
    return logger


def main():
    logger = configureLogger()
    logger.info("Starting reclamation worker process. PID: %(pid)s", dict(pid=os.getpid()))
    with open(config.CONFIGURATION_FILE, "r") as f:
        conf = yaml.load(f.read())
    network.setGatewayIP(conf['GATEWAY_IP'])
    reclamationserver = ReclamationServer(network.NETMASK,
                                          conf['OSMOSIS_SERVER_IP'],
                                          network.BOOTSERVER_IP_ADDRESS,
                                          inaugurator.server.config.PORT,
                                          network.GATEWAY_IP_ADDRESS,
                                          config.ROOT_PASSWORD,
                                          config.WITH_LOCAL_OBJECT_STORE,
                                          RECLAMATION_REQUESTS_FIFO_PATH,
                                          SOFT_RECLAMATION_FAILURE_MSG_FIFO_PATH)
    reclamationserver.registerAction("cold", ColdReclaim)
    reclamationserver.run()

if __name__ == "__main__":
    pool = multiprocessing.Pool()
    pool.apply_async(main)
    main()
