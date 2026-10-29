#!/usr/bin/env python3
"""Build an Orsay ZIP with a device-scoped connection, no HA/provider secrets."""
import argparse
import json
from pathlib import Path
import zipfile
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

def icons(root):
    folder = root / 'images'
    folder.mkdir(exist_ok=True)
    for size in ((106, 86), (115, 95), (85, 70), (95, 78)):
        im = Image.new('RGB', size, '#142b39')
        d = ImageDraw.Draw(im)
        w, h = size
        d.rounded_rectangle((3, 3, w - 4, h - 4), radius=12, fill='#1a414b')
        d.polygon(((w*.39, h*.25), (w*.39, h*.71), (w*.7, h*.48)), fill='#a0ffe5')
        im.save(folder / ('icon%d.png' % w))
    im = Image.new('RGB', (640, 360), '#203748')
    d = ImageDraw.Draw(im)
    d.polygon(((270, 110), (270, 250), (390, 180)), fill='#70cbb8')
    im.save(folder / 'backdrop.png')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--key-file', type=Path)
    p.add_argument('--base', default='http://192.168.0.146:8113')
    p.add_argument('--output', type=Path, default=Path('SamsungWatch_0.310_Europe_20261029.zip'))
    p.add_argument('--resolution', choices=['720','1080'], default='1080')
    p.add_argument('--version', default='0.310')
    args = p.parse_args()
    root = Path(__file__).resolve().parent / 'widget'
    icons(root)
    key = args.key_file.read_text().strip() if args.key_file else 'SET_DURING_PI_PACKAGING'
    connection = 'var WATCH_CONNECTION = ' + json.dumps({'base': args.base, 'key': key}) + ';\n'
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                content = connection if name == 'connection.js' else path.read_bytes()
                if name == 'preview.js' and args.key_file:
                    content = '/* Preview data omitted from paired TV package. */\n'
                if name == 'watch.js':
                    content = re.sub(r"var buildVersion = '[^']+'", "var buildVersion = '" + args.version + "'", content.decode()).encode()
                if name == 'config.xml':
                    config = ET.fromstring(content)
                    config.find('ver').text = args.version
                    if args.resolution == '1080':
                        config.find('width').text = '1920'; config.find('height').text = '1080'
                    content = ET.tostring(config, encoding='utf-8', xml_declaration=True)
                if args.resolution == '1080':
                    if name == 'watch.css':
                        content = re.sub(r'(?<![\w-])(-?\d+(?:\.\d+)?)px', lambda m: format(float(m[1])*1.5,'.3f').rstrip('0').rstrip('.')+'px', content.decode())
                    elif name == 'watch.js': content = content.decode().replace('var renderScale = 4 / 3;', 'var renderScale = 2;')
                    elif name == 'widget.info': content = content.decode().replace('1280x720','1920x1080')
                    elif name == 'index.html': content = content.decode().replace('width=1280','width=1920')
                z.writestr(name, content)
    print('Built', args.output.name, args.output.stat().st_size, 'bytes')

if __name__ == '__main__':
    main()
