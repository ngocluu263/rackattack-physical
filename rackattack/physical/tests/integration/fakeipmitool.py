import os
import time
import yaml
import random
import argparse
from rackattack.physical import pikapatch
from rackattack.physical.tests.integration.main import useFakeRackConf, useFakeIPMITool


intervalRanges = {0: (0.01, 0.05), 0.85: (0.3, 0.6), 0.95: (2, 4)}
rangesProbabilities = intervalRanges.keys()
rangesProbabilities.sort()


def informFakeConsumersManagerOfReboot(hostname):
    rebootsPipe = os.environ["FAKE_REBOOTS_PIPE_PATH"]
    fd = os.open(rebootsPipe, os.O_WRONLY)
    os.write(fd, "%(hostname)s," % dict(hostname=hostname))
    os.close(fd)


def power(mode):
    time.sleep(0.02)
    if mode == "on":
        informFakeConsumersManagerOfReboot(args.H)
        print "Chassis Power Control: Up/On"
    elif mode == "off":
        print "Chassis Power Control: Down/Off"
    else:
        raise NotImplementedError


def sol(subaction):
    if subaction != "activate":
        return
    possibleOutputLines = ("Yo yo i'm a cool server",
                           "This server has got swag.",
                           "Wow this totally looks like a serial log of a linux server",
                           "asdasd")
    while True:
        withinBound = random.random()
        chosenRangeProbability = \
            [rangeProb for rangeProb in rangesProbabilities if rangeProb <= withinBound][-1]
        chosenRange = intervalRanges[chosenRangeProbability]
        interval = chosenRange[0] + random.random() * (chosenRange[1] - chosenRange[0])
        time.sleep(interval)
        print random.choice(possibleOutputLines)


def main(args):
    useFakeRackConf()
    useFakeIPMITool()
    if args.I != "lanplus":
        assert args.I is None
    action = dict(power=power, sol=sol).get(args.action)
    action(args.subaction)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-I", default=None, type=str)
    parser.add_argument("-H", default=None, type=str)
    parser.add_argument("-U", default=None, type=str)
    parser.add_argument("-P", default=None, type=str)
    parser.add_argument("-R", default=1, type=int)
    parser.add_argument("action", default=None, type=str)
    parser.add_argument("subaction", default=None, type=str)
    args = parser.parse_args()
    main(args)
