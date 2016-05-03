import os
import sys
import time
import random
from rackattack.common import softreclaim
from rackattack.physical.tests.integration.main import (useFakeRackConf, useFakeIPMITool,
                                                        useFakeGeneralConfiguration, FAKE_REBOOTS_PIPE_NAME)


ORIG_SOFT_RECLAIM = softreclaim.SoftReclaim
fakeRebootRequestfd = None


class FakeSoftReclaim(ORIG_SOFT_RECLAIM):
    def __init__(self,
                 hostID,
                 hostname,
                 username,
                 password,
                 macAddress,
                 targetDevice,
                 isInauguratorActive,
                 maxUptime,
                 inauguratorCommandLine,
                 softReclamationFailedMsgFifoWriteFd,
                 inauguratorKernel,
                 inauguratorInitRD):
        self._hostID = hostID
        hostname = "10.0.0.101"
        username = "root"
        password = "strato"
        macAddress = hostID + "-primary-mac"
        self._ipmiHostname = hostID + "-fake-ipmi"
        assert hasattr(self, "_KEXEC_CMD")
        self._KEXEC_CMD = "echo"
        ORIG_SOFT_RECLAIM.__init__(self,
                                   hostID,
                                   hostname,
                                   username,
                                   password,
                                   macAddress,
                                   targetDevice,
                                   isInauguratorActive,
                                   maxUptime,
                                   inauguratorCommandLine,
                                   softReclamationFailedMsgFifoWriteFd,
                                   inauguratorKernel,
                                   inauguratorInitRD)

    def run(self):
        logging.info("Faking kexec reset by physically restarting host %(id)s", dict(id=self._hostID))
        ORIG_SOFT_RECLAIM.run(self)
        self._informFakeConsumersManagerOfReboot()

    def _informFakeConsumersManagerOfReboot(self):
        hostRequest = "%(hostname)s," % dict(hostname=self._ipmiHostname)
        hostRequest = hostRequest.encode("utf-8")
        before = time.time()
        os.write(fakeRebootRequestfd, hostRequest)
        after = time.time()
        print("Writing to fake reboots fifo took %(amount)s seconds" % dict(amount=before - after))

    def _validateUptime(self):
        uptime = self._getUptime()
        if random.randint(0, 9) == 0:
            raise softreclaim.UptimeTooLong(100000)

    def _reclaimByKexec(self):
        self._connection.ftp.putFile("/tmp/vmlinuz-%s" % (self._hostID,), self._inauguratorKernel)
        self._connection.ftp.putFile("/tmp/initrd-%s" % (self._hostID,), self._inauguratorInitRD)
        self._connection.run.script(
            "%s --load /tmp/vmlinuz --initrd=/tmp/initrd --append='%s'" %
            (self._KEXEC_CMD,
             self._inauguratorCommandLine(self._hostID, self._macAddress, self._hostname, clearDisk=False,
                                          targetDevice=self._targetDevice)))
        self._connection.run.backgroundScript("sleep 2; %s -e" % (self._KEXEC_CMD,))


if __name__ == "__main__":
    useFakeRackConf()
    useFakeIPMITool()
    useFakeGeneralConfiguration()
    print("Opening fake reboot manager's request fifo write end")
    global fakeRebootRequestfd
    if not os.path.exists(FAKE_REBOOTS_PIPE_NAME):
        os.mkfifo(FAKE_REBOOTS_PIPE_NAME)
    fakeRebootRequestfd = os.open(FAKE_REBOOTS_PIPE_NAME, os.O_WRONLY)
    print("Fifo open.")
    assert hasattr(softreclaim, "SoftReclaim")
    softreclaim.SoftReclaim = FakeSoftReclaim
    # Cannot import main since python does not support spwaning threads from an import context
    mainPath = os.path.join(os.curdir, "rackattack", "physical", "main_reclamationserver.py")
    execfile(mainPath)
    neverEnds = threading.Event()
    neverEnds.wait()
