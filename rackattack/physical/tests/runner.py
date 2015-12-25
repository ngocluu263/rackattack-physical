import os
import logging
import unittest


logLevels = {0: logging.CRITICAL + 1,
             1: logging.CRITICAL,
             2: logging.CRITICAL,
             3: logging.WARNING,
             4: logging.INFO,
             5: logging.DEBUG}


def configureLogging(verbosity):
    logger = logging.getLogger()
    maxVerbosity = max(logLevels.keys())
    if verbosity > maxVerbosity:
        verbosity = maxVerbosity
    elif verbosity < 0:
        verbosity = 0
    logLevel = logLevels[verbosity]
    logger.setLevel(logLevel)


if __name__ == "__main__":
    if "VERBOSITY" not in os.environ:
        maxVerbosity = max(logLevels.keys())
        print "Note: For different verbosity levels, run with VERBOSITY=(number from 0 to " \
              "%(maxVerbosity)s)." % dict(maxVerbosity=maxVerbosity)
    suite = unittest.TestLoader().discover('.', "test_*.py")
    verbosity = int(os.getenv("VERBOSITY", 0))
    configureLogging(verbosity)
    unittest.TextTestRunner(verbosity=verbosity).run(suite)
