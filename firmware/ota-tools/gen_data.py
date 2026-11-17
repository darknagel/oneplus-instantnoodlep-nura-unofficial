#!/usr/bin/env python3
# Generate the data block of oneplus-ota-fetch from the traces and op lists.
import json, sys
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0])
from ota_manifest import parse

block, parts = parse(open('/tmp/ota-manifest.bin', 'rb').read())
pstart, msize, sigsize = map(int, open('/tmp/ota-info.txt').read().split())
out = {'payload_offset': pstart, 'manifest_size': msize, 'signature_size': sigsize,
       'block_size': block, 'partitions': {}}
for name in ('odm', 'vendor'):
    p = next(x for x in parts if x['name'] == name)
    need = json.load(open('/tmp/%s-trace-ops.json' % name))
    ops = []
    for i in need:
        op = p['ops'][i]
        ops.append([op['type'], op['off'], op['len'], op['sha'].hex() if op['sha'] else '',
                    [[s, n] for s, n in op['dst']]])
    files = {k: [v['size'], v['sha256']] for k, v in
             json.load(open('/tmp/%s-trace.json' % name))['files'].items()}
    out['partitions'][name] = {'size': p['size'], 'ops': ops, 'files': files}
json.dump(out, open('/tmp/ota-fetch-data.json', 'w'), separators=(',', ':'))
print('data bytes', len(json.dumps(out, separators=(',', ':'))))
