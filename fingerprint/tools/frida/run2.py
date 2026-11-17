import frida, sys, time, os
here = os.path.dirname(os.path.abspath(__file__))
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 60
outp = open(os.path.join(here, sys.argv[2] if len(sys.argv) > 2 else 'capture-trace.txt'), 'w', encoding='utf-8')
def w(tag):
    def f(lvl, txt):
        outp.write('[%s] %s\n' % (tag, txt)); outp.flush()
    return f
dev = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
procs = {p.name: p.pid for p in dev.enumerate_processes()}
hal = [p for n, p in procs.items() if 'fingerprint@2.1-service' in n]
qd = [p for n, p in procs.items() if n.startswith('qseecomd')]
print('hal', hal, 'qseecomd', qd)
sessions = []
for pid, js, tag in [(hal[0], 'hook2.js', 'HAL')] + [(p, 'hookq.js', 'QSD%d' % p) for p in qd]:
    s = dev.attach(pid)
    sc = s.create_script(open(os.path.join(here, js), encoding='utf-8').read())
    sc.set_log_handler(w(tag))
    sc.on('message', lambda m, d, tag=tag: (outp.write('[%s] MSG %r\n' % (tag, m)), outp.flush()))
    sc.load()
    sessions.append((s, sc))
print('READY', flush=True)
time.sleep(secs)
for s, sc in sessions:
    try: s.detach()
    except Exception: pass
outp.close()
print('done')
