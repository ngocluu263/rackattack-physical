from rackattack.physical import ipmi
from rackattack.physical import network
from rackattack.physical import config
from rackattack.physical import serialoverlan
import logging


class Host:
    def __init__(self, index, id, ipmiLogin, primaryMAC, secondaryMAC, topology):
        self._index = index
        self._id = id
        self._ipmiLogin = ipmiLogin
        self._primaryMAC = primaryMAC
        self._secondaryMAC = secondaryMAC
        self._topology = topology
        self._ipmiLogin = ipmiLogin
        self._ipmi = ipmi.IPMI(**ipmiLogin)
        self._sol = None

    def index(self):
        return self._index

    def id(self):
        return self._id

    def primaryMACAddress(self):
        return self._primaryMAC

    def secondaryMACAddress(self):
        return self._secondaryMAC

    def ipAddress(self):
        return network.ipAddressFromHostIndex(self._index)

    def rootSSHCredentials(self):
        return dict(hostname=self.ipAddress(), username="root", password=config.ROOT_PASSWORD)

    def coldRestart(self):
        logging.info("Cold booting host %(id)s", dict(id=self._id))
        self._ipmi.powerCycle()
        if self._sol is None:
            self._sol = serialoverlan.SerialOverLan(hostID=self._id, **self._ipmiLogin)

    def turnOff(self):
        logging.info("Turning off host %(id)s", dict(id=self._id))
        self._ipmi.off()
        if self._sol is not None:
            self._sol.stop()
            self._sol = None

    def destroy(self):
        logging.info("Host %(id)s destroyed", dict(id=self._id))

    def fulfillsRequirement(self, requirement):
        return True

    def serialLogFilename(self):
        if self._sol is None:
            raise Exception("SOL stopped")
        return self._sol.serialLogFilename()

    def truncateSerialLog(self):
        if self._sol is None:
            return
        self._sol.truncateSerialLog()

    def reconfigureBIOS(self):
        logging.warning("Implement me!")
