#!/usr/bin/env python3
"""Make the voice call calibration of the OnePlus 8 Pro from its ACDB files.

The echo canceller and the rest of the call audio processing run in the
ADSP, in OnePlus' own vocproc topologies (0x1000bff1 Tx, 0x1000bff2 Rx).
The topologies and their calibration are in the ACDB files of the odm
partition (etc/acdbdata), which oneplus-ota-fetch downloads. This script
turns them into the files the kernel loads (q6core "topologies", q6cvp
"calibration"):

  topologies.bin          the custom topology definitions (Global_cal.acdb)
  {hs,spk}-{net}-{bw}.bin SET_PARAM_V3 payloads for a call on the handset
                          (earpiece) or the speakerphone, per network and
                          voice bandwidth: the static calibration of the Tx
                          and Rx modules, then the volume dependent one.

Usage: oneplus-voicecal ACDB_DIR OUT_DIR
"""
import os
import struct
import sys

# ACDB device IDs from the OnePlus audio_platform_info.xml: voice handset
# with two microphones (HANDSET_DMIC_AEC_NS) and the speakerphone.
DEVICES = {'hs': ('Handset', 41, 7), 'spk': ('Speaker', 43, 14)}
NETWORKS = {'gsm': 0x11360, 'wcdma': 0x11361, 'lte': 0x11363}
BANDWIDTHS = {'nb': 8000, 'wb': 16000}
AFE_RATE = 48000            # the device ports run at 48 kHz
VOLUME_STEP = 4             # of 0-8; the steps differ only in the Rx gain
OPMODE, MEDIA, FEATURE = 0x13085, 0x10fc0, 0x1308a
TOPOLOGY_PROP = 0x132ac     # topology definitions with module instances


def sections(path):
    d = open(path, 'rb').read()
    if d[:8] != b'QCMSNDDB':
        raise SystemExit('%s: not an ACDB file' % path)
    out, o = {}, 32
    while o + 12 <= len(d):
        name = d[o:o + 8].decode('ascii', 'replace')
        size, = struct.unpack_from('<I', d, o + 8)
        out[name] = d[o + 12:o + 12 + size]
        o += 12 + size
    return out


def u32s(b, off, n):
    return struct.unpack_from('<%dI' % n, b, off)


def table(b, width):
    n, = struct.unpack_from('<I', b, 0)
    return [u32s(b, 4 + 4 * width * i, width) for i in range(n)]


def pool(s, off):
    size, = struct.unpack_from('<I', s['DATAPOOL'], off)
    return s['DATAPOOL'][off + 4:off + 4 + size]


def params(s, prefix, ofst, row):
    """SET_PARAM_V3 payloads of one calibration row."""
    cdft, cdot = u32s(s[prefix + 'OFST'], ofst + 4 + 8 * row, 2)
    n, = struct.unpack_from('<I', s[prefix + 'CDFT'], cdft)
    out = b''
    for j in range(n):
        module, instance, param = u32s(s[prefix + 'CDFT'], cdft + 4 + 12 * j, 3)
        data = pool(s, u32s(s[prefix + 'CDOT'], cdot + 4 + 4 * j, 1)[0])
        out += struct.pack('<IHHII', module, instance, 0, param, len(data))
        out += data + b'\0' * (-len(data) % 4)
    return out


def static(s, tx, rx, net, rate):
    lut = [e for e in table(s['VSTILUT0'], 6)
           if e[:4] == (tx, rx, AFE_RATE, AFE_RATE)]
    if not lut:
        return None
    # rows: network, Tx rate, Rx rate, ...; the Tx modules are in the row
    # with the Rx rate 0, the Rx modules in the one with the Tx rate 0
    rows = table(s['VSTICVD0'], 7)
    out = []
    for want in ((rate, 0), (0, rate)):
        for i, r in enumerate(rows):
            if r[0] == net and r[1:3] == want and r[3:] == (OPMODE, OPMODE, MEDIA, FEATURE):
                out.append(params(s, 'VSTI', lut[0][4], i))
                break
    return b''.join(out) if len(out) == 2 else None


def dynamic(s, tx, rx, net, rate):
    lut = [e for e in table(s['VDYILUT0'], 5) if e[:3] == (tx, rx, 0)]
    if not lut:
        return b''
    rows = table(s['VDYICVD0'], 8)
    for i, r in enumerate(rows):
        if (r[0], r[2], r[3]) == (net, rate, VOLUME_STEP) and \
                r[4:] == (OPMODE, OPMODE, MEDIA, FEATURE):
            return params(s, 'VDYI', lut[0][3], i)
    return b''


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)

    g = sections(os.path.join(src, 'Global_cal.acdb'))
    topo = [off for prop, off in table(g['GPROPLUT'], 2) if prop == TOPOLOGY_PROP]
    if not topo:
        raise SystemExit('Global_cal.acdb: no topology definitions')
    files = {'topologies.bin': pool(g, topo[0])}

    for dev, (name, tx, rx) in DEVICES.items():
        s = sections(os.path.join(src, name + '_cal.acdb'))
        for net_name, net in NETWORKS.items():
            for bw, rate in BANDWIDTHS.items():
                cal = static(s, tx, rx, net, rate)
                if cal is None:
                    continue
                files['%s-%s-%s.bin' % (dev, net_name, bw)] = cal + dynamic(s, tx, rx, net, rate)

    for f, data in files.items():
        tmp = os.path.join(out, f + '.tmp')
        with open(tmp, 'wb') as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(out, f))
    print('oneplus-voicecal: wrote %d files to %s' % (len(files), out))


if __name__ == '__main__':
    main()
