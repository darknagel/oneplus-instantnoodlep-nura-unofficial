#!/usr/bin/env python3
# Open the voice call audio path while a ModemManager call is up: enable the
# mixer routes (loudspeaker, microphones) and hold the hostless CS-Voice
# PCM open in both directions, so the ADSP runs its voice session for the
# modem. Run as root (sdx55-callaudio.service). Test helper until UCM and a
# proper call audio daemon handle this.
#
# Echo cancellation: when oneplus-voicecal has made the calibration from the
# OnePlus ACDB (oneplus-ota-fetch runs it), the vocproc uses OnePlus' own
# topologies with both microphones, and the calibration for the current
# route (earpiece or speakerphone), network and voice bandwidth is sent once
# audio runs, and again after the route changes. Without the files the call
# runs without processing as before.
import ctypes, errno, os, re, subprocess, time

LIVE = ('dialing', 'ringing-out', 'active', 'held', 'waiting')
START = ('ringing-out', 'active')
DELAY = 1.0
MIX = (("TERT_MI2S_RX Voice Mixer CS-Voice", None),
       ("CS-Voice Capture Mixer VA_CODEC_DMA_TX_0", None),
       ("VA_AIF1_CAP Mixer DEC0", None))
SET = (("VA DEC0 MUX", "VA_DMIC"), ("VA DMIC MUX0", "DMIC2"), ("VA_DEC0 Volume", "120"))
# second microphone for the OnePlus dual microphone topology
MIX_EC = (("VA_AIF1_CAP Mixer DEC1", None),)
SET_EC = (("VA DEC1 MUX", "VA_DMIC"), ("VA DMIC MUX1", "DMIC1"), ("VA_DEC1 Volume", "120"))

VOICECAL = 'oneplus-instantnoodlep/voice'
TX_TOPOLOGY, RX_TOPOLOGY = 0x1000bff1, 0x1000bff2
Q6CORE = '/sys/module/q6core/parameters/'
Q6CVP = '/sys/module/q6cvp/parameters/'
# The OnePlus modules accept their calibration only once audio runs.
CAL_DELAY = 2.0
CAL_TRIES = 5

a = ctypes.CDLL("libasound.so.2")
pcms = []
ec = False
cal = {'at': None, 'route': None, 'tries': 0}


def log(*args):
    print(*args, flush=True)


def cset(name, val):
    subprocess.run(['amixer', '-q', '-c0', 'cset', "name='%s'" % name, str(val)])


def cget(name):
    out = subprocess.run(['amixer', '-c0', 'cget', "name='%s'" % name],
                         capture_output=True, text=True).stdout
    m = re.search(r': values=(\S+)', out)
    return m.group(1) if m else None


def sysfs(path, val):
    # one write() call: a buffered file would write again when closed after
    # an error
    fd = os.open(path, os.O_WRONLY)
    try:
        os.write(fd, val.encode())
    finally:
        os.close(fd)


def setup_ec():
    """Register the OnePlus topologies and switch the vocproc to them."""
    if not os.path.exists('/lib/firmware/%s/topologies.bin' % VOICECAL):
        return False
    try:
        sysfs(Q6CORE + 'topologies', '%s/topologies.bin' % VOICECAL)
        sysfs(Q6CVP + 'tx_topology', str(TX_TOPOLOGY))
        sysfs(Q6CVP + 'rx_topology', str(RX_TOPOLOGY))
        sysfs(Q6CVP + 'tx_channels', '2')
        sysfs(Q6CVP + 'cvd_v3', '1')
    except OSError as e:
        log('echo cancellation off: %s' % e)
        return False
    log('echo cancellation on')
    return True


def device():
    for l in open('/proc/asound/pcm'):
        if 'CS-Voice' in l:
            return ('hw:0,%d' % int(l.split(':')[0].split('-')[1])).encode()


def start():
    for n, _ in MIX + (MIX_EC if ec else ()):
        cset(n, 1)
    for n, v in SET + (SET_EC if ec else ()):
        cset(n, v)
    dev = device()
    for stream in (0, 1):
        p = ctypes.c_void_p()
        if a.snd_pcm_open(ctypes.byref(p), dev, stream, 0) < 0:
            log('open failed', stream); continue
        a.snd_pcm_set_params(p, 2, 3, 1, 8000, 1, 500000)
        if stream == 0:  # hostless: never stop on underrun
            sw = ctypes.c_void_p(); b = ctypes.c_ulong()
            a.snd_pcm_sw_params_malloc(ctypes.byref(sw)); a.snd_pcm_sw_params_current(p, sw)
            a.snd_pcm_sw_params_get_boundary(sw, ctypes.byref(b))
            a.snd_pcm_sw_params_set_stop_threshold(p, sw, b); a.snd_pcm_sw_params(p, sw)
        pcms.append(p)
    for p in reversed(pcms):
        a.snd_pcm_start(p)
    cal.update(at=time.monotonic() + CAL_DELAY, route=None, tries=0)
    log('voice path on')


def stop():
    for p in pcms:
        a.snd_pcm_drop(p); a.snd_pcm_close(p)
    pcms.clear()
    for n, _ in MIX[:2]:
        cset(n, 0)
    cal['at'] = None
    log('voice path off')


def network():
    out = subprocess.run(['mmcli', '-m', 'any', '-K'], capture_output=True, text=True).stdout
    tech = ' '.join(re.findall(r'access-technologies\.value\[\d+\]\s*:\s*(\S+)', out))
    if 'lte' in tech or '5gnr' in tech:
        return 'lte'
    if any(t in tech for t in ('umts', 'hsdpa', 'hsupa', 'hspa')):
        return 'wcdma'
    return 'gsm'


def route():
    return 'spk' if cget('Bottom Speaker Switch') == 'on' else 'hs'


def calibrate():
    """Send the calibration for the current route; True when the ADSP took it."""
    r, net = route(), network()
    # wideband first: the narrowband data has a shorter microphone filter, the
    # ADSP rejects the wideband data while the call runs at 8 kHz. The OnePlus
    # module keeps a rejected filter in its configuration and fails every
    # parameter until the next filter replaces it, so a file can need a
    # second pass after another one was rejected.
    for bw in ('wb', 'nb'):
        name = '%s/%s-%s-%s.bin' % (VOICECAL, r, net, bw)
        if not os.path.exists('/lib/firmware/' + name):
            continue
        for attempt in range(2):
            try:
                sysfs(Q6CVP + 'calibration', name + ' -')
            except OSError as e:
                if e.errno == errno.EIO:
                    continue
                log('calibration %s: %s' % (name, e))
                return False
            cal['route'] = r
            log('calibration %s' % name)
            return True
    return False


def states():
    out = subprocess.run(['mmcli', '-m', 'any', '--voice-list-calls'], capture_output=True, text=True).stdout
    return re.findall(r'\(([a-z-]+)\)\s*$', out, re.M)


ec = setup_ec()
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
    elif pcms and ec and cal['at'] and time.monotonic() >= cal['at']:
        # first calibration, and again after a switch between earpiece
        # and speakerphone
        if cal['route'] is None or cal['route'] != route():
            if calibrate():
                cal['tries'] = 0
            else:
                cal['tries'] += 1
                if cal['tries'] >= CAL_TRIES:
                    log('calibration failed, the call runs without it')
                    cal['at'] = None
                else:
                    cal['at'] = time.monotonic() + 1.0
    time.sleep(0.2)
