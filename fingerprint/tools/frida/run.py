import frida, sys, time, os
here = os.path.dirname(os.path.abspath(__file__))
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
outp = open(os.path.join(here, 'hal-trace.txt'), 'w', encoding='utf-8')
def on_msg(m, d):
    if m['type'] == 'log':
        outp.write(m['payload'] + '\n')
    else:
        outp.write(repr(m) + '\n')
    outp.flush()
dev = frida.get_device_manager().add_remote_device('127.0.0.1:27042')
pid = dev.spawn(['/odm/bin/hw/vendor.oplus.hardware.biometrics.fingerprint@2.1-service'])
s = dev.attach(pid)
sc = s.create_script(open(os.path.join(here, 'hook.js'), encoding='utf-8').read())
sc.on('message', on_msg)
s.on('detached', lambda *a: outp.write('DETACHED %r\n' % (a,)))
sc.set_log_handler(lambda lvl, txt: (outp.write(txt + '\n'), outp.flush()))
sc.load()
dev.resume(pid)
print('pid', pid)
time.sleep(secs)
outp.close()
print('done')
