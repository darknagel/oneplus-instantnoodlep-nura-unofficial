#!/usr/bin/env python3
# Probe a remote OTA zip: range support, payload.bin location, partition list.
import struct, sys, urllib.request, zlib

URL = sys.argv[1]

def get(start, length):
    req = urllib.request.Request(URL, headers={'Range': 'bytes=%d-%d' % (start, start + length - 1)})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 206:
            raise SystemExit('no range support (HTTP %d)' % r.status)
        return r.read(), r.headers

# total size
d, h = get(0, 4)
total = int(h['Content-Range'].split('/')[1])
print('size', total, 'MB', total // 2**20)
# end of central directory (+ zip64)
tail_len = min(total, 1 << 16)
tail, _ = get(total - tail_len, tail_len)
eocd = tail.rfind(b'PK\x05\x06')
cd_size, cd_off = struct.unpack_from('<II', tail, eocd + 12)
if cd_off == 0xffffffff:
    loc = tail.rfind(b'PK\x06\x07')
    z64, = struct.unpack_from('<Q', tail, loc + 8)
    rec, _ = get(z64, 56)
    cd_size, cd_off = struct.unpack_from('<QQ', rec, 40)
cd, _ = get(cd_off, cd_size)
i = 0
entries = {}
while i < len(cd) and cd[i:i + 4] == b'PK\x01\x02':
    method, = struct.unpack_from('<H', cd, i + 10)
    csize, usize = struct.unpack_from('<II', cd, i + 20)
    nlen, elen, clen = struct.unpack_from('<HHH', cd, i + 28)
    lho, = struct.unpack_from('<I', cd, i + 42)
    name = cd[i + 46:i + 46 + nlen].decode()
    extra = cd[i + 46 + nlen:i + 46 + nlen + elen]
    j = 0
    while j + 4 <= len(extra):
        hid, hsz = struct.unpack_from('<HH', extra, j)
        if hid == 1:
            vals = list(struct.unpack_from('<%dQ' % (hsz // 8), extra, j + 4))
            if usize == 0xffffffff: usize = vals.pop(0)
            if csize == 0xffffffff: csize = vals.pop(0)
            if lho == 0xffffffff: lho = vals.pop(0)
        j += 4 + hsz
    entries[name] = (method, csize, usize, lho)
    i += 46 + nlen + elen + clen
for n, e in entries.items():
    print('  %-40s method %d size %d' % (n, e[0], e[2]))
method, csize, usize, lho = entries['payload.bin']
lh, _ = get(lho, 30)
nlen, elen = struct.unpack_from('<HH', lh, 26)
pstart = lho + 30 + nlen + elen
print('payload.bin at', pstart, 'stored' if method == 0 else 'COMPRESSED')
hdr, _ = get(pstart, 24)
assert hdr[:4] == b'CrAU', hdr[:4]
ver, msize = struct.unpack_from('>QQ', hdr, 4)
sigsize, = struct.unpack_from('>I', hdr, 20)
print('payload v%d manifest %d bytes' % (ver, msize))
manifest, _ = get(pstart + 24, msize)
open('/tmp/ota-manifest.bin', 'wb').write(manifest)
open('/tmp/ota-info.txt', 'w').write('%d %d %d\n' % (pstart, msize, sigsize))
print('saved manifest; data starts at payload+%d' % (24 + msize + sigsize))
