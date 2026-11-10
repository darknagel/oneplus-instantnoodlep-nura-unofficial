#!/usr/bin/env python3
"""Exercise QRTR DEL_CLIENT through real sockets and isolated test endpoints.

Requires root, CONFIG_QRTR_TUN, and no pre-existing test node IDs/services.
Never sends a deletion for a production client. --baseline expects the old
kernel to reject the same-endpoint forwarding case.
"""
import argparse
import json
import os
import socket
import struct

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', action='store_true')
args = parser.parse_args()
CTRL = 0xfffffffe
SERVICE = 0x7fffff00
NODES = (60000, 60001, 60002, 60003)
NEW_SERVER, DEL_CLIENT, NEW_LOOKUP, BYE = 4, 6, 10, 3
results = []
fds = []
sockets = []


def sock():
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((1, 0))
    s.settimeout(2)
    return s


def ctrl(cmd, *fields):
    return struct.pack('<5I', cmd, *fields, *([0] * (4 - len(fields))))


def services(service):
    with sock() as q:
        q.sendto(ctrl(NEW_LOOKUP, service, 0, 0, 0), (1, CTRL))
        found = set()
        while True:
            packet, source = q.recvfrom(4096)
            cmd, sid, instance, node, port = struct.unpack('<5I', packet)
            assert source == (1, CTRL) and cmd == NEW_SERVER, (packet, source)
            if not (sid or instance or node or port):
                return found
            found.add((sid, instance, node, port))


def inject(fd, src, payload, version=3, source_port=CTRL):
    cmd = struct.unpack_from('<I', payload)[0]
    if version == 3:
        hdr = struct.pack('<4BI4H', 3, cmd, 0, 0, len(payload),
                          src, source_port & 0xffff, 1, CTRL & 0xffff)
    else:
        hdr = struct.pack('<8I', 1, cmd, src, source_port, 0,
                          len(payload), 1, CTRL)
    assert os.write(fd, hdr + payload) == len(hdr + payload)


def announce(fd, src, node, port):
    inject(fd, src, ctrl(NEW_SERVER, SERVICE, 1, node, port))


def notifications(s):
    packets = []
    s.setblocking(False)
    try:
        while True:
            packet, source = s.recvfrom(4096)
            values = struct.unpack('<5I', packet)
            if values[0] == DEL_CLIENT:
                packets.append((values[1], values[2]))
    except BlockingIOError:
        return packets
    finally:
        s.settimeout(2)


def check(name, send, target, removed, expect_accept):
    notifications(observer)
    send()
    # The listing's end marker is a barrier through the ordered NS worker.
    listed = services(SERVICE)
    notices = notifications(observer)
    present = any(x[2:] == target for x in listed)
    accepted = target in notices
    ok = accepted == expect_accept and present == (not removed)
    result = dict(name=name, target=target, notified=accepted,
                  still_registered=present, passed=ok)
    results.append(result)
    print(json.dumps(result), flush=True)
    assert ok, result


existing = services(0)
assert not any(x[0] == SERVICE or x[2] in NODES for x in existing), existing
try:
    observer, attacker = sock(), sock()
    sockets.extend((observer, attacker))
    local_port = observer.getsockname()[1]
    observer.sendto(ctrl(NEW_SERVER, SERVICE, 1, 1, local_port), (1, CTRL))
    a = os.open('/dev/qrtr-tun', os.O_RDWR | os.O_NONBLOCK)
    fds.append(a)
    b = os.open('/dev/qrtr-tun', os.O_RDWR | os.O_NONBLOCK)
    fds.append(b)
    announce(a, NODES[0], NODES[0], 101)
    announce(a, NODES[0], NODES[1], 102)
    announce(b, NODES[2], NODES[2], 103)
    assert len(services(SERVICE)) == 4

    for version in (3, 1):
        check(f'forwarded_same_endpoint_v{version}',
              lambda: inject(a, NODES[0], ctrl(DEL_CLIENT, NODES[1], 102), version),
              (NODES[1], 102), not args.baseline, not args.baseline)
        announce(a, NODES[0], NODES[1], 102)
        assert len(services(SERVICE)) == 4

    check('cross_endpoint_rejected',
          lambda: inject(a, NODES[0], ctrl(DEL_CLIENT, NODES[2], 103)),
          (NODES[2], 103), False, False)
    check('remote_cannot_remove_local_client',
          lambda: inject(a, NODES[0], ctrl(DEL_CLIENT, 1, local_port)),
          (1, local_port), False, False)
    check('local_cannot_remove_another_local_port',
          lambda: attacker.sendto(ctrl(DEL_CLIENT, 1, local_port), (1, CTRL)),
          (1, local_port), False, False)
    check('local_cannot_remove_remote_client',
          lambda: attacker.sendto(ctrl(DEL_CLIENT, NODES[1], 102), (1, CTRL)),
          (NODES[1], 102), False, False)
    check('forwarder_must_use_control_port',
          lambda: inject(a, NODES[0], ctrl(DEL_CLIENT, NODES[1], 102), source_port=111),
          (NODES[1], 102), False, False)
    check('unmapped_forwarded_node_rejected',
          lambda: inject(a, NODES[0], ctrl(DEL_CLIENT, NODES[3], 104)),
          (NODES[3], 104), True, False)
    check('direct_remote_deletion',
          lambda: inject(b, NODES[2], ctrl(DEL_CLIENT, NODES[2], 103)),
          (NODES[2], 103), True, True)

    # The kernel-generated DEL_CLIENT on close must still remove a local server.
    local = sock()
    sockets.append(local)
    own_port = local.getsockname()[1]
    local.sendto(ctrl(NEW_SERVER, SERVICE, 1, 1, own_port), (1, CTRL))
    assert any(x[2:] == (1, own_port) for x in services(SERVICE))
    check('normal_local_close', local.close, (1, own_port), True, True)
finally:
    # Remove only the synthetic nodes before releasing the transports.
    if fds:
        for node in NODES[:2]:
            inject(fds[0], node, ctrl(BYE))
    if len(fds) > 1:
        inject(fds[1], NODES[2], ctrl(BYE))
    if fds:
        services(SERVICE)
    for s in sockets:
        s.close()
    for fd in fds:
        os.close(fd)

assert not services(SERVICE), 'test services leaked'
print(json.dumps(dict(baseline=args.baseline, passed=len(results), total=10,
                     cleanup='no synthetic services remain')), flush=True)
