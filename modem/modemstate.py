#!/usr/bin/env python3
# Print modem operating mode and network registration state (no identifiers).
import socket, struct
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

def q(sv, msg):
    c = socket.socket(42, socket.SOCK_DGRAM); c.settimeout(3)
    c.sendto(struct.pack('<BHHH', 0, 1, msg, 0), (3, svc[sv]))
    d = c.recv(4096); c.close()
    out, o = {}, 7
    while o + 3 <= len(d):
        t, l = struct.unpack_from('<BH', d, o); out[t] = d[o + 3:o + 3 + l]; o += 3 + l
    return out

modes = ['online', 'low power', 'factory test', 'offline', 'resetting', 'shutting down', 'persistent LPM', 'mode-only LPM']
t = q(2, 0x2d)
print('DMS operating mode:', modes[t[1][0]] if 1 in t and t[1][0] < len(modes) else t)
t = q(3, 0x24)   # NAS get serving system
reg = ['not registered', 'registered', 'searching', 'denied', 'unknown']
if 1 in t:
    print('NAS registration:', reg[t[1][0]] if t[1][0] < 5 else t[1][0], '| CS attach', t[1][1], '| PS attach', t[1][2], '| network type', t[1][3])
t = q(11, 0x2f)  # UIM card status
if 0x10 in t:
    print('UIM card status raw (no IDs):', t[0x10][:8].hex())

import sys, time
if len(sys.argv) > 1 and sys.argv[1] == 'online':
    c = socket.socket(42, socket.SOCK_DGRAM); c.settimeout(5)
    # DMS SET_OPERATING_MODE (0x2e), TLV 1 = 0 online
    c.sendto(struct.pack('<BHHH', 0, 2, 0x2e, 4) + struct.pack('<BHB', 1, 1, 0), (3, svc[2]))
    d = c.recv(4096)
    r, e = struct.unpack_from('<HH', d, 10)
    print('set online: result %d error %d' % (r, e))
    time.sleep(3)
    t = q(2, 0x2d)
    print('DMS operating mode now:', modes[t[1][0]] if t[1][0] < len(modes) else t[1][0])
