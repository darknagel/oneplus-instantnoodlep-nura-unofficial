// Attach-mode tracer for the running Goodix HAL: TA cmds, goodix ioctls, netlink, sysfs/proc writes
function log(s) { console.log(s); }
function hex(p, n) { try { return hexdump(p, { length: n, header: false, ansi: false }); } catch (e) { return '<' + e + '>'; } }
const libc = Process.getModuleByName('libc.so');
const mmap = new NativeFunction(libc.getExportByName('mmap'), 'pointer', ['pointer', 'size_t', 'int', 'int', 'int', 'long']);
const munmap = new NativeFunction(libc.getExportByName('munmap'), 'int', ['pointer', 'size_t']);
const readlink = new NativeFunction(libc.getExportByName('readlink'), 'int', ['pointer', 'pointer', 'size_t']);
function fdname(fd) {
  const b = Memory.alloc(256);
  const n = readlink(Memory.allocUtf8String('/proc/self/fd/' + fd), b, 255);
  return n > 0 ? b.readUtf8String(n) : '?';
}
function ts() { return (Date.now() % 1000000).toString().padStart(6, '0'); }
function dumpFd(fd, len, tag, max) {
  const map = Math.max(0x10000, (len + 0xfff) & ~0xfff);
  const p = mmap(ptr(0), map, 3, 1, fd, 0);
  if (p.equals(ptr(-1))) { log(tag + ' mmap failed'); return; }
  log(tag + ' ' + len + ' B:\n' + hex(p, Math.min(len, max)));
  munmap(p, map);
}
let seq = 0;
const q = Process.getModuleByName('libQSEEComAPI.so');
for (const e of q.enumerateExports()) {
  if (e.type !== 'function' || !e.name.startsWith('QSEECom_')) continue;
  const name = e.name;
  if (name === 'QSEECom_app_load_query') continue;
  Interceptor.attach(e.address, {
    onEnter(a) {
      this.n = ++seq; this.a = [a[0], a[1], a[2], a[3], a[4], a[5]];
      if (name.indexOf('modified') >= 0) {
        const fd0 = a[5].readS32();
        const m = mmap(ptr(0), 0x1000, 1, 1, fd0, 0);
        const tgt = m.add(4).readU32(), cmd = m.add(8).readU32();
        munmap(m, 0x1000);
        this.tc = tgt + '/' + cmd;
        this.plen = a[1].add(8).readU32();
        log('\n' + ts() + ' #' + this.n + ' CMD ' + this.tc + ' size ' + this.plen);
        dumpFd(fd0, this.plen, '  in', 192);
      } else {
        log('\n' + ts() + ' #' + this.n + ' ' + name + '(' + this.a.map(x => x.toString()).join(', ') + ')');
        if (name.startsWith('QSEECom_send')) log('  req:\n' + hex(a[1], Math.min(a[2].toInt32(), 128)));
      }
    },
    onLeave(r) {
      if (name.indexOf('modified') >= 0) {
        const fd0 = this.a[5].readS32();
        const m = mmap(ptr(0), 0x1000, 1, 1, fd0, 0);
        const res = m.add(12).readU32();
        munmap(m, 0x1000);
        log(ts() + ' #' + this.n + ' CMD ' + this.tc + ' -> ' + r + ' result ' + res);
        dumpFd(fd0, this.plen, '  out', 192);
      } else {
        log(ts() + ' #' + this.n + ' ' + name + ' -> ' + r);
        if (name.startsWith('QSEECom_send')) log('  rsp:\n' + hex(this.a[3], Math.min(this.a[4].toInt32(), 64)));
      }
    }
  });
}
Interceptor.attach(libc.getExportByName('ioctl'), {
  onEnter(a) {
    const fd = a[0].toInt32(); const n = fdname(fd);
    if (n.indexOf('goodix') >= 0) { this.l = true; log(ts() + ' ioctl goodix 0x' + a[1].toUInt32().toString(16)); }
  },
  onLeave(r) { if (this.l && r.toInt32() !== 0) log('  -> ' + r); }
});
function hookRecv(fn) {
  Interceptor.attach(libc.getExportByName(fn), {
    onEnter(a) { this.fd = a[0].toInt32(); this.b = a[1]; this.msg = fn === 'recvmsg'; },
    onLeave(r) {
      const n = r.toInt32(); if (n <= 0) return;
      const name = fdname(this.fd);
      if (name.indexOf('socket') < 0) return;
      let buf = this.b;
      if (this.msg) { const iov = this.b.add(16).readPointer(); buf = iov.readPointer(); }
      log(ts() + ' ' + fn + ' fd ' + this.fd + ' ' + name + ' ' + n + ' B:\n' + hex(buf, Math.min(n, 64)));
    }
  });
}
['recv', 'recvfrom', 'recvmsg'].forEach(hookRecv);
const watch = {};
Interceptor.attach(libc.getExportByName('openat'), {
  onEnter(a) { try { this.p = a[1].readUtf8String(); } catch (e) { this.p = null; } },
  onLeave(r) {
    if (!this.p) return;
    if (this.p.startsWith('/sys') || this.p.startsWith('/proc') || this.p.startsWith('/dev')) {
      log(ts() + ' open ' + this.p + ' -> ' + r);
      if (r.toInt32() >= 0) watch[r.toInt32()] = this.p;
    }
  }
});
Interceptor.attach(libc.getExportByName('write'), {
  onEnter(a) {
    const fd = a[0].toInt32(); const n = a[2].toInt32();
    const name = watch[fd] || fdname(fd);
    if (name.startsWith('/sys') || name.startsWith('/proc')) {
      let s = ''; try { s = a[1].readUtf8String(Math.min(n, 64)); } catch (e) {}
      log(ts() + ' write ' + name + ' "' + s.replace(/\n/g, '\\n') + '"');
    }
  }
});
log('attached, hooks ready');
