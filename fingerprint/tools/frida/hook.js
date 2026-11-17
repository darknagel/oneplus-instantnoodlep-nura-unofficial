// Log everything the Goodix HAL sends to QSEE + goodix_fp/ion ioctls
const out = [];
function log(s) { console.log(s); }
function hex(p, n) {
  try { return hexdump(p, { length: n, header: false, ansi: false }); } catch (e) { return '<' + e + '>'; }
}
const libc = Process.getModuleByName('libc.so');
const mmap = new NativeFunction(libc.getExportByName('mmap'), 'pointer', ['pointer', 'size_t', 'int', 'int', 'int', 'long']);
const munmap = new NativeFunction(libc.getExportByName('munmap'), 'int', ['pointer', 'size_t']);
const readlink = new NativeFunction(libc.getExportByName('readlink'), 'int', ['pointer', 'pointer', 'size_t']);
function fdname(fd) {
  const b = Memory.alloc(256);
  const n = readlink(Memory.allocUtf8String('/proc/self/fd/' + fd), b, 255);
  return n > 0 ? b.readUtf8String(n) : '?';
}
function dumpFd(fd, len, tag) {
  const p = mmap(ptr(0), 0x10000, 3, 1, fd, 0);
  if (p.equals(ptr(-1))) { log(tag + ' mmap fd ' + fd + ' failed'); return; }
  log(tag + ' fd ' + fd + ' (' + fdname(fd) + ') ' + len + ' B:\n' + hex(p, Math.min(len, 1024)));
  munmap(p, 0x10000);
}
let seq = 0;
function hookQsee(m) {
  for (const e of m.enumerateExports()) {
    if (e.type !== 'function' || !e.name.startsWith('QSEECom_')) continue;
    const name = e.name;
    Interceptor.attach(e.address, {
      onEnter(a) {
        this.n = ++seq; this.a = [a[0], a[1], a[2], a[3], a[4], a[5]];
        let s = '\n#' + this.n + ' ' + name + '(' + this.a.map(x => x.toString()).join(', ') + ')';
        if (name === 'QSEECom_start_app' || name === 'QSEECom_start_app_V2') {
          try { s += ' path=' + a[1].readUtf8String() + ' fname=' + a[2].readUtf8String(); } catch (e) {}
        }
        log(s);
        if (name.startsWith('QSEECom_send')) {
          const slen = a[2].toInt32();
          log('  req(' + slen + '):\n' + hex(a[1], Math.min(slen, 128)));
          if (name.indexOf('modified') >= 0) {
            log('  ion_fd_info:\n' + hex(a[5], 32));
            for (let i = 0; i < 4; i++) {
              const fd = a[5].add(i * 8).readS32(), off = a[5].add(i * 8 + 4).readU32();
              if (fd > 0) { log('  fd[' + i + ']=' + fd + ' off=0x' + off.toString(16) + ' ' + fdname(fd)); }
            }
            const fd0 = a[5].readS32();
            if (fd0 > 0) dumpFd(fd0, a[1].add(8).readU32(), '  payload-in');
          }
        }
      },
      onLeave(r) {
        let s = '#' + this.n + ' ' + name + ' -> ' + r;
        log(s);
        if (name.startsWith('QSEECom_send')) {
          log('  rsp:\n' + hex(this.a[3], Math.min(this.a[4].toInt32(), 64)));
          if (name.indexOf('modified') >= 0) {
            const fd0 = this.a[5].readS32();
            if (fd0 > 0) dumpFd(fd0, Math.min(this.a[1].add(8).readU32(), 96), '  payload-out');
          }
        }
      }
    });
  }
  log('hooked QSEECom_* in ' + m.name);
}
// ioctl: goodix_fp + ion alloc
Interceptor.attach(libc.getExportByName('ioctl'), {
  onEnter(a) {
    const fd = a[0].toInt32(); const n = fdname(fd);
    if (n.indexOf('goodix') >= 0 || n.indexOf('ion') >= 0 || n.indexOf('dma_heap') >= 0) {
      this.l = true;
      const req = a[1].toUInt32();
      let s = 'ioctl ' + n + ' 0x' + req.toString(16);
      if (n.indexOf('ion') >= 0 && !a[2].isNull()) s += '\n' + hex(a[2], 32);
      else if (!a[2].isNull() && a[2].compare(ptr(0x10000)) > 0) { try { s += ' arg=' + a[2].readU32(); } catch (e) { s += ' arg=' + a[2]; } }
      else s += ' arg=' + a[2];
      log(s);
    }
  },
  onLeave(r) { if (this.l) log('  -> ' + r); }
});
let qh = false;
const q = Process.findModuleByName('libQSEEComAPI.so');
if (q) { qh = true; hookQsee(q); }
else {
  Process.attachModuleObserver({
    onAdded(m) {
      if (m.name.indexOf('lib') === 0 && (m.path.indexOf('gf_') >= 0 || m.path.indexOf('goodix') >= 0 || m.name === 'libQSEEComAPI.so')) log('loaded ' + m.path);
      if (!qh && m.name === 'libQSEEComAPI.so') { qh = true; hookQsee(m); }
    }
  });
  log('waiting for libQSEEComAPI.so');
}
