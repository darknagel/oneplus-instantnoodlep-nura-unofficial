#!/usr/bin/env python3
# Download one partition from a remote full OTA (payload.bin in a zip) using
# HTTP range requests, and write the partition image.
import bz2, hashlib, lzma, struct, sys, urllib.request
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0])
from ota_manifest import parse

URL, PART, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
pstart, msize, sigsize = map(int, open('/tmp/ota-info.txt').read().split())
block, parts = parse(open('/tmp/ota-manifest.bin', 'rb').read())
p = next(x for x in parts if x['name'] == PART)
data_base = pstart + 24 + msize + sigsize

def get(start, length):
    req = urllib.request.Request(URL, headers={'Range': 'bytes=%d-%d' % (start, start + length - 1)})
    with urllib.request.urlopen(req, timeout=120) as r:
        assert r.status == 206
        return r.read()

with open(OUT, 'wb') as f:
    f.truncate(p['size'])
    for n, op in enumerate(p['ops']):
        raw = get(data_base + op['off'], op['len']) if op['len'] else b''
        if op['sha'] and hashlib.sha256(raw).digest() != op['sha']:
            raise SystemExit('hash mismatch in op %d' % n)
        if op['type'] == 0:
            out = raw
        elif op['type'] == 1:
            out = bz2.decompress(raw)
        elif op['type'] == 8:
            out = lzma.decompress(raw)
        else:
            raise SystemExit('unsupported op type %d' % op['type'])
        pos = 0
        for start, num in op['dst']:
            f.seek(start * block)
            f.write(out[pos:pos + num * block])
            pos += num * block
        if n % 20 == 0:
            print('op %d/%d' % (n, len(p['ops'])), flush=True)
print('wrote', OUT, p['size'])
