import subprocess
import time
import logging
import multiprocessing.pool


class IPMI:
    IPMITOOL_FILENAME = "ipmitool"
    _CONCURRENCY = 4
    _pool = None

    def __init__(self, hostname, username, password):
        self._hostname = hostname
        self._username = username
        self._password = password
        if IPMI._pool is None:
            IPMI._pool = multiprocessing.pool.ThreadPool(self._CONCURRENCY)

    def off(self):
        IPMI._pool.apply_async(self._powerCommand, args=("off",))

    def asyncPowerCycle(self):
        IPMI._pool.apply_async(self.powerCycle)

    def powerCycle(self):
        self._powerCommand("off")
        time.sleep(1)
        self._powerCommand("on")

    def softReset(self):
        self._powerCommand("soft")

    def _command(self, *args):
        NUMBER_OF_RETRIES = 10
        cmdLine = [
            self.IPMITOOL_FILENAME, "-I", "lanplus",
            "-H", str(self._hostname), "-U", self._username, "-P", self._password]
        cmdLine.extend(args)
        for i in xrange(NUMBER_OF_RETRIES - 1):
            try:
                return subprocess.check_output(cmdLine, stderr=subprocess.STDOUT, close_fds=True)
            except:
                time.sleep(0.1)
        try:
            return subprocess.check_output(cmdLine, stderr=subprocess.STDOUT, close_fds=True)
        except subprocess.CalledProcessError as e:
            logging.error("Output: %(output)s", dict(output=e.output))
            raise

    def _powerCommand(self, command):
        if command == "on":
            self._command("chassis", "bootdev", "pxe")
        time.sleep(1)
        self._command("power", command)
