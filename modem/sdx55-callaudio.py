#!/usr/bin/env python3
# Open the voice call audio path while a ModemManager call is up: enable the
# mixer routes (loudspeaker, main microphone) and hold the hostless CS-Voice
# PCM open in both directions, so the ADSP runs its voice session for the
# modem. Run as root (sdx55-callaudio.service). Test helper until UCM and a
# proper call audio daemon handle this.
import ctypes, re, subprocess, time

LIVE = ('dialing', 'ringing-out', 'active', 'held', 'waiting')
START = ('ringing-out', 'active')
DELAY = 1.0
MIX = (("TERT_MI2S_RX Voice Mixer CS-Voice", None),
       ("CS-Voice Capture Mixer VA_CODEC_DMA_TX_0", None),
       ("VA_AIF1_CAP Mixer DEC0", None))
SET = (("VA DEC0 MUX", "VA_DMIC"), ("VA DMIC MUX0", "DMIC2"), ("VA_DEC0 Volume", "120"))

a = ctypes.CDLL("libasound.so.2")
pcms = []


def cset(name, val):
    subprocess.run(['amixer', '-q', '-c0', 'cset', "name='%s'" % name, str(val)])


def device():
    for l in open('/proc/asound/pcm'):
        if 'CS-Voice' in l:
            return ('hw:0,%d' % int(l.split(':')[0].split('-')[1])).encode()


def start():
    for n, _ in MIX:
        cset(n, 1)
    for n, v in SET:
        cset(n, v)
    dev = device()
    for stream in (0, 1):
        p = ctypes.c_void_p()
        if a.snd_pcm_open(ctypes.byref(p), dev, stream, 0) < 0:
            print('open failed', stream, flush=True); continue
        a.snd_pcm_set_params(p, 2, 3, 1, 8000, 1, 500000)
        if stream == 0:  # hostless: never stop on underrun
            sw = ctypes.c_void_p(); b = ctypes.c_ulong()
            a.snd_pcm_sw_params_malloc(ctypes.byref(sw)); a.snd_pcm_sw_params_current(p, sw)
            a.snd_pcm_sw_params_get_boundary(sw, ctypes.byref(b))
            a.snd_pcm_sw_params_set_stop_threshold(p, sw, b); a.snd_pcm_sw_params(p, sw)
        pcms.append(p)
    for p in reversed(pcms):
        a.snd_pcm_start(p)
    print('voice path on', flush=True)


def stop():
    for p in pcms:
        a.snd_pcm_drop(p); a.snd_pcm_close(p)
    pcms.clear()
    for n, _ in MIX[:2]:
        cset(n, 0)
    print('voice path off', flush=True)


def states():
    out = subprocess.run(['mmcli', '-m', 'any', '--voice-list-calls'], capture_output=True, text=True).stdout
    return re.findall(r'\(([a-z-]+)\)\s*$', out, re.M)


# The uplink stays silent when our session exists before the modem has set
# up its own, so wait until the call is alerting or connected and give the
# modem a moment (it sets up its vocoder when the traffic channel comes up).
since = None
while True:
    try:
        st = states()
    except Exception:
        st = []
    ready = any(s in START for s in st)
    up = any(s in LIVE for s in st)
    if ready and not pcms:
        since = since or time.monotonic()
        if time.monotonic() - since >= DELAY:
            start()
    elif not up:
        since = None
        if pcms:
            stop()
    time.sleep(0.2)
