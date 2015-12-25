import os
import logging
import unittest
import itertools
import rackattack


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


def importAllModulesToMakeThemAppearInCoverageReport():
    blackList = ["rackattack.physical.logconfig"]
    dirLists = [[os.path.join(item[0], filename) for filename in item[2]] for item in os.walk("rackattack")]
    files = list(itertools.chain(*dirLists))
    pythonFiles = [_file for _file in files if _file.endswith(".py")]
    testPath = os.path.join("rackattack", "physical", "tests")
    productionFiles = [_file for _file in pythonFiles if not _file.startswith(testPath)]
    productionFilesWithoutMain = [_file for _file in productionFiles if "main" not in
                                  os.path.basename(_file)]
    modules = [_file.replace(os.path.sep, ".").split(".py")[0] for _file in productionFilesWithoutMain]
    modules = [module for module in modules if module not in blackList]
    for module in modules:
        if module.endswith(".__init__"):
            module = module.rstrip(".__init__")
        __import__(module)

if __name__ == "__main__":
    importAllModulesToMakeThemAppearInCoverageReport()
    if "VERBOSITY" not in os.environ:
        maxVerbosity = max(logLevels.keys())
        print "Note: For different verbosity levels, run with VERBOSITY=(number from 0 to " \
              "%(maxVerbosity)s)." % dict(maxVerbosity=maxVerbosity)
    suite = unittest.TestLoader().discover('.', "test_*.py")
    verbosity = int(os.getenv("VERBOSITY", 0))
    configureLogging(verbosity)
    unittest.TextTestRunner(verbosity=verbosity).run(suite)
