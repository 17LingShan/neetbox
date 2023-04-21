print('========= If you see this on Windows, your subprocess is running with consoles merged =========')
print('========= This happens when your DaemonableProcess runs in attached mode. =========')

import os
import sys

# sys.stdout=open(r'D:\Projects\ML\neetbox\logdir\daemon.log', 'a+')

import json
import argparse
print('imported external packages')

from neetbox.daemon._daemon import daemon_process
print('imported neetbox.daemon')

def run():
    if len(sys.argv) <= 1:
        print('_daemon_launcher: Warning: empty daemon_config')
        daemon_config = {}
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument('--config')
        args = ap.parse_args()
        daemon_config = json.loads(args.config)
        print('Daemon launcher started with config:', daemon_config)
    daemon_process(daemon_config)
        

print('_daemon_launcher is starting with __name__ =',
      __name__, ' and args =', sys.argv)

run()
print('_daemon_launcher: exiting')
