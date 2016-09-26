#!/usr/bin/python
from __future__ import print_function
import argparse
import re
import subprocess
import sys
import yaml
import requests
import lockfile

SESSION_ID_RE = re.compile(r"'SESSION_COOKIE'\s+:\s+'(\S+)'")
YAML = "/etc/rackattack.physical.rack.yaml"
RACKATTACK_LOCK = "/tmp/rackattack.conf"

def main():

    parser = argparse.ArgumentParser("IPMI Fixer")
    parser.add_argument("--base", help="base of IP address range (e.g. 127.0.0)")
    parser.add_argument("--start", help="start of IP range (inclusive)",  type=int)
    parser.add_argument("--end", help="end of IP range (inclusive)", type=int)
    parser.add_argument("--username", default="root", help="login username")
    parser.add_argument("--password", default="strato", help="login password")
    parser.add_argument("--server", help="rackattack server name")

    args = parser.parse_args()

    if args.server:
        print("Acquiring lock...")
        with lockfile.LockFile(RACKATTACK_LOCK):
            print("Lock acquired.")
            ipmiCredentials = findServer(args.server)
            if not ipmiCredentials:
                print ("Server %s does not exist" % args.server)
                sys.exit(1)
            resetIPMI(ipmiCredentials['hostname'], ipmiCredentials['username'], ipmiCredentials['password'])
            sys.exit(0)

    if args.start > args.end:
        print("error: start can't be greater than end (duh)")
        parser.print_usage()
    
    for i in xrange(args.start, args.end + 1):
        ip = "{}.{}".format(args.base, i)
        print("processing {}: ".format( ip ))
        try:
            session_id = login(ip, args.username, args.password)
            print("\t[OK] login ")
            update(ip, session_id, args.username, 0)
            print("\t[OK] disable IPMI ")
            update(ip, session_id, args.username, 1)
            print("\t[OK] enable IPMI ")
        except RuntimeError, e:
            print("\t[ERROR] {}".format(e.message))
            sys.exit(1)

def login(ip, username, password):
    # curl -vv --cookie-jar cj_10_16_64_62  --insecure --data "WEBVAR_USERNAME=root&WEBVAR_PASSWORD=strato" https://10.16.64.62/rpc/WEBSES/create.asp
    try:
        response = subprocess.check_output(["curl",
                                            "--insecure",
                                            "--silent",
                                            "--data",
                                            "WEBVAR_USERNAME={}&WEBVAR_PASSWORD={}".format(username, password),
                                            "https://{}/rpc/WEBSES/create.asp".format(ip)])
    except subprocess.CalledProcessError:
        raise RuntimeError("login failed")

    match = SESSION_ID_RE.search(response)
    return match.groups()[0]


def findServer(serverName):
    _yaml = yaml.load(open(YAML))
    for server in _yaml['HOSTS']:
        if server['id'] == serverName:
            return server['ipmiLogin']
    
def resetIPMI(ip, username, password):
    print (ip, username, password)
    try:
        session_id = login(ip, username, password)
        print("\t[OK] login ")
        update(ip, session_id, username, 0)
        print("\t[OK] disable IPMI ")
        update(ip, session_id, username, 1)
        print("\t[OK] enable IPMI ")
    except RuntimeError, e:
        print("\t[ERROR] {}".format(e.message))
        sys.exit(1)
 

def update(ip, session_id, username, ipc_val):
    #curl -v --insecure -b "lang=EN; SessionCookie=5cIZLmCdqDk4WvPNjNXcsYcQwgj7q2Ju005; Username=root; lastNav=CONFIG_LEFTNAV; lastHiLit=STR_TOPNAV_CONFIGURATION; lItem=3; test=1"  --data "FAILEDATTEMPTS=3&LOCKOUTTIME=1&FORCEHTTPS=1&WEBSESSION_TIMEOUT=1800&HTTP_PORT=80&HTTPS_PORT=443&SSHSERVICE=1&HTTPSERVICE=1&RMCPSERVICE=1" https://10.16.64.62/rpc/setloginconfig.asp
    url = "https://{}/rpc/setloginconfig.asp".format(ip )

    data = {
        'FAILEDATTEMPTS': 3,
        'FORCEHTTPS': 1,
        'HTTPSERVICE': 1,
        'HTTPS_PORT': 443,
        'HTTP_PORT': 80,
        'LOCKOUTTIME': 1,
        'RMCPSERVICE': ipc_val,
        'SSHSERVICE': 1,
        'WEBSESSION_TIMEOUT': 1800
    }
    try:
        subprocess.check_output(["curl",
                                 "--insecure",
                                 "--silent",
                                 "--cookie",
                                 "lang=EN; SessionCookie={}; Username={}; lastNav=CONFIG_LEFTNAV; lastHiLit=STR_TOPNAV_CONFIGURATION; lItem=3; test=1".format(session_id, username),
                                 "--data",
                                 "&".join([ "{}={}".format(key, val) for key, val in data.iteritems() ]),
                                 url ])
    except subprocess.CalledProcessError:
        raise RuntimeError("update failed")

def update2( ip, session_id ):
    url = "https://{}/rpc/setloginconfig.asp".format( ip )
    data = {
        'FAILEDATTEMPTS': 3,
        'FORCEHTTPS': 1,
        'HTTPSERVICE': 1,
        'HTTPS_PORT': 443,
        'HTTP_PORT': 80,
        'LOCKOUTTIME': 1,
        'RMCPSERVICE': 1,
        'SSHSERVICE': 1,
        'WEBSESSION_TIMEOUT': 1800
    }
    cookies = {
        'SessionCookie': session_id,
        'Username': 'root',
        'lItem': "3",
        'lang': 'EN',
        'lastHiLit': 'STR_TOPNAV_CONFIGURATION',
        'lastNav': 'CONFIG_LEFTNAV',
        'test': "1"
    }

    response = requests.post(url, data=data, cookies=cookies, verify=False)
    if response.status_code != 200:
        import pdb; pdb.set_trace()
        raise RuntimeError("Update failed for {}".format(ip))

def login2(ip, username, password):
    url = "http://{}/rpc/WEBSES/create.asp".format(ip)
    data = {
        "WEBVAR_USERNAME": username,
        "WEBVAR_PASSWORD": password
    }

    response = requests.post(url, data=data, verify=False)
    if response.status_code == 200:
        match = SESSION_ID_RE.search(response.text)
        return match.groups()[0]
    else:
        raise RuntimeError("login failed for {}".format(ip))

if __name__ == "__main__":
   main()
