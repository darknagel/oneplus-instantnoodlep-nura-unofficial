#!/usr/bin/env python3
# Run inside the Alpine chroot (erofs-utils 1.9 + strace).
# Usage: trace_blocks.py IMAGE OUTFILE SPEC...
#   SPEC: dir:/path   (list a directory and read every file in it)
#         file:/path  (read one file)
# Writes the byte ranges the reads touched (start end per line) plus the
# list of files with their sha256 to OUTFILE.json.
import hashlib, json, re, subprocess, sys

img, out = sys.argv[1], sys.argv[2]
specs = sys.argv[3:]
ranges, files = [], {}

def traced(args):
    log = '/tmp/trace.log'
    r = subprocess.run(['strace', '-f', '-e', 'trace=pread64,preadv,preadv2,read,lseek',
                        '-o', log] + args, capture_output=True)
    for line in open(log):
        m = re.search(r'pread64\(\d+, .*?, (\d+), (\d+)\) = (\d+)', line)
        if m:
            ln, off, got = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if got:
                ranges.append((off, off + got))
    return r.stdout

def ls(path):
    txt = traced(['dump.erofs', '--ls', '--path=' + path, img]).decode()
    entries = []
    for line in txt.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and parts[2] not in ('.', '..'):
            entries.append((parts[2], parts[1]))
    return entries

def ancestors(path):
    parts = path.strip('/').split('/')
    return ['/' + '/'.join(parts[:i]) for i in range(len(parts))]

def cat(path):
    data = traced(['dump.erofs', '--cat', '--path=' + path, img])
    files[path] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

for spec in specs:
    kind, path = spec.split(':', 1)
    for a in ancestors(path):
        ls(a)
    if kind == 'dir':
        for name, typ in ls(path):
            if typ == '1':
                cat(path.rstrip('/') + '/' + name)
    else:
        cat(path)

json.dump({'ranges': sorted(ranges), 'files': files}, open(out, 'w'), indent=1)
print('files', len(files), 'ranges', len(ranges))
