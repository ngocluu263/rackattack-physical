import time
import logging
import multiprocessing.pool
from rackattack.physical import config
from rackattack.physical.ipmi import IPMI


class ColdReclaim:
    _CONCURRENCY = 8
    _pool = None

    def __init__(self, hostname, username, password, hardReset):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._hardReset = hardReset
        if config.ARE_IPMI_COMMANDS_SYNCHRONOUS:
            self._commandsInterval = 1
        else:
            self._commandsInterval = 15
        if ColdReclaim._pool is None:
            ColdReclaim._pool = multiprocessing.pool.ThreadPool(self._CONCURRENCY)
        ColdReclaim._pool.apply_async(self._run)

    def _run(self):
        ipmi = IPMI(self._hostname, self._username, self._password)
        try:
            ipmi._powerCommand("off")
            time.sleep(self._commandsInterval)
            ipmi._powerCommand("on")
#            if self._hardReset == "True":
#                ipmi.powerCycle()
#            else:
#                ipmi.softReset()
        except:
            logging.exception("Unable to reclaim by cold restart '%(hostname)s'",
                              dict(hostname=self._hostname))
