#!/usr/bin/env python3
"""Open Watch once per confirmed TV off/on cycle, using a calibrated route."""
import argparse
import json
import logging
from pathlib import Path
import socket
import time
from remote import Remote

LOG=logging.getLogger('watch-launcher')

class PowerCycle:
    def __init__(self, off_seconds=20, ready_seconds=25):
        self.off_seconds=off_seconds; self.ready_seconds=ready_seconds
        self.off_since=None; self.on_since=None; self.armed=False
    def update(self, online, now):
        if not online:
            self.on_since=None
            if self.off_since is None:self.off_since=now
            if now-self.off_since>=self.off_seconds:self.armed=True
            return False
        self.off_since=None
        if not self.armed:return False
        if self.on_since is None:self.on_since=now
        if now-self.on_since<self.ready_seconds:return False
        self.armed=False
        return True

def available(host):
    try:
        with socket.create_connection((host,55000),timeout=2):return True
    except OSError:return False

def launch(config):
    if not config.get('calibrated'):
        raise ValueError('Power-on menu navigation has not been verified yet.')
    with Remote(config['host']) as remote:
        remote.key('KEY_CONTENTS')
        time.sleep(config.get('hub_delay',5))
        for key in config['navigation']:
            remote.key(key)
        remote.key('KEY_ENTER')
    LOG.info('Watch launch sequence accepted by TV.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--once',action='store_true');a=p.parse_args()
    c=json.loads(Path(a.config).read_text());logging.basicConfig(level=logging.INFO)
    if a.once:launch(c);return
    if not c.get('calibrated'):raise ValueError('Complete power-on calibration before enabling.')
    power=PowerCycle(c.get('off_seconds',20),c.get('ready_seconds',25))
    LOG.info('Waiting for an off/on cycle. No launch on service startup while TV is on.')
    while True:
        if power.update(available(c['host']),time.monotonic()):
            try:launch(c)
            except Exception as e:LOG.warning('Launch failed (%s); no repeated key presses this cycle.',type(e).__name__)
        time.sleep(3)

if __name__=='__main__':main()
