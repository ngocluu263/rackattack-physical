import subprocess
import time
import logging
import multiprocessing.pool


class IPMI:
    _CONCURRENCY = 4
    IPMITOOL_FILENAME = "ipmitool"
    _pool = None

    def __init__(self, hostname, username, password):
        self._hostname = hostname
        self._username = username
        self._password = password
        if IPMI._pool is None:
            IPMI._pool = multiprocessing.pool.ThreadPool(self._CONCURRENCY)

    def off(self):
        IPMI._pool.apply_async(self._powerCommand, args=("off",))

    def powerCycle(self):
        IPMI._pool.apply_async(self._powerCycle)

    def _powerCycle(self):
        self._powerCommand("off")
        self._powerCommand("on")

    def _powerCommand(self, command):
        NUMBER_OF_RETRIES = 10
        cmdLine = [
            "ipmitool", "power", command,
            "-H", str(self._hostname), "-U", self._username, "-P", self._password]
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
