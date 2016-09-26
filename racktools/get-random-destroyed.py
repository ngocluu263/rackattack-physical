#!/bin/python
import subprocess
import yaml
import random

status = yaml.load(subprocess.check_output('RACKATTACK_PROVIDER=tcp://rackattack-provider.dc1.strato:1014@@amqp://guest:guest@rackattack-provider.dc1.strato:1013@@http://rackattack-provider.dc1.strato:1016 UPSETO_JOIN_PYTHON_NAMES_SPACES=Yes PYTHONPATH=~/work/rackattack-api/py/ python /root/racktools/getStatus.py', shell=True))
# Try to get nodes that are in default pool and are destroyed, if there are none, try to retest nodes that were tested but didn't get destroyed after initial test
toCheck = [host for host in status['hosts'] if host['pool'] == 'default' and host['state'] == 'DESTROYED']
if not len(toCheck):
	toCheck = [host for host in status['hosts'] if 'jenkins.dc1:8080/job/Check-node' in host['pool'] and host['state'] != 'DESTROYED']

if len(toCheck) > 0:
	print random.choice(toCheck)['id']
else:
	print ""

