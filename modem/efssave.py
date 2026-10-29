#!/usr/bin/env python3
# Run as root (from udev). Saves an SDX55 Sahara memory dump (EFS sync) from
# devcoredump into /var/lib/sdx55-rfs/efs/<time>/<filename> and frees it.
import os, struct, sys, time

MAGIC = 0x1234567890abcdef
OUT = '/var/lib/sdx55-rfs/efs'
LOG = '/var/lib/sdx55-rfs/efssave.log'

def log(msg):
    with open(LOG, 'a') as f:
        f.write('%s %s\n' % (time.strftime('%F %T'), msg))

dev = sys.argv[1] if len(sys.argv) > 1 else None
if not dev:
    sys.exit(0)
path = '/sys/class/devcoredump/%s/data' % dev
# Only dumps of the modem's PCI device
failing = os.path.realpath('/sys/class/devcoredump/%s/failing_device' % dev)
if '0002:01:00.0' not in failing:
    log('%s: not the modem (%s), ignored' % (dev, failing))
    sys.exit(0)

data = open(path, 'rb').read()
magic, ver, size, tsize = struct.unpack_from('<QQQQ', data)
if magic != MAGIC:
    log('%s: no sahara dump (RAM dump?), %d bytes kept in %s' % (dev, len(data), OUT))
    os.makedirs(OUT, exist_ok=True)
    open('%s/devcd-%s.bin' % (OUT, time.strftime('%Y%m%d-%H%M%S')), 'wb').write(data)
else:
    n = tsize // 64
    d = os.path.join(OUT, time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(d, exist_ok=True)
    off = 32 + n * 64
    for i in range(n):
        typ, addr, length = struct.unpack_from('<QQQ', data, 32 + i * 64)
        desc = data[32 + i * 64 + 24:32 + i * 64 + 44].split(b'\0')[0].decode(errors='replace')
        name = data[32 + i * 64 + 44:32 + i * 64 + 64].split(b'\0')[0].decode(errors='replace')
        name = os.path.basename(name) or 'entry%d.bin' % i
        open(os.path.join(d, name), 'wb').write(data[off:off + length])
        log('%s: %s (%s) %d bytes -> %s' % (dev, name, desc, length, d))
        off += length
    os.chmod(d, 0o700)
    # Each sync is 2 MiB; keep the newest ten
    for old in sorted(x for x in os.listdir(OUT) if x[:1].isdigit())[:-10]:
        p = os.path.join(OUT, old)
        for f in os.listdir(p):
            os.unlink(os.path.join(p, f))
        os.rmdir(p)
# Free the dump
with open(path, 'wb') as f:
    f.write(b'1')
