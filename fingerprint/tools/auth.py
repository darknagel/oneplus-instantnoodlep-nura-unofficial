#!/usr/bin/env python3
# Enroll a fingerprint with the Goodix G5 TA on mainline (OnePlus 8 Pro).
# Needs: fp-hold (goodix_fp held open), qsee-supplicant with RPMB listener,
# gfp9608 loaded + init chain done, keymaster HMAC key handed over (1000/10),
# setActiveGroup (1000/0) done, gatekeeper handle for uid 1000.
# Lights a white disk under the finger on /dev/fb0 at each touch, then captures.
import fcntl, mmap, os, re, struct, subprocess, sys, time

OPTEST = '/root/fp/optest'
TOUCH = sys.argv[1] if len(sys.argv) > 1 else '/dev/input/event4'
FB_W, FB_H, FB_STRIDE = 1440, 3168, 5760
RADIUS = 190

def tee(target, cmd, size, env_extra=None, payload=None):
    env = dict(os.environ, NOPOWER='1')
    if env_extra: env.update(env_extra)
    if payload is not None:
        open('/tmp/enr-payload.bin', 'wb').write(payload)
        env['PAYLOAD'] = '/tmp/enr-payload.bin'
    out = subprocess.run([OPTEST, str(target), str(cmd), str(size), '8'], env=env,
                         capture_output=True, text=True, timeout=30).stdout
    m = re.search(r'payload result@0xc = (\d+)', out)
    res = int(m.group(1)) if m else -1
    data = bytearray()
    if 'payload:' in out:
        for line in out.split('payload:')[1].strip().split('\n'):
            line = line.strip()
            if not re.match(r'^([0-9a-f]{2} ?)+$', line): break
            data += bytes.fromhex(line.replace(' ', ''))
    return res, bytes(data)

# ---- framebuffer -------------------------------------------------------------
fbfd = os.open('/dev/fb0', os.O_RDWR)
# write() (not mmap) so the DRM fbdev emulation gets damage and flushes to the panel
def disk(cx, cy, color):
    px = struct.pack('<I', color)
    y0, y1 = max(0, cy - RADIUS), min(FB_H - 1, cy + RADIUS)
    band = bytearray(os.pread(fbfd, (y1 - y0 + 1) * FB_STRIDE, y0 * FB_STRIDE))
    for y in range(y0, y1 + 1):
        dy = y - cy
        dx = int((RADIUS * RADIUS - dy * dy) ** 0.5)
        x0, x1 = max(0, cx - dx), min(FB_W - 1, cx + dx)
        off = (y - y0) * FB_STRIDE + x0 * 4
        band[off:off + (x1 - x0 + 1) * 4] = px * (x1 - x0 + 1)
    os.pwrite(fbfd, bytes(band), y0 * FB_STRIDE)
def clear():
    os.pwrite(fbfd, b'\0' * (FB_STRIDE * FB_H), 0)

# ---- touchscreen ---------------------------------------------------------------
tfd = os.open(TOUCH, os.O_RDONLY)
def absmax(code):
    buf = bytearray(24)
    fcntl.ioctl(tfd, 0x80184540 + code, buf)
    return struct.unpack('<6i', buf)[2]
XMAX, YMAX = absmax(0x35), absmax(0x36)
print('touch range', XMAX, YMAX, flush=True)
EV = struct.Struct('<qqHHi')
def wait_touch(down):
    x = y = None; tracking = None
    while True:
        ev = os.read(tfd, EV.size * 64)
        for i in range(0, len(ev), EV.size):
            _, _, t, c, v = EV.unpack_from(ev, i)
            if t == 3 and c == 0x39:
                tracking = v
                if not down and v == -1:
                    return None
            elif t == 3 and c == 0x35: x = v
            elif t == 3 and c == 0x36: y = v
            elif t == 1 and c == 0x14a:
                if down and v == 1 and x is not None and y is not None:
                    return x * (FB_W - 1) // XMAX, y * (FB_H - 1) // YMAX
                if not down and v == 0:
                    return None
        if down and tracking is not None and tracking >= 0 and x is not None and y is not None:
            return x * (FB_W - 1) // XMAX, y * (FB_H - 1) // YMAX

# ---- authenticate -----------------------------------------------------------------
subprocess.run(['sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink; dmesg -n 1'])
clear()
SENSOR = (720, 2547)
def ring(color):
    global RADIUS
    keep = RADIUS
    RADIUS = 200; disk(SENSOR[0], SENSOR[1], color)
    RADIUS = 185; disk(SENSOR[0], SENSOR[1], 0)
    RADIUS = keep
ring(0x0000a0ff)
gp = bytearray(288); gs = b'/data/vendor_de/0/fpdata'; gp[0x20:0x20 + len(gs)] = gs
res, _ = tee(1000, 0, 288, payload=bytes(gp))
print('set active group (1000/0):', res, flush=True)
res, d7 = tee(1000, 7, 112)
print('fingers:', struct.unpack_from('<I', d7, 0x1c)[0] if len(d7) >= 0x20 else '?', flush=True)
res, _ = tee(1000, 1, 40)
print('auth start (1000/1):', res, flush=True)
AUTH_SET = '0x24:w:1,0x58:w:2,0x88:w:1,0x90:w:1,0x94:w:0x1c'
for n in range(1, int(os.environ.get('TRIES', '10')) + 1):
    print('>>> Finger auflegen', flush=True)
    xy = wait_touch(True)
    disk(xy[0], xy[1], 0x00ffffff)
    time.sleep(0.08)
    tee(1002, 9, 32)
    result = None
    for attempt in range(4):
        tee(1001, 15, 48)
        tee(1002, 3, 56, {'SET': '0x20:w:2,0x28:w:1'})
        r101, _ = tee(1002, 101, 80, {'SET': '0x20:w:1,0x2c:w:0x092c,0x30:w:0x0bbf,0x34:w:0x21c,0x38:w:0x776,0x3c:w:0x42a80000,0x40:w:0x7f'})
        r2, d2 = tee(1001, 2, 176, {'SET': AUTH_SET})
        fid = struct.unpack_from('<I', d2, 0x30)[0] if len(d2) >= 0x34 else 0
        print('  try %d: capture=%d auth=%d fid=0x%x' % (attempt + 1, r101, r2, fid), flush=True)
        result = (r2, fid)
        if r2 == 0: break
    tee(1002, 8, 28)
    ok = result and result[0] == 0
    print('touch %d: %s' % (n, 'MATCH fid=0x%x' % result[1] if ok else 'no match (%s)' % (result[0] if result else '?')), flush=True)
    wait_touch(False)
    disk(xy[0], xy[1], 0)
    ring(0x0000ff00 if ok else 0x00ff0000)
