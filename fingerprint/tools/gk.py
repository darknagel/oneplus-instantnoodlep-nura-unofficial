#!/usr/bin/env python3
# QTI Gatekeeper over keymaster64 TA (CBOR protocol, cmds 0x21001 enroll / 0x21002 verify).
#   gk.py enroll UID PASSWORD HANDLE_OUT
#   gk.py verify UID CHALLENGE_HEX(8 bytes, LE as in TA payload) HANDLE_IN PASSWORD TOKEN_OUT
# TOKEN_OUT = 69-byte hw_auth_token_t (type + timestamp big endian, like Android).
import os, struct, subprocess, sys

RAW = '/root/fp/rawcmd'

def enc_uint(major, n):
    if n < 24: return bytes([major << 5 | n])
    if n < 0x100: return bytes([major << 5 | 24, n])
    if n < 0x10000: return bytes([major << 5 | 25]) + struct.pack('>H', n)
    if n < 0x100000000: return bytes([major << 5 | 26]) + struct.pack('>I', n)
    return bytes([major << 5 | 27]) + struct.pack('>Q', n)

def enc_map(items):
    out = enc_uint(5, len(items))
    for k, v in items:
        out += enc_uint(0, k)
        out += enc_uint(2, len(v)) + v if isinstance(v, (bytes, bytearray)) else enc_uint(0, v)
    return out

def dec(b, i=0):
    ib = b[i]; major, ai = ib >> 5, ib & 31; i += 1
    if ai < 24: n = ai
    elif ai == 24: n = b[i]; i += 1
    elif ai == 25: n = struct.unpack_from('>H', b, i)[0]; i += 2
    elif ai == 26: n = struct.unpack_from('>I', b, i)[0]; i += 4
    elif ai == 27: n = struct.unpack_from('>Q', b, i)[0]; i += 8
    else: raise ValueError('cbor ai %d' % ai)
    if major == 0: return n, i
    if major == 1: return -1 - n, i
    if major in (2, 3): return bytes(b[i:i + n]), i + n
    if major == 4:
        arr = []
        for _ in range(n): v, i = dec(b, i); arr.append(v)
        return arr, i
    if major == 5:
        m = {}
        for _ in range(n):
            k, i = dec(b, i); v, i = dec(b, i); m[k] = v
        return m, i
    raise ValueError('cbor major %d' % major)

def send(cmd, cbor):
    open('/tmp/gk-req.bin', 'wb').write(struct.pack('<I', cmd) + cbor)
    env = dict(os.environ, REQ='/tmp/gk-req.bin', OUT='/tmp/gk-rsp.bin')
    out = subprocess.run([RAW, 'keymaster64', '0x1000', '0'], env=env, capture_output=True, text=True).stdout
    print(out.split('rsp:')[0].strip())
    rsp = open('/tmp/gk-rsp.bin', 'rb').read()
    status, ln = struct.unpack_from('<iI', rsp, 0)
    print('status', status, 'len', ln)
    if status != 0:
        return None
    m, _ = dec(rsp[8:8 + ln])
    print('rsp map keys', sorted(m.keys()) if isinstance(m, dict) else m)
    return m

def lsend(req):
    open('/tmp/gk-req.bin', 'wb').write(req)
    env = dict(os.environ, REQ='/tmp/gk-req.bin', OUT='/tmp/gk-rsp.bin')
    out = subprocess.run([RAW, 'keymaster64', '0x1000', '0'], env=env, capture_output=True, text=True).stdout
    print(out.split('rsp:')[0].strip())
    rsp = open('/tmp/gk-rsp.bin', 'rb').read()
    status, off, ln = struct.unpack_from('<iII', rsp, 0)
    print('status', status, 'off', off, 'len', ln)
    return rsp[off:off + ln] if status == 0 and ln else None

def lbuild(cmd, uid, word2, blobs):
    hdr = bytearray(0x20)
    struct.pack_into('<II', hdr, 0, cmd, uid)
    if word2 is not None:
        struct.pack_into('<Q', hdr, 8, word2)
    data = bytearray()
    for slot, blob in blobs:
        struct.pack_into('<II', hdr, slot, 0x20 + len(data), len(blob))
        data += blob
    return bytes(hdr + data)

mode = sys.argv[1]
if mode == 'lenroll':
    uid, pw, out = int(sys.argv[2]), sys.argv[3].encode(), sys.argv[4]
    h = lsend(lbuild(0x1001, uid, None, [(0x18, pw)]))
    if h:
        open(out, 'wb').write(h); print('handle', len(h), 'bytes')
elif mode == 'lverify':
    uid, chl, hin, pw, out = int(sys.argv[2]), bytes.fromhex(sys.argv[3]), sys.argv[4], sys.argv[5].encode(), sys.argv[6]
    challenge = struct.unpack('<Q', chl)[0]
    t = lsend(lbuild(0x1002, uid, challenge, [(0x10, open(hin, 'rb').read()), (0x18, pw)]))
    if t:
        open(out, 'wb').write(t); print('token', len(t), 'bytes:', t.hex())
elif mode == 'enroll':
    uid, pw, out = int(sys.argv[2]), sys.argv[3].encode(), sys.argv[4]
    m = send(0x21001, enc_map([(3, uid), (8, pw)]))
    if m and 6 in m:
        open(out, 'wb').write(m[6]); print('handle', len(m[6]), 'bytes')
elif mode == 'verify':
    uid, chl, hin, pw, out = int(sys.argv[2]), bytes.fromhex(sys.argv[3]), sys.argv[4], sys.argv[5].encode(), sys.argv[6]
    challenge = struct.unpack('<Q', chl)[0]
    handle = open(hin, 'rb').read()
    m = send(0x21002, enc_map([(3, uid), (4, challenge), (6, handle), (9, pw)]))
    if m:
        print({k: (v.hex() if isinstance(v, bytes) else v) for k, v in m.items()})
        tok = struct.pack('<BQQQ', m.get(11, 0), m.get(4, 0), m.get(12, 0), m.get(13, 0))
        tok += struct.pack('>I', m.get(14, 0)) + struct.pack('>Q', m.get(15, 0)) + m.get(16, b'')
        open(out, 'wb').write(tok); print('token', len(tok), 'bytes')
