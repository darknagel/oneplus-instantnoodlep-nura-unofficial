#!/usr/bin/env python3
# Continuously copy the QSEE log ring (debugfs fptest_qsee_log) to stdout.
import re, struct, sys, time
P = '/sys/kernel/debug/fptest_qsee_log'
last = None
while True:
    d = open(P, 'rb').read()
    wrap, off = struct.unpack_from('<HH', d, 0)
    b = d[4:]
    if last is None:
        last = off
    elif off != last:
        chunk = b[last:off] if off > last else b[last:] + b[:off]
        sys.stdout.write(re.sub(r'[^\x20-\x7e\n]', '.', chunk.decode('latin1')))
        sys.stdout.flush()
        last = off
    time.sleep(0.02)
