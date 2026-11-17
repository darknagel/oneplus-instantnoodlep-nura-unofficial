#!/usr/bin/env python3
"""Join a split Qualcomm image (<name>.mdt + <name>.bNN) into one ELF (.mbn).
Handles ELF32 and ELF64. Segment N goes to its p_offset; .mdt supplies headers."""
import struct, sys, os

def main(mdt_path, out_path):
    base = mdt_path[:-4]
    mdt = open(mdt_path, 'rb').read()
    cls = mdt[4]
    if cls == 2:
        phoff, = struct.unpack_from('<Q', mdt, 0x20)
        phentsize, phnum = struct.unpack_from('<HH', mdt, 0x36)
        fmt = '<IIQQQQQQ'  # type flags offset vaddr paddr filesz memsz align
        get = lambda p: (p[0], p[2], p[5])
    else:
        phoff, = struct.unpack_from('<I', mdt, 0x1c)
        phentsize, phnum = struct.unpack_from('<HH', mdt, 0x2a)
        fmt = '<IIIIIIII'  # type offset vaddr paddr filesz memsz flags align
        get = lambda p: (p[0], p[1], p[4])
    segs = []
    for i in range(phnum):
        p = struct.unpack_from(fmt, mdt, phoff + i * phentsize)
        segs.append(get(p))
    size = max(off + fsz for _, off, fsz in segs)
    out = bytearray(size)
    out[:len(mdt)] = mdt
    for i, (typ, off, fsz) in enumerate(segs):
        if not fsz:
            continue
        seg_file = '%s.b%02d' % (base, i)
        if not os.path.exists(seg_file):
            if off + fsz <= len(mdt):
                continue  # already inside the .mdt
            sys.exit('missing ' + seg_file)
        data = open(seg_file, 'rb').read()
        if len(data) != fsz:
            sys.exit('%s: size %d != p_filesz %d' % (seg_file, len(data), fsz))
        out[off:off + fsz] = data
        print('seg %d type %d off 0x%x size 0x%x <- %s' % (i, typ, off, fsz, os.path.basename(seg_file)))
    open(out_path, 'wb').write(out)
    print('wrote %s (%d bytes, ELF%d)' % (out_path, size, 64 if cls == 2 else 32))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
