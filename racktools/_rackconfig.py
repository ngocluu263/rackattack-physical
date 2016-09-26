from rackattack import clientfactory
import yaml
import subprocess
import signal
import time
import os
import sys
import shutil
import argparse
import lockfile
import pprint
from datetime import datetime
import tempfile

YAML = "/etc/rackattack.physical.rack.yaml"
RACKATTACK_LOCK = "/tmp/rackattack.conf"

BACKUP_GIT_REPO_URL = "http://github.com/Stratoscale/rootfs-rackattack-provider-bezeq"
BACKUP_GIT_REPO_CONFIGU_FILE_PATH = "etc/rackattack.physical.rack.yaml"

SERVER_STATES = ['detached', 'offline', 'online']



class RackattackConfig(object):
    def __init__(self, yamlConf=YAML):
        self._yaml = yaml.load(open(yamlConf))
        self._yamlConfPath = yamlConf
        self._client = clientfactory.factory()

    def updateState(self, servers, state):
        if state not in SERVER_STATES:
            print "Invalid state given"
            raise ValueError(state)
        self._update(servers, "state", state)

    def updatePool(self, servers, pool):
        assert pool is not None
        assert len(pool)
        self._update(servers, "pool", pool)

    def _validateServersExist(self, servers):
        # Verify all servers exist
        existingServers = [server['id'] for server in self._yaml['HOSTS']]
        nonExistingServers = set(servers) - set(existingServers)
        return
        assert not nonExistingServers, "Invalid servers: %s" % str(nonExistingServers)

    def _search(self, field, value):
        return [server['id'] for server in self._yaml['HOSTS'] if server[field] == value]
                
    def _update(self, servers, field, value):
        self._validateServersExist(servers)
        for server in self._yaml['HOSTS']:
            if server['id'] in servers:
                print 'Handling server %s: %s -> %s' % (server['id'], server.get(field, None), value)
                server[field] = value
        self._save(field, value)

    def _save(self, confChangeType, confChangeValue):
	confChangeValue = confChangeValue.replace("/",".")
        yamlBackupPath = "%s-%s-before-%s-%s" % (self._yamlConfPath,
                                                 datetime.now().strftime("%b-%d-%y-%H-%M-%S"),
                                                 confChangeType,
                                                 confChangeValue)
        shutil.copyfile(self._yamlConfPath, yamlBackupPath)
        yaml.dump(self._yaml, open(self._yamlConfPath, 'w'))

    def reloadConf(self):
        self._client.call("admin__asyncReloadConfiguration")

    def _show(self, field, value):
        servers = self._search(field, value)
        print "Number of servers in '%s' %s: %d" % (value, field, len(servers))
        print "\n".join(servers)

    def showServersInState(self, state):
        self._show("state", state)

    def showServersInPool(self, pool):
        self._show("pool", pool)

    def backup(self, gitrepo, path_inside_repo, args):
        print "Backing up the configuration file..."
        assert args.show is None or not args.show
        gitrepo_dir = tempfile.mkdtemp()
        try:
            print "\tCloning..."
            subprocess.check_output(["git", "clone", gitrepo, gitrepo_dir], stderr=subprocess.PIPE)
            os.chdir(gitrepo_dir)
            subprocess.check_output(["git", "checkout", "master"], stderr=subprocess.PIPE)
            if args.backup:
                message = "Backup configuration file"
            else:
                if args.state:
                    prop = "state"
                    value = args.state
                elif args.pool:
                    prop = "pool"
                    value = args.pool
                else:
                    raise Exception("Cannot create a backup commit message; Unknown operation")
                servers = ",".join(args.servers)
                message = "Change %(prop)s of servers %(servers)s to %(value)s" % \
                          dict(prop=prop, servers=servers, value=value)
            dest_path = os.path.join(gitrepo_dir, path_inside_repo)
            print "\tCopying configuration file to repository..."
            shutil.copy(args.yaml, dest_path)
            print "\tValidating that a diff exists..."
            output = subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.PIPE)
            if not output:
                print "\tNo need to backup. The configuration file is identical to that in origin/master"
                return
            print "\tCommiting..."
            subprocess.check_output(["git", "commit", "-am", message], stderr=subprocess.PIPE)
            print "\tPushing..."
            subprocess.check_output(["git", "push", "origin", "master"], stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as ex:
            print ex
        finally:
            shutil.rmtree(gitrepo_dir)
        print "\tBackup complete."


def setLocalRackattack():
    localProvider = "tcp://localhost:1014@@amqp://guest:guest@localhost:1013@@http://localhost:1016"
    os.environ["RACKATTACK_PROVIDER"] = localProvider

def main(args):
    if "RACKATTACK_PROVIDER" not in os.environ:
        setLocalRackattack()
    print "Acquiring the lock for the configuration file..."
    listOnly = args.show
    with lockfile.LockFile(RACKATTACK_LOCK):
        print "Lock acquired."
        rackCfg = RackattackConfig(args.yaml)
        if args.state:
            if listOnly:
                rackCfg.showServersInState(args.state)
            else:
                rackCfg.updateState(args.servers, args.state)
                rackCfg.backup(BACKUP_GIT_REPO_URL, BACKUP_GIT_REPO_CONFIGU_FILE_PATH, args)
        elif args.pool:
            if listOnly:
                rackCfg.showServersInPool(args.pool)
            else:
                rackCfg.updatePool(args.servers, args.pool)
                rackCfg.backup(BACKUP_GIT_REPO_URL, BACKUP_GIT_REPO_CONFIGU_FILE_PATH, args)
        elif args.backup:
            rackCfg.backup(BACKUP_GIT_REPO_URL, BACKUP_GIT_REPO_CONFIGU_FILE_PATH, args)
        else:
            raise Exception("Unknown conf parameter")
        if not listOnly:
            rackCfg.reloadConf()

def parse_args():
    parser = argparse.ArgumentParser(
        prog="rackconfig",
        description="Safely configure physical rackattack server",
    )

    parser.add_argument("--yaml", "-y", default=YAML, help="Rackattack YAML configuration path")
    group1 = parser.add_mutually_exclusive_group(required=True)
    group1.add_argument("--show", help="Display servers in certain state or pool", action='store_true')
    group1.add_argument("--servers", metavar="rackXX-serverYY", nargs="+", help="servers to change configuration")
    
    group2 = parser.add_mutually_exclusive_group(required=True)
    group2.add_argument("--state", choices=SERVER_STATES, help="state to move all servers to")
    group2.add_argument("--pool", help="pool to move all servers to")
    group2.add_argument("--backup", help="Backup Rackattack's configuration files to a GitHub repository")
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()
    main(args)
