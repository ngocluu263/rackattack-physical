#!/usr/bin/python

import subprocess
import argparse
import os

parser = argparse.ArgumentParser(
    prog='ipmi command send',
    description='send ipmi commands using ipmitool to multiple rackattack servers',
)
group1 = parser.add_mutually_exclusive_group(required=True)
group1.add_argument('--file', '-f', default=None, help='white space separated file conataing rackattack server names')
group1.add_argument('--serverList', '-s', metavar="rackXX-serverYY", nargs="+", help='white space separated input of rackattack server names')
parser.add_argument('--cmd', '-c', default='chassis power status', help='default ipmi-tool command. will be appended to ipmitool -I lanplus -U root -P strato')
args = parser.parse_args()

class sendIpmiCommand(object):

    IPMI_TOOL_PATH = '/usr/bin/ipmitool'
    IPMI_SERVER_POSTFIX = '-ipmi.dc1.strato'
    IPMI_USER = 'root'
    IPMI_PASSWORD = 'strato'

    def __init__(self, serverList, cmd):
        self._serverList = serverList
	self._cmd = cmd
    
    def runCommand(self, cmd):
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        return process.communicate()[0]

    def runOnAll(self):
        for server in self._serverList:
            cmd = '%(_ipmi)s -I lanplus -U %(_user)s -P %(_pass)s %(_cmd)s -H %(_server)s%(_postfix)s' % dict(_ipmi=self.IPMI_TOOL_PATH, _user=self.IPMI_USER, _cmd=self._cmd, _pass=self.IPMI_PASSWORD, _server=server, _postfix=self.IPMI_SERVER_POSTFIX)
            print '%(_server)s: %(_out)s' % dict(_server=server, _out=self.runCommand(cmd))

if __name__ == '__main__':
    serverList = []
    if args.file:
        if not os.path.isfile(args.file):
            print 'file %s does not exist' % args.file
        else:
            with open(args.file) as f:
                for line in f.readlines():
                    serverList += line.strip().split()
    else:
        serverList += args.serverList

    runner = sendIpmiCommand(serverList, args.cmd)
    runner.runOnAll()

