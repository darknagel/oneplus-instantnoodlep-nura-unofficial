# Modem & GPS (SDX55)

**Works:** modem online, LTE + 5G bands, GPS fix without SIM, SIM with PIN,
network registration, mobile data (IPv6 only, up to 90 Mbit/s, tested on congstar),
SMS send and receive.
**Not done:** calls.
Tested on one IN2023 (EU). The prebuilt image has all of this; the setup below is
only for your own build.

## Setup

1. Build and flash the kernel with all pmaports patches (0018 and 0020: kernel,
   0019: ModemManager), see
   "Build it yourself" in the [main README](../README.md).
2. On the phone, as root:

   ```sh
   apk add git
   git clone https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial.git
   sh oneplus-instantnoodlep-nura-unofficial/modem/install.sh
   reboot
   ```

3. Check:

   ```sh
   sdx55-modemstate        # should say "online"
   cat /dev/gnss-sdx55     # NMEA, first fix after a few minutes outside
   ```

GPS for apps: `apk add gpsd && gpsd -n /dev/gnss-sdx55`. The GNSS session runs while a
program reads `/dev/gnss-sdx55` and stops when the last one closes it.

Mobile data on congstar, as root (the password is the public one of the APN):

```sh
nmcli con add type gsm ifname '*' con-name congstar apn internet.v6.telekom gsm.username congstar gsm.password cs gsm.pin-flags 4
```

SMS app for Plasma Mobile: `apk add spacebar`, then log in again. Enter numbers
with the country code (`+49...`).

## Calls

Voice calls work with audio in both directions (kernel patches 0117–0137, pmaports 0058),
tested outgoing and incoming over VoLTE and outgoing over 2G (CSFB) on congstar with
`plasma-dialer`. The vocoder runs in the
ADSP of the SM8250; the modem and the ADSP exchange the speech frames over PCIe through a
shared mailbox and talk to each other over QRTR, which the kernel forwards between the MHI
link and GLINK.

- `sdx55-callaudio` (root service) watches ModemManager. Once a call is alerting or
  connected it enables the mixer routes (speakers, main microphone) and holds the hostless
  `CS-Voice` PCM open, which starts the voice session in the ADSP. Opening it before the
  modem has set up its own session leaves the uplink silent, hence the short delay.
- `sdx55-callaudiod` (session service, D-Bus activated) stands in for `callaudiod`, which
  needs a speaker and an earpiece port on one sink; PipeWire puts them into separate
  profiles. It implements the same interface and switches the amplifiers directly: the
  earpiece is the top speaker alone at a lower gain (`Top Speaker Volume`), the speaker
  button turns both on, mute sets the microphone gain to zero. If the session bus still
  starts `callaudiod`, put the same service file into `~/.local/share/dbus-1/services/`.

Echo cancellation (kernel 0241–0242, pmaports 0108): OnePlus runs the call audio
processing in the ADSP in its own vocproc topologies, `0x1000bff1` (Tx, two microphones,
with OnePlus' echo canceller module `0x1000b500`) and `0x1000bff2` (Rx, module
`0x1000b501`). Their definitions and calibration are in the ACDB files of the odm
partition. `oneplus-ota-fetch` downloads `Global_cal.acdb`, `Handset_cal.acdb` and
`Speaker_cal.acdb` from the official OTA, and `oneplus-voicecal` turns them into
`/lib/firmware/oneplus-instantnoodlep/voice/`: `topologies.bin` and one calibration file
per route (`hs` earpiece, `spk` speakerphone), network (`gsm`, `wcdma`, `lte`) and voice
bandwidth (`nb`, `wb`), each the static calibration of the Tx and Rx modules plus the
volume dependent one. When the files exist, `sdx55-callaudio` registers the topologies
(`q6core.topologies`), switches the vocproc to them with the CVD 2.2 setup
(`q6cvp.cvd_v3`), adds the second microphone (`VA_DEC1`, DMIC1) and writes the matching
calibration to `q6cvp.calibration` two seconds after the call audio starts, and again
when the route changes. The OnePlus modules create their state only once audio flows
through them and reject their parameters before that, which is why the calibration
cannot go with the session setup. The ADSP also rejects wideband data while the call runs
at 8 kHz (a longer microphone filter), so `sdx55-callaudio` falls back to the narrowband
file. `journalctl -u sdx55-callaudio` shows the file it used. Without the files the call
runs without processing as before.

Limits: the microphone gain is fixed at +36 dB (`VA_DEC0 Volume` 120; at +24 dB the
other side heard us too quietly), the calibration uses the middle of OnePlus' nine
volume steps, incoming calls over 2G are untested, and several of the kernel patches are still marked WIP: which of the
mailbox placement patches are really needed has not been narrowed down.

What made it work in the end: the SDX55 has two QRTR nodes behind its MHI link. Forwarded
control packets were addressed to the first one, so the flow control release (RESUME_TX)
from the ADSP never reached the node the modem's voice task sends from, and its eleventh
command, the one that selects the mailbox, blocked forever.

### VoLTE

The IMS stack (SIP registration, IPsec, the voice call itself) runs inside the modem, but
the modem asks the AP for its IMS data connection through the QMI IMS Data service. On
Linux `81voltd` provides that service and creates the bearer through ModemManager.
Upstream 81voltd only accepts a modem whose QMI port is called `qrtr0`; ModemManager calls
the external SDX55 `qrtr3` (its QRTR node), so pmaports 0069 forks the package with a patch
that accepts any `qrtr*` port. With it the modem brings up APN `ims` (profile 2, IPv6),
registers at `ims.telekom.de` (AKA + IPsec) and calls stay on LTE; the audio path is the
same as for 2G calls. The carrier configuration `Commercial-DT-VOLTE` was already selected
by the modem. Tested on congstar (Telekom network).

Build and install: `pmbootstrap build --arch aarch64 81voltd`, install `81voltd` and
`81voltd-systemd` on the phone; the service is enabled on install.

The modem asks for the IMS connection right after the SIM unlock, while ModemManager still
initialises the modem; pmaports 0087 makes 81voltd try again for up to a minute, and
pmaports 0089 makes it wait until the modem is registered and repeat a connection attempt
that ModemManager cancelled. Without VoLTE a call falls back to 2G, and mobile data stops
for the length of the call. If it still fails, the modem does not ask again until 81voltd
restarts (`systemctl restart 81voltd`).

## System sleep

- For suspend the PCIe host takes the link to the modem down (kernel 0171); the modem
  keeps running and stays registered. On resume the link comes back and MHI goes from M3
  to M0. With the link left in L1.2 the modem was gone after a suspend in which it had
  something to say.
- The modem wakes the phone with WAKE# (GPIO 87, kernel 0172–0173), for an incoming call
  or message.
- Anything that makes the modem talk ends the sleep at once. Three things did:
  NetworkManager took the IMS bearer down together with mobile data (pmaports 0090 leaves
  it up), ModemManager asked for WDS event reports (0090 drops them), and the GNSS session
  runs at 1 Hz (`sdx55-gnss-sleep.service` stops it for the sleep).
- The GNSS session only runs while a program has `/dev/gnss-sdx55` open. A running
  session makes the modem write to its EFS and send it to the phone a few minutes later,
  and when the session ended for the sleep it did so right after the phone fell asleep:
  seven of eight two-minute sleeps ended after about 85 s with the modem's WAKE#. With
  the session only running for a reader, seven of eight lasted the full two minutes.
- Mobile data stays connected over suspend (pmaports 0103). The address stays the same,
  and data that arrives for the phone wakes it. An open SSH session keeps the phone from
  sleeping.

## Facts

- The modem firmware **must come from your own modem partition** of the slot the
  bootloader started (`modem_a` on a normal install) –
  `install.sh` copies it. The firmware package of the distribution is a
  different version; with it the modem stays offline.
- Modem data (EFS, NV, DDR) is copied from your own partitions too. It
  contains calibration and IDs: **never share it**.
- Without a SIM, ModemManager lists the modem as failed (`sim-missing`); GPS
  still works through `sdx55-gnss`.
- The modem does not activate the SIM on its own; `sdx55-sim` does it. Both
  slots were tested for detection, network registration only in slot 1.
- Data only runs on the `IP_HW0` channel (`mhi_hwip0`). `sdx55-sim` loads
  `mhi_net` and then starts ModemManager, about 30 s after the modem is up.
- That one channel carries both the internet connection and the IMS connection for
  VoLTE. ModemManager multiplexes it (QMAP): each connection gets its own `rmnet` link,
  `qmapmux0.0`, `qmapmux0.1`, ... (pmaports 0085–0086). Without that, mobile data did not
  come up while 81voltd was running.
- Unmodified ModemManager needs pmaports patch 0019: it aborts after a SIM PIN
  unlock and cannot use `mhi_net` over QRTR. A later `apk upgrade` can replace
  the patched package.
- If the modem crashes: reboot.
- Kernel patches 0023–0030 are still debug quality.
