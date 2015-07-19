import sys
import os
if 'PIKA_EGG_PATH' in os.environ:
    sys.path.insert(0, os.environ['PIKA_EGG_PATH'])
