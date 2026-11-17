#!/usr/bin/env python3
# Minimal protobuf reader for update_engine's DeltaArchiveManifest.
import sys

def varint(b, i):
    v = s = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            return v, i

def fields(b):
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        f, t = key >> 3, key & 7
        if t == 0:
            v, i = varint(b, i)
        elif t == 2:
            n, i = varint(b, i); v = b[i:i + n]; i += n
        elif t == 1:
            v = b[i:i + 8]; i += 8
        elif t == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError('wire type %d' % t)
        yield f, v

def parse(manifest):
    block = 4096
    parts = []
    for f, v in fields(manifest):
        if f == 3:
            block = v
        elif f == 13:
            p = {'name': None, 'ops': [], 'size': 0}
            for pf, pv in fields(v):
                if pf == 1:
                    p['name'] = pv.decode()
                elif pf == 7:
                    for nf, nv in fields(pv):
                        if nf == 1: p['size'] = nv
                elif pf == 8:
                    op = {'type': 0, 'off': 0, 'len': 0, 'dst': [], 'sha': None}
                    for of, ov in fields(pv):
                        if of == 1: op['type'] = ov
                        elif of == 2: op['off'] = ov
                        elif of == 3: op['len'] = ov
                        elif of == 6:
                            e = dict(fields(ov)); op['dst'].append((e.get(1, 0), e.get(2, 0)))
                        elif of == 8: op['sha'] = ov
                    p['ops'].append(op)
            parts.append(p)
    return block, parts

if __name__ == '__main__':
    block, parts = parse(open(sys.argv[1], 'rb').read())
    print('block', block)
    for p in parts:
        types = sorted(set(o['type'] for o in p['ops']))
        data = sum(o['len'] for o in p['ops'])
        print('%-22s size %6d MB  ops %4d  types %s  download %6.1f MB' % (p['name'], p['size'] >> 20, len(p['ops']), types, data / 2**20))
