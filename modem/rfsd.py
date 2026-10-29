#!/usr/bin/env python3
# Run as root. Minimal TFTP-over-QRTR server for the SDX55 remote file system
# (what tftp_server does on Android). Read-only files come from the modem_a
# partition and /lib/firmware, /readwrite is kept in /var/lib/sdx55-rfs.
import os, socket, struct, subprocess, sys, threading, time

AF_QIPCRTR = 42
SERVICE = 4096
INSTANCE = int(sys.argv[1]) if len(sys.argv) > 1 else 3
MNT = '/run/sdx55-modem_a'
RW = '/var/lib/sdx55-rfs/readwrite'

RRQ, WRQ, DATA, ACK, ERROR, OACK = 1, 2, 3, 4, 5, 6

logf = sys.stdout  # the journal when run as a service
lock = threading.Lock()


def log(msg):
    up = open('/proc/uptime').read().split()[0]
    with lock:
        logf.write('[%10s] %s\n' % (up, msg))
        logf.flush()


os.makedirs(MNT, exist_ok=True)
os.makedirs(RW, exist_ok=True)
if not os.path.ismount(MNT):
    subprocess.call(['mount', '-o', 'ro', '/dev/disk/by-partlabel/modem_a', MNT])

RO_PREFIXES = ('/readonly/firmware/image/', '/readonly/vendor/firmware_mnt/image/',
               '/readonly/vendor/firmware/', '/readonly/firmware/')
# Files in OVR replace those on modem_a (debug: e.g. a changed mbn_hw.dig)
OVR = '/var/lib/sdx55-rfs/override'
RO_DIRS = (OVR, MNT + '/image/sdx55', MNT + '/image', MNT, '/lib/firmware/qcom/sdx55m')


def safe(rel):
    rel = os.path.normpath('/' + rel).lstrip('/')
    return None if rel.startswith('..') else rel


def resolve(name, write=False):
    if name.startswith('/readwrite/'):
        rel = safe(name[len('/readwrite/'):])
        return rel and os.path.join(RW, rel)
    if write:
        return None
    for pre in RO_PREFIXES:
        if name.startswith(pre):
            rel = safe(name[len(pre):])
            if not rel:
                return None
            for d in RO_DIRS:
                p = os.path.join(d, rel)
                if os.path.isfile(p):
                    return p
            return None
    return None


def parse_req(pkt):
    parts = pkt[2:].split(b'\0')
    name, mode = parts[0].decode(errors='replace'), parts[1].decode(errors='replace')
    opts = {}
    for i in range(2, len(parts) - 1, 2):
        if parts[i]:
            opts[parts[i].decode().lower()] = parts[i + 1].decode()
    return name, mode, opts


def oack(opts):
    return struct.pack('>H', OACK) + b''.join(k.encode() + b'\0' + str(v).encode() + b'\0'
                                              for k, v in opts.items())


def err(sock, addr, code, msg):
    sock.sendto(struct.pack('>HH', ERROR, code) + msg.encode() + b'\0', addr)


def recv_from(sock, addr, timeout=2.0):
    sock.settimeout(timeout)
    while True:
        d, a = sock.recvfrom(65536)
        if a == addr:
            return d


def serve_rrq(addr, name, opts):
    sock = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM)
    path = resolve(name)
    if not path or not os.path.isfile(path):
        log('RRQ %s -> not found %s' % (name, opts))
        err(sock, addr, 1, 'file not found')
        return
    size = os.path.getsize(path)
    blksize = int(opts.get('blksize', 512))
    wsize = int(opts.get('wsize', 1))
    seek = int(opts.get('seek', 0))
    rsize = int(opts['rsize']) if 'rsize' in opts else None
    reply = {}
    for k in ('blksize', 'timeoutms', 'wsize', 'seek', 'rsize'):
        if k in opts:
            reply[k] = opts[k]
    if 'tsize' in opts:
        reply['tsize'] = size
    log('RRQ %s -> %s (%d bytes) %s' % (name, path, size, opts))
    with open(path, 'rb') as f:
        f.seek(seek)
        data = f.read(rsize if rsize is not None else -1)
    try:
        if reply:
            sock.sendto(oack(reply), addr)
            d = recv_from(sock, addr)
            op = struct.unpack_from('>H', d)[0]
            if op != ACK:      # e.g. a TFTP_STAT ends here with an ERROR
                return
        blocks = [data[i:i + blksize] for i in range(0, len(data), blksize)]
        if len(data) % blksize == 0:
            blocks.append(b'')
        acked, tries = 0, 0
        while acked < len(blocks):
            for i in range(acked, min(acked + wsize, len(blocks))):
                sock.sendto(struct.pack('>HH', DATA, (i + 1) & 0xffff) + blocks[i], addr)
            try:
                d = recv_from(sock, addr)
            except socket.timeout:
                tries += 1
                if tries > 5:
                    log('RRQ %s timed out' % name)
                    return
                continue
            op, blk = struct.unpack_from('>HH', d)
            if op == ACK:
                # Translate the 16 bit block number back into an index
                base = acked & ~0xffff
                idx = base + blk
                if idx < acked and idx + 0x10000 <= len(blocks):
                    idx += 0x10000
                if idx <= len(blocks):
                    acked = max(acked, idx)
                tries = 0
            elif op == ERROR:
                log('RRQ %s aborted by modem' % name)
                return
    except socket.timeout:
        log('RRQ %s timed out after OACK' % name)
    finally:
        sock.close()


def serve_wrq(addr, name, opts):
    sock = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM)
    path = resolve(name, write=True)
    if not path:
        log('WRQ %s -> rejected' % name)
        err(sock, addr, 2, 'access violation')
        return
    if 'unlink' in opts:
        # Qualcomm extension: a WRQ with "unlink" deletes the file, no data follows
        try:
            os.remove(path)
            log('WRQ %s -> unlinked' % name)
        except FileNotFoundError:
            log('WRQ %s -> unlink, not there' % name)
        sock.sendto(oack(opts), addr)
        sock.close()
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    blksize = int(opts.get('blksize', 512))
    wsize = int(opts.get('wsize', 1))
    reply = {k: opts[k] for k in ('blksize', 'timeoutms', 'wsize', 'tsize') if k in opts}
    log('WRQ %s -> %s %s' % (name, path, opts))
    total, expect = 0, 1
    try:
        with open(path + '.part', 'wb') as f:
            if reply:
                sock.sendto(oack(reply), addr)
            else:
                sock.sendto(struct.pack('>HH', ACK, 0), addr)
            while True:
                d = recv_from(sock, addr, 5.0)
                op, blk = struct.unpack_from('>HH', d)
                if op == ERROR:
                    log('WRQ %s aborted by modem' % name)
                    return
                if op != DATA:
                    continue
                if blk == expect & 0xffff:
                    payload = d[4:]
                    f.write(payload)
                    total += len(payload)
                    last = len(payload) < blksize
                    if last or expect % wsize == 0:
                        sock.sendto(struct.pack('>HH', ACK, blk), addr)
                    expect += 1
                    if last:
                        break
                else:
                    sock.sendto(struct.pack('>HH', ACK, (expect - 1) & 0xffff), addr)
        os.replace(path + '.part', path)
        log('WRQ %s done, %d bytes' % (name, total))
    except socket.timeout:
        log('WRQ %s timed out' % name)
    finally:
        sock.close()


srv = socket.socket(AF_QIPCRTR, socket.SOCK_DGRAM)
node, _ = srv.getsockname()
# Publish the service: QRTR_TYPE_NEW_SERVER to the name service
srv.sendto(struct.pack('<IIIII', 4, SERVICE, INSTANCE, 0, 0), (node, 0xfffffffe))
log('== serving service %d instance %d on port %d' % (SERVICE, INSTANCE, srv.getsockname()[1]))

while True:
    pkt, addr = srv.recvfrom(65536)
    if len(pkt) < 4:
        continue
    op = struct.unpack_from('>H', pkt)[0]
    if op not in (RRQ, WRQ):
        continue
    try:
        name, mode, opts = parse_req(pkt)
    except Exception as e:
        log('bad request %r: %s' % (pkt[:64], e))
        continue
    fn = serve_rrq if op == RRQ else serve_wrq
    threading.Thread(target=fn, args=(addr, name, opts), daemon=True).start()
