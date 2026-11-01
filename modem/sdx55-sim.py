#!/usr/bin/env python3
# Activate the SIM on the SDX55. The modem detects the card but does not make
# it the primary subscription on its own, so ModemManager reports sim-missing.
# Watch the card status and send QMI UIM Change Provisioning Session when a
# USIM is present without a primary session, then let ModemManager look again.
# Also load mhi_net once the modem has settled: it is blocked from loading on
# its own (/etc/modprobe.d/sdx55-mhi-net.conf), because probing it during modem
# start reset the phone. ModemManager then starts from here (see
# ModemManager-sdx55.conf): it aborts on data ports that appear while it runs.
import socket, struct, subprocess, time

UIM = 11
SETTLED = 6  # checks with the modem up before loading mhi_net
READY = '/run/sdx55-net-ready'
up = 0


def services():
    s = socket.socket(42, socket.SOCK_DGRAM); s.settimeout(1)
    node, _ = s.getsockname()
    s.sendto(struct.pack('<IIIIII', 10, 0, 0, 0, 0, 0) + bytes(8), (node, 0xfffffffe))
    svc = {}
    while True:
        try: d = s.recv(64)
        except socket.timeout: break
        t, sv, inst, n, p = struct.unpack_from('<IIIII', d)
        if t == 4 and n == 3: svc[sv] = p
        if t == 4 and sv == 0 and n == 0: break
    s.close()
    return svc


def q(port, msg, body=b''):
    c = socket.socket(42, socket.SOCK_DGRAM); c.settimeout(5)
    c.sendto(struct.pack('<BHHH', 0, 1, msg, len(body)) + body, (3, port))
    d = c.recv(8192); c.close()
    out, o = {}, 7
    while o + 3 <= len(d):
        t, l = struct.unpack_from('<BH', d, o); out[t] = d[o + 3:o + 3 + l]; o += 3 + l
    return out


def tlv(t, v):
    return struct.pack('<BH', t, len(v)) + v


def find_usim(d):
    n = d[8]; o = 9
    for i in range(n):
        st = d[o]; apps = d[o + 5]; o += 6
        for a in range(apps):
            typ = d[o]; o += 6
            l = d[o]; aid = d[o + 1:o + 1 + l]; o += 1 + l + 7
            if st == 1 and typ == 2:
                return i + 1, aid
    return None


def check():
    global up
    port = services().get(UIM)
    if port is None:
        return
    up += 1
    if up == SETTLED:
        r = subprocess.run(['modprobe', '-i', 'mhi_net'])
        print('load mhi_net:', r.returncode, flush=True)
        time.sleep(2)
        open(READY, 'w').close()
        subprocess.run(['systemctl', 'start', 'ModemManager'])
    d = q(port, 0x2f)[0x10]
    if d[:2] != b'\xff\xff':
        return
    f = find_usim(d)
    if f is None:
        return
    slot, aid = f
    r = q(port, 0x38, tlv(0x01, bytes([0, 1])) + tlv(0x10, bytes([slot, len(aid)]) + aid))
    print('activate SIM in slot %d: %s' % (slot, r.get(2, b'').hex()), flush=True)
    time.sleep(3)
    subprocess.run(['systemctl', 'try-restart', 'ModemManager'])


n = 0
while True:
    try: check()
    except (OSError, KeyError, IndexError) as e: print('check:', e, flush=True)
    n += 1
    time.sleep(5 if n < 24 else 30)
