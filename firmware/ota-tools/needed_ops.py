#!/usr/bin/env python3
# Map traced byte ranges of a partition image to the OTA operations covering
# them; print the op index list and the download size, and build a sparse test
# image containing only those ops (copied from the full image).
import json, sys
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0])
from ota_manifest import parse

part, trace, full, sparse = sys.argv[1:5]
block, parts = parse(open('/tmp/ota-manifest.bin', 'rb').read())
p = next(x for x in parts if x['name'] == part)
ranges = json.load(open(trace))['ranges']
blocks = set()
for s, e in ranges:
    blocks.update(range(s // block, (e - 1) // block + 1))
need = []
for i, op in enumerate(p['ops']):
    if any(b in blocks for start, num in op['dst'] for b in range(start, start + num)):
        need.append(i)
dl = sum(p['ops'][i]['len'] for i in need)
print('%s: %d blocks touched, %d of %d ops, download %.1f MB (full %.1f MB)' % (
    part, len(blocks), len(need), len(p['ops']), dl / 2**20, sum(o['len'] for o in p['ops']) / 2**20))
with open(full, 'rb') as src, open(sparse, 'wb') as dst:
    dst.truncate(p['size'])
    for i in need:
        for start, num in p['ops'][i]['dst']:
            src.seek(start * block); dst.seek(start * block)
            dst.write(src.read(num * block))
json.dump(need, open(trace.replace('.json', '-ops.json'), 'w'))
