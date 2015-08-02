import os
import sys


def setupPath():
    inauguratorDir = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', "inaugurator")
    sys.path.insert(0, inauguratorDir)


def verify():
    import inaugurator
    for pathComponent in ('usr', 'build'):
        assert pathComponent not in inaugurator.__file__, inaugurator

setupPath()
