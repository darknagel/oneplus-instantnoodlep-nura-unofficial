#!/usr/bin/env python3
# GNSS for the OnePlus 8 Pro's SDX55: talk to the modem's QMI LOC service
# over QRTR, start a 1 Hz tracking session and hand the standard NMEA
# sentences to a pseudo terminal at /dev/gnss-sdx55 (for gpsd and friends).
# Restarts the session whenever the modem goes away and comes back.
import os, socket, struct, sys, time, tty

LOC, DMS = 16, 2
LINK = '/dev/gnss-sdx55'
NMEA_TYPES = 0x39f      # GGA RMC GSV GSA VTG GLGSV GNGSA GNGNS


def log(*a):
    print(*a, flush=True)


def tlv(t, v):
    return struct.pack('<BH', t, len(v)) + v


def parse(d):
    flags, tx, msg, ln = struct.unpack_from('<BHHH', d)
    out, o = {}, 7
    while o + 3 <= min(len(d), 7 + ln):
        t, l = struct.unpack_from('<BH', d, o)
        out[t] = d[o + 3:o + 3 + l]
        o += 3 + l
    return flags, msg, out


def lookup(svc, timeout=2):
    s = socket.socket(42, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    node, _ = s.getsockname()
    s.sendto(struct.pack('<IIIIII', 10, svc, 0, 0, 0, 0) + bytes(8), (node, 0xfffffffe))
    found = None
    try:
        while True:
            t, sv, inst, n, p = struct.unpack_from('<IIIII', s.recv(64))
            if t == 4 and sv == svc and n:
                found = (n, p)
            if t == 4 and sv == 0 and n == 0:
                break
    except socket.timeout:
        pass
    s.close()
    return found


class Client:
    def __init__(self, addr):
        self.addr, self.txn = addr, 0
        self.s = socket.socket(42, socket.SOCK_DGRAM)
        self.s.settimeout(1)

    def call(self, msg, body=b'', on_ind=None, timeout=5):
        self.txn = (self.txn + 1) & 0xffff
        self.s.sendto(struct.pack('<BHHH', 0, self.txn, msg, len(body)) + body, self.addr)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                f, m, t = parse(self.s.recv(8192))
            except socket.timeout:
                continue
            if f == 2 and m == msg:
                return struct.unpack_from('<HH', t.get(2, bytes(4)))
            if f == 4 and on_ind:
                on_ind(m, t)
        return None


def ensure_online():
    """Without a SIM nothing else brings the modem out of low power mode.
    Only touch it when it is not online yet, so ModemManager stays in charge
    of the radio when it manages the modem."""
    addr = lookup(DMS)
    if not addr:
        return
    dms = Client(addr)
    dms.s.sendto(struct.pack('<BHHH', 0, 1, 0x2d, 0), addr)
    try:
        f, m, t = parse(dms.s.recv(4096))
        mode = t.get(1, b'\xff')[0]
    except socket.timeout:
        return
    if mode not in (0, 1, 5):   # online; leave LPM to ModemManager (airplane mode)
        return
    if mode != 0 and not os.path.exists('/run/sdx55-gnss.online-done'):
        r = dms.call(0x2e, tlv(1, b'\x00'))
        log('set modem online:', r)
        open('/run/sdx55-gnss.online-done', 'w').close()


def session(master):
    addr = lookup(LOC)
    if not addr:
        return
    log('LOC service at', addr)
    ensure_online()
    loc = Client(addr)
    loc.call(0x0020, tlv(1, struct.pack('<I', 2)))                     # client revision
    loc.call(0x003a, tlv(1, struct.pack('<I', 1)))                     # engine lock: none
    loc.call(0x003e, tlv(1, struct.pack('<I', NMEA_TYPES)))            # standard NMEA
    if time.time() > 1.7e9:                                             # clock looks synced
        loc.call(0x0038, tlv(1, struct.pack('<Q', int(time.time() * 1000))) + tlv(2, struct.pack('<I', 1000)))
    loc.call(0x004a, tlv(1, struct.pack('<I', 4)))                     # standalone
    loc.call(0x0021, tlv(1, struct.pack('<Q', 0x4)))                   # NMEA events
    r = loc.call(0x0022, tlv(1, b'\x01') + tlv(0x10, struct.pack('<I', 1)) + tlv(0x13, struct.pack('<I', 1000)))
    log('start session:', r)
    if r != (0, 0):
        return
    last = time.monotonic()
    while time.monotonic() - last < 30:   # no NMEA for 30 s: modem gone, start over
        try:
            f, m, t = parse(loc.s.recv(8192))
        except socket.timeout:
            continue
        if f == 4 and m == 0x26 and 1 in t:
            line = t[1].split(b'\0')[0].strip()
            if line.startswith(b'$G'):
                last = time.monotonic()
                try:
                    os.write(master, line + b'\r\n')
                except OSError:
                    pass
    log('NMEA stopped, restarting')


def main():
    master, slave = os.openpty()
    tty.setraw(slave)
    os.set_blocking(master, False)
    try:
        os.unlink(LINK)
    except FileNotFoundError:
        pass
    os.symlink(os.ttyname(slave), LINK)
    log('NMEA on', LINK, '->', os.ttyname(slave))
    while True:
        try:
            session(master)
        except OSError as e:
            log('error:', e)
        time.sleep(5)


main()
