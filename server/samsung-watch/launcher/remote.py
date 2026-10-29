"""Authenticated Samsung 2012 LAN remote; no service-menu or power-off keys."""
import argparse
import base64
import socket
import struct
import time

SAFE_KEYS = {'KEY_CONTENTS','KEY_SMART_HUB','KEY_ENTER','KEY_RETURN','KEY_EXIT','KEY_UP','KEY_DOWN','KEY_LEFT','KEY_RIGHT'}

def field(data):
    return struct.pack('<H', len(data)) + data

class Remote:
    def __init__(self, host, timeout=5):
        self.socket = socket.create_connection((host,55000),timeout=timeout)
        self.socket.settimeout(timeout)
        data = b'\x64\x00'
        for value in ['192.168.0.146','homeassistant-pi-watch','Pi Watch remote']:
            data += field(base64.b64encode(value.encode()))
        self.send(data)
        while True:
            response = self.response()
            if response == b'\x64\x00\x01\x00':break
            if response[:1] == b'\x0a':continue
            self.close()
            raise RuntimeError('The TV has not approved Pi Watch remote.')
    def exact(self,n):
        data=b''
        while len(data)<n:
            chunk=self.socket.recv(n-len(data))
            if not chunk:raise ConnectionError('TV closed the remote connection.')
            data+=chunk
        return data
    def send(self,data):
        self.socket.sendall(b'\x00'+field(b'iphone.iapp.samsung')+field(data))
    def response(self):
        h=self.exact(3)
        self.exact(int.from_bytes(h[1:3],'little'))
        return self.exact(int.from_bytes(self.exact(2),'little'))
    def key(self,key):
        if key not in SAFE_KEYS:raise ValueError('Unsupported navigation key.')
        self.send(b'\x00\x00\x00'+field(base64.b64encode(key.encode())))
        response=self.response()
        if response!=b'\x00\x00\x00\x00':raise RuntimeError('TV did not accept the key.')
        time.sleep(.3)
    def close(self):self.socket.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('keys',nargs='+',choices=sorted(SAFE_KEYS));p.add_argument('--host',default='192.168.0.123');a=p.parse_args()
    with Remote(a.host) as remote:
        for key in a.keys:remote.key(key);print('Accepted:',key)
