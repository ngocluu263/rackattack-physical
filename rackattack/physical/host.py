from rackattack.physical import ipmi
from rackattack.physical import network
from rackattack.physical import config
from rackattack.physical import serialoverlan
import logging
import enum
import re


class Enum(set):
    def __getattr__(self, name):
            if name in self:
                    return name
            raise AttributeError


STATES = Enum(["ONLINE", "OFFLINE", "DETACHED"])


class Host:
    DEFAULT_POOL = "default"
    DEFAULT_TARGET_DEVICE = None
    DEFAULT_TARGET_DEVICE_TYPE = None
    NR_TRUNCATION_CALLS_BEFORE_ACTUAL_TRUNCATION = 5

    def __init__(self, index, id, ipmiLogin, primaryMAC, secondaryMAC, topology, state, pool=None,
                 targetDevice=None, NICBondings=None, targetDeviceType=None, otherMACAddresses=None,
                 serialPort=0):
        self._index = index
        self._id = id
        self._ipmiLogin = ipmiLogin
        self._primaryMAC = primaryMAC
        self._secondaryMAC = secondaryMAC
        self._topology = topology
        if pool is None:
            pool = self.DEFAULT_POOL
        self._pool = pool
        self.setState(state)
        self._ipmiLogin = ipmiLogin
        self._ipmi = ipmi.IPMI(**ipmiLogin)
        self._sol = None
        self._solFilename = None
        if targetDevice is None:
            targetDevice = self.DEFAULT_TARGET_DEVICE
        self._targetDevice = targetDevice
        if targetDeviceType is None:
            targetDeviceType = self.DEFAULT_TARGET_DEVICE_TYPE
        self._targetDeviceType = targetDeviceType
        self._NICBondings = None
        if NICBondings is None:
            NICBondings = list()
        self.setNICBondings(NICBondings)
        self._otherMACAddresses = None
        if otherMACAddresses is None:
            otherMACAddresses = dict()
        self.setOtherMACAddresses(otherMACAddresses)
        self._nrTruncationCalls = 0
        self._serialPort = serialPort
        self._reasonForDestruction = None

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

    def destroy(self, reason=None):
        logging.info("Host %(id)s destroyed", dict(id=self._id))
        if reason is not None:
            self._reasonForDestruction = reason

    def fulfillsRequirement(self, requirement):
        requestedPool = requirement.get("pool", self.DEFAULT_POOL)
        if requestedPool is None:
            requestedPool = self.DEFAULT_POOL
        if requestedPool != self.pool():
            return False
        minimumNrNICBondings = requirement.get("hardwareConstraints", dict()).get("minimumNrNICBondings", 0)
        if len(self.getNICBondings()) < minimumNrNICBondings:
            return False
        maximumNrNICBondings = requirement.get("hardwareConstraints", dict()).get("maximumNrNICBondings",
                                                                                  None)
        if maximumNrNICBondings is not None:
            assert isinstance(maximumNrNICBondings, int)
            if len(self.getNICBondings()) > minimumNrNICBondings:
                return False
        wildcard = requirement.get("serverIDWildcard", None)
        if wildcard is not None and wildcard:
            assert isinstance(wildcard, str), str(wildcard)
            if not self._doesSearchTermMatchWildcardPattern(self._id, wildcard):
                return False
        return True

    def serialLogFilename(self):
        if self._solFilename is None:
            logging.error("SOL filename requested for host %(id)s with no SOL", dict(id=self._id))
            raise Exception("SOL hasn't started")
        return self._solFilename

    def truncateSerialLogEveryNCalls(self):
        self._nrTruncationCalls += 1
        if self._nrTruncationCalls > self.NR_TRUNCATION_CALLS_BEFORE_ACTUAL_TRUNCATION:
            self._nrTruncationCalls = 0
            self.truncateSerialLog()

    def truncateSerialLog(self):
        if self._sol is None:
            return
        self._sol.truncateSerialLog()

    def reconfigureBIOS(self):
        logging.warning("Implement me!")

    def ipmiLoginCredentials(self):
        return self._ipmiLogin

    def state(self):
        return self._state

    def setState(self, state):
        assert state in STATES, state
        self._state = state

    def targetDevice(self):
        return self._targetDevice

    def setTargetDevice(self, targetDevice):
        if targetDevice != self._targetDevice:
            logging.info("Changing target device of %(hostID)s from %(old)s to %(new)s",
                         dict(hostID=self._id, old=self._targetDevice, new=targetDevice))
            self._targetDevice = targetDevice

    def targetDeviceType(self):
        return self._targetDeviceType

    def setTargetDeviceType(self, targetDeviceType):
        if targetDeviceType != self._targetDeviceType:
            logging.info("Changing target device type of %(hostID)s from %(old)s to %(new)s",
                         dict(hostID=self._id, old=self._targetDeviceType, new=targetDeviceType))
            self._targetDeviceType = targetDeviceType

    def getNICBondings(self):
        return self._NICBondings

    def setNICBondings(self, NICBondings):
        assert isinstance(NICBondings, list)
        if NICBondings != self._NICBondings:
            logging.info("Changing NIC bonding lists of %(hostID)s from %(old)s to %(new)s",
                         dict(hostID=self._id, old=self._NICBondings, new=NICBondings))

            self._NICBondings = NICBondings

    def setOtherMACAddresses(self, otherMACAddresses):
        assert isinstance(otherMACAddresses, dict)
        if otherMACAddresses != self._otherMACAddresses:
            logging.info("Changing list of other MAC addresses of %(hostID)s from %(old)s to %(new)s",
                         dict(hostID=self._id, old=self._otherMACAddresses, new=otherMACAddresses))
        self._otherMACAddresses = otherMACAddresses

    def getOtherMACAddresses(self):
        return self._otherMACAddresses

    def getSerialPort(self):
        return self._serialPort

    def setSerialPort(self, serialPort):
        assert isinstance(serialPort, int)
        if serialPort != self._serialPort:
            logging.info("Changing serial port of %(hostID)s from %(old)s to %(new)s",
                         dict(hostID=self._id, old=self._serialPort, new=serialPort))
        self._serialPort = serialPort

    @staticmethod
    def _doesSearchTermMatchWildcardPattern(searchTerm, wildcard):
        regexPattern = ".*".join([re.escape(part) for part in wildcard.split("*")]) + "$"
        regex = re.compile(regexPattern)
        return regex.match(searchTerm) is not None

    def getReasonForDestruction(self):
        return self._reasonForDestruction
