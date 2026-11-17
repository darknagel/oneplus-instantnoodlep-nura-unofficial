// qseecomd: trace listener traffic of libqisl (QSEE Interrupt Service Listener)
function log(s) { console.log(s); }
function hex(p, n) { try { return hexdump(p, { length: n, header: false, ansi: false }); } catch (e) { return '<' + e + '>'; } }
function ts() { return (Date.now() % 1000000).toString().padStart(6, '0'); }
const libc = Process.getModuleByName('libc.so');
const readlink = new NativeFunction(libc.getExportByName('readlink'), 'int', ['pointer', 'pointer', 'size_t']);
function fdname(fd) {
  const b = Memory.alloc(256);
  const n = readlink(Memory.allocUtf8String('/proc/self/fd/' + fd), b, 255);
  return n > 0 ? b.readUtf8String(n) : '?';
}
const qisl = Process.findModuleByName('libqisl.so');
log('libqisl ' + (qisl ? qisl.base : 'not loaded'));
function inQisl(ctx) {
  try {
    const bt = Thread.backtrace(ctx, Backtracer.FUZZY).slice(0, 6);
    return bt.some(x => qisl && x.compare(qisl.base) >= 0 && x.compare(qisl.base.add(qisl.size)) < 0);
  } catch (e) { return false; }
}
const q = Process.getModuleByName('libQSEEComAPI.so');
for (const fn of ['QSEECom_receive_req', 'QSEECom_send_resp']) {
  Interceptor.attach(q.getExportByName(fn), {
    onEnter(a) { this.q = inQisl(this.context); this.h = a[0]; this.b = a[1]; this.n = a[2].toInt32();
      if (this.q && fn === 'QSEECom_send_resp') log(ts() + ' QISL send_resp len ' + this.n + ':\n' + hex(a[1], Math.min(this.n, 96))); },
    onLeave(r) { if (this.q && fn === 'QSEECom_receive_req') log(ts() + ' QISL receive_req -> ' + r + ' len ' + this.n + ':\n' + hex(this.b, Math.min(this.n, 96))); }
  });
}
// what does QISL poll/open/read
Interceptor.attach(libc.getExportByName('__open_2'), {
  onEnter(a) { this.p = a[0].readUtf8String(); this.q = inQisl(this.context); },
  onLeave(r) { if (this.q) log(ts() + ' QISL open ' + this.p + ' -> ' + r); }
});
Interceptor.attach(libc.getExportByName('poll'), {
  onEnter(a) { this.q = inQisl(this.context); if (this.q) { this.fds = a[0]; const fd = a[0].readS32(); log(ts() + ' QISL poll fd ' + fd + ' ' + fdname(fd) + ' events 0x' + a[0].add(4).readU16().toString(16) + ' timeout ' + a[2].toInt32()); } },
  onLeave(r) { if (this.q) log(ts() + ' QISL poll -> ' + r + ' revents 0x' + this.fds.add(6).readU16().toString(16)); }
});
log('qseecomd hooks ready');
