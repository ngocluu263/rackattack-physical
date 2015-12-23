import time
import logging
import multiprocessing.pool


from rackattack.physical.ipmi import IPMI


class ColdReclaim:
    _MAX_NR_RETRIES = 5
    _RETRY_INTERVAL = 10
    _CONCURRENCY = 8
    _pool = None

    def __init__(self, hostname, username, password, hardReset):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._hardReset = hardReset
        if ColdReclaim._pool is None:
            ColdReclaim._pool = multiprocessing.pool.ThreadPool(self._CONCURRENCY)
        callback = self._run
        ColdReclaim._pool.apply_async(callback)

    def _run(self):
        ipmi = IPMI(self._hostname, self._username, self._password)
        for retry in xrange(self._MAX_NR_RETRIES):
            try:
                if self._hardReset == "True":
                    ipmi.powerCycle()
                else:
                    ipmi.softReset()
                return
            except:
                logging.exception("Unable to reclaim by cold restart '%(hostname)s'",
                                  dict(hostname=self._hostname))
                time.sleep(self._RETRY_INTERVAL)
        raise Exception("Cold restart retries exceeded '%(hostname)s'" % dict(hostname=self._hostname))
