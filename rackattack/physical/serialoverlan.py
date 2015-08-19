import logging
import pty
import os
import subprocess
import threading
import time
import signal
import errno
from rackattack.physical import config
from rackattack.tcp import suicide


class SerialOverLan(threading.Thread):
    def __init__(self, hostname, username, password, hostID):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._hostID = hostID
        self._stop = False
        self._popen = None
        self._serialFile = self._getSerialFilePath()
        threading.Thread.__init__(self)
        self.daemon = True
        self.start()

    def stop(self):
        logging.info("Stopping SOL for %(hostname)s", dict(hostname=self._hostname))
        self._stop = True
        popen = self._popen
        if popen is not None:
            popen.terminate()

    def serialLogFilename(self):
        return self._serialFile

    def truncateSerialLog(self):
        popen = self._popen
        if popen is None:
            return
        try:
            popen.send_signal(signal.SIGHUP)
        except OSError as e:
            if e.errno == errno.ESRCH:
                return
            raise

    def run(self):
        RETRIES = 10
        INTERVAL = 10
        for i in xrange(RETRIES):
            logging.info("trying to establish SOL connection to %(hostname)s", dict(
                hostname=self._hostname))
            stdin, self._popen = self._popenSOL()
            try:
                self._popen.wait()
            finally:
                os.close(stdin)
            self._popen = None
            if self._stop:
                logging.info('SOL thread for %(hostname)s exists', dict(hostname=self._hostname))
                return
            logging.error("SOL connection to %(hostname)s is broken", dict(hostname=self._hostname))
            time.sleep(INTERVAL)
        logging.error(
            "All retries to establish SOL connection to %(hostname)s failed", dict(
                hostname=self._hostname))

    def _popenSOL(self):
        self.truncateSerialLog()
        subprocess.call(self._getSolCommand("deactivate"))
        master, slave = pty.openpty()
        try:
            with open(self._serialFile, "w") as outputFile:
                return master, subprocess.Popen(
                    ['python', '-c', self._TRUNCER] + list(self._getSolCommand("activate")), stdin=slave,
                    stderr=subprocess.STDOUT, stdout=outputFile, close_fds=True)
        except:
            os.close(master)
            raise
        finally:
            os.close(slave)

    def _getSolCommand(self, action):
        NUMBER_OF_RETRIES = "10"
        return ("ipmitool", "-I", "lanplus", "-H", self._hostname,
                "-U", self._username, "-P", self._password, "sol", action, "-R", NUMBER_OF_RETRIES)

    def _getSerialFilePath(self):
        if not os.path.isdir(config.SERIAL_LOGS_DIRECTORY):
            os.makedirs(config.SERIAL_LOGS_DIRECTORY)
        return os.path.join(config.SERIAL_LOGS_DIRECTORY, self._hostID + "-serial.txt")

    _TRUNCER = \
        "import subprocess\n" \
        "import signal\n" \
        "import sys\n" \
        "import os\n" \
        "import pty\n" \
        "import errno\n" \
        "\n" \
        "\n" \
        "def setTruncateRequested(*args):\n" \
        "    global truncateRequested\n" \
        "    truncateRequested = True\n" \
        "\n" \
        "\n" \
        "truncateRequested = False\n" \
        "signal.signal(signal.SIGHUP, setTruncateRequested)\n" \
        "master, slave = pty.openpty()\n" \
        "popen = subprocess.Popen(sys.argv[1:], stdout=slave, stderr=subprocess.STDOUT)\n" \
        "os.close(slave)\n" \
        "while True:\n" \
        "    try:\n" \
        "        data = os.read(master, 4096)\n" \
        "    except OSError as e:\n" \
        "        if e.errno == errno.EINTR:\n" \
        "            continue\n" \
        "        raise\n" \
        "    if len(data) == 0:\n" \
        "        sys.exit(popen.wait())\n" \
        "    if truncateRequested:\n" \
        "        truncateRequested = False\n" \
        "        os.ftruncate(sys.stdout.fileno(), 0)\n" \
        "        os.lseek(sys.stdout.fileno(), 0, os.SEEK_SET)\n" \
        "    os.write(sys.stdout.fileno(), data)\n"
