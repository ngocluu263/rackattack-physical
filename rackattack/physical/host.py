from rackattack.physical import ipmi
from rackattack.physical import network
from rackattack.physical import config
from rackattack.physical import serialoverlan
import logging


class Host:
    DEFAULT_POOL = "default"

    def __init__(self, index, id, ipmiLogin, primaryMAC, secondaryMAC, topology, pool=None, isOnline=True):
        self._index = index
        self._id = id
        self._ipmiLogin = ipmiLogin
        self._primaryMAC = primaryMAC
        self._secondaryMAC = secondaryMAC
        self._topology = topology
        if pool is None:
            pool = self.DEFAULT_POOL
        self._pool = pool
        self._isOnline = isOnline
        self._ipmiLogin = ipmiLogin
        self._ipmi = ipmi.IPMI(**ipmiLogin)
        self._sol = None
        self._solFilename = None

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

    def pool(self):
        return self._pool

    def setPool(self, pool):
        if pool != self._pool:
            logging.info("Moving host %(hostID)s from pool %(oldPool)s to %(newPool)s",
                         dict(hostID=self._id, oldPool=self._pool, newPool=pool))
            self._pool = pool

    def rootSSHCredentials(self):
        return dict(hostname=self.ipAddress(), username="root", password=config.ROOT_PASSWORD)

    def validateSOLStarted(self):
        if self._sol is None:
            self._sol = serialoverlan.SerialOverLan(hostID=self._id, **self._ipmiLogin)
            self._solFilename = self._sol.serialLogFilename()

    def turnOff(self):
        logging.info("Turning off host %(id)s", dict(id=self._id))
        self._ipmi.off()
        if self._sol is not None:
            self._sol.stop()
            self._sol = None

    def destroy(self):
        logging.info("Host %(id)s destroyed", dict(id=self._id))

    def fulfillsRequirement(self, requirement):
        requestedPool = requirement.get("pool", self.DEFAULT_POOL)
        if requestedPool is None:
            requestedPool = self.DEFAULT_POOL
        if requestedPool != self.pool():
            return False
        return True

    def serialLogFilename(self):
        if self._solFilename is None:
            logging.error("SOL filename requested for host %(id)s with no SOL")
            raise Exception("SOL hasn't started")
        return self._solFilename

    def truncateSerialLog(self):
        if self._sol is None:
            return
        self._sol.truncateSerialLog()

    def reconfigureBIOS(self):
        logging.warning("Implement me!")

    def ipmiLoginCredentials(self):
        return self._ipmiLogin

    def isOnline(self):
        return self._isOnline

    def setIsOnline(self, isOnline):
        self._isOnline = isOnline
