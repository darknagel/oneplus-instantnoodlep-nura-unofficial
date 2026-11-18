# OnePlus 8 Pro (instantnoodlep) – unofficial Nura mainline port

Patches and a ready-to-flash image that turn the OnePlus 8 Pro (IN2023, Snapdragon 865) into
a Linux phone running [Nura](https://nura.eco) (formerly postmarketOS) on a mainline kernel.
Unofficial and independent: not affiliated with or supported by the Nura project. Tool and
package names still say `postmarketos`, so the commands here do too.

Questions and reports: [XDA thread](https://xdaforums.com/t/unofficial-mainline-linux-nura-formerly-postmarketos-for-oneplus-8-pro-instantnoodlep.4807386/)

> [!WARNING]
> **Images up to v2026.11.10 overcharge the battery (4.76 V instead of 4.35 V).** Flash
> v2026.11.15 or [update the kernel](#update-an-older-image); `apk upgrade` does not fix it.
> Found by naorunaoru.

**Contents:** [Status](#status) · [Install](#install) · [First login](#first-login) ·
[Desktop](#desktop) · [Phone features](#phone-features) ·
[Update an older image](#update-an-older-image) · [Troubleshooting](#troubleshooting) ·
[Known issues](#known-issues) · [Build it yourself](#build-it-yourself)

## Status

Everything on the phone works, except what is listed below: display (1440×3168, 120 Hz),
touch, GPU, sound, Wi-Fi, Bluetooth, USB networking, calls (VoLTE and 2G), SMS, mobile
data, GPS, NFC, all five cameras, the sensors, the fingerprint reader, hardware video
decoding and encoding,
charging, vibration, torch, and an external display over USB-C.

Not working or limited:

| Area | State |
|---|---|
| Fingerprint reader | works with `fprintd`; in Plasma Mobile also screen unlock and setup in the settings (`goodix-fp-overlay`); not in Phosh, no login with a finger |
| Fast charging (Warp) and wireless charging | not done; charging is 5 V, up to 2 A into the battery |
| Camera autofocus | phase detection on the main camera only, the other cameras use contrast |
| Calls | no echo cancellation, see [`modem/`](modem/) |
| NFC | reading tags only; writing and card emulation are untested |
| Charging | the last ten percent are slow, and the phone does not sleep while charging, see [`docs/charging.md`](docs/charging.md) |
| External display | sound over the monitor breaks after system sleep, see [`docs/displayport.md`](docs/displayport.md) |

Tested on IN2023 phones (EU) with the Samsung AMS678UW01 panel. With another panel the
screen may stay black, see [`docs/panel-log.md`](docs/panel-log.md). Patch-by-patch details:
[`docs/patches.md`](docs/patches.md).

## Install

**You need:**

- an unlocked bootloader (`fastboot flashing unlock`, this wipes the phone)
- `fastboot` from the Android platform tools
- a backup of `super` if you want to go back to Android: the image overwrites it. See the
  [wiki page](https://wiki.nura.eco/wiki/OnePlus_8_Pro_(oneplus-instantnoodlep)).

**Flash:**

1. Download the files from [Releases](../../releases) and check them: `sha256sum -c SHA256SUMS`
2. Power off, then hold **Volume up + Volume down + Power** for about ten seconds.
3. In the folder with the files:

   ```sh
   fastboot set_active a
   fastboot flash dtbo_a dtbo.img
   fastboot flash boot_a boot.img
   fastboot flash super oneplus-instantnoodlep-rootfs.img
   fastboot reboot
   ```

   If `set_active` says "unknown command", check with `fastboot getvar current-slot`. Slot
   `a` is fine, carry on. On slot b the phone finds the old Android boot image and stays black.

The image is console only. It contains no Wi-Fi networks, SSH keys or personal data. At first
boot it grows the file system and copies the modem, DSP and video firmware and the proximity
calibration from your phone's own partitions. It contains no proprietary OnePlus files: once
the phone has internet, `oneplus-ota-fetch` downloads the fingerprint firmware and the sensor
configuration from OnePlus' official update (about 40 MB, checked against known hashes).
Reboot once after that for the sensors.

## First login

Connect USB. The phone appears as a network adapter at `172.16.42.1`.

```sh
ssh root@172.16.42.1        # password: root
passwd                      # do this first, anyone on your network can log in until then
nmtui                       # connect to Wi-Fi
```

Then `apk update`, but read [Known issues](#known-issues) before `apk upgrade`.

## Desktop

| Interface | Package | Notes |
|---|---|---|
| Phosh | `postmarketos-ui-phosh` | tested |
| Plasma Mobile | `postmarketos-ui-plasma-mobile` | tested |
| Sxmo | `postmarketos-ui-sxmo-de-sway` | not tried |

Your user **must have the ID 10000**, Nura starts the interface for exactly this ID. Use a
numeric password, the lock screen shows a number pad. As root:

```sh
apk update
adduser -u 10000 -g "" alice                         # pick your own name
for g in audio input plugdev video netdev feedbackd wheel; do addgroup alice $g 2>/dev/null; done
apk add xdg-user-dirs && su alice -c xdg-user-dirs-update   # camera apps need ~/Pictures
apk add postmarketos-base-ui-audio-backend-pipewire xwayland   # sound and X11 apps, see below
apk add postmarketos-ui-phosh stevia-schemas         # stevia-schemas: Phosh keyboard fix
apk add doas && echo 'permit persist :wheel' > /etc/doas.d/wheel.conf
reboot
```

Install one interface at a time, and the PipeWire audio backend first: the image's sound
settings are made and tested for PipeWire, and apk may pick PulseAudio for Plasma Mobile
otherwise. To switch later:
`apk add postmarketos-base-ui-audio-backend-pipewire && reboot`. Without `xwayland`, Plasma
Mobile's background services hang at login, and the volume keys and other shortcuts do
nothing.
Useful apps: `snapshot` (camera), `spacebar` (SMS in Plasma Mobile). With your own user you
can switch off root login over SSH:
`rm /etc/ssh/sshd_config.d/10-oneplus-instantnoodlep-release.conf`

Using the phone as a small server (screen off, charge limit, sleep): [`docs/server.md`](docs/server.md).

## Phone features

### Mobile data and SMS

As root, about a minute after boot:

```sh
mmcli -i any --pin=YOURPIN                       # only if your SIM has a PIN
nmcli con add type gsm ifname '*' con-name mobile apn YOUR_APN gsm.pin-flags 4
```

The connection comes back on its own after the PIN at every boot. On congstar, use
`apn internet.v6.telekom gsm.username congstar gsm.password cs`. In a desktop you can also
enter PIN and APN in the settings; if Plasma Mobile keeps asking for the APN password:
`nmcli con mod NAME gsm.password-flags 0 gsm.password YOURPASSWORD`

Send an SMS from the console, with the country code in the number:

```sh
S=$(mmcli -m any --messaging-create-sms="text='Hello',number='+49...'" | sed -n 's|.*/SMS/\([0-9]*\).*|\1|p')
mmcli -s $S --send
mmcli -m any --messaging-list-sms
```

More about the modem: [`modem/`](modem/).

### GPS

```sh
cat /dev/gnss-sdx55         # NMEA, the first fix takes a few minutes outside
```

For apps: `apk add gpsd && gpsd -n /dev/gnss-sdx55`

### Fingerprint

```sh
fprintd-enroll -f right-thumb
fprintd-verify
```

Place the finger on the blue ring at the bottom of the screen; the screen lights up under it
while it captures. Move the finger a little between touches while enrolling. The sensor's
firmware comes from `oneplus-ota-fetch` at first boot (`journalctl -u oneplus-ota-fetch`).
How it works and its limits: [`fingerprint/image/README.md`](fingerprint/image/README.md).

In Plasma Mobile, install `goodix-fp-overlay` from the release as root (with the
`libfprint` of the same release), then log out and in again:

```sh
apk add --allow-untrusted goodix-fp-overlay-*.apk
```

While a finger is needed it shows a round Breeze-style plate with a ring in your accent
colour and the fingerprint icon over the sensor, on the desktop and on the lock screen, in
every screen rotation. Under the finger it lights the sensor white at full brightness. It
also sets up the lock screen's fingerprint service. On the lock screen, put the finger on
the ring: the phone unlocks right away, also after it slept. After five wrong fingers the
lock screen wants the PIN until it locks again.

Add fingers in Settings → Users → Configure Fingerprint Authentication. After you pick a
finger, a password dialog opens after a few seconds; tap the field to get the keyboard. If
the settings then show "Did not receive a reply" (they wait only 25 s), close the message
and pick the finger again: the password is remembered for a few minutes. Or as root:
`fprintd-enroll -f right-index-finger USER`.

### Sensors

The sensors work after the first boot with internet and one reboot (see above):
`monitor-sensor` shows accelerometer, light and
proximity, `monitor-sensor --compass` the heading. The compass becomes accurate after the
phone has been moved around in a figure eight. Details, the sensor DSP and how to set up
older images: [`docs/sensors.md`](docs/sensors.md).

### Video

The video codec (Venus) decodes H.264, HEVC, VP8, VP9 and more and encodes H.264 and HEVC,
which saves a lot of CPU and battery. Players use it through V4L2, for example
`mpv --hwdec=v4l2m2m-copy VIDEO`, `ffmpeg -c:v h264_v4l2m2m -i VIDEO ...` or GStreamer's
`v4l2h264dec`. Check with `ls /sys/class/video4linux/*/name | xargs grep venus`.
The firmware is signed for this phone and comes from its own `modem` partition at first boot;
on images before v2026.11.10 see [Update an older image](#update-an-older-image).

### NFC

```sh
systemctl add-wants multi-user.target neard
systemctl start neard
nfctool --device nfc0 --enable
nfctool --device nfc0 --poll=Initiator
```

Reading tags works. Writing and card emulation are not tested. There is no app for it yet.

### External display

USB-C to DisplayPort or HDMI with video, audio, a USB hub and charging at the same time.
Details and tested monitors: [`docs/displayport.md`](docs/displayport.md).

## Update an older image

To keep your installed system, install the kernel package from the newest release instead of
flashing the image. As root, with the file copied to the phone:

```sh
apk add --allow-untrusted linux-postmarketos-qcom-sm8250-*.apk
reboot
```

This replaces the kernel and its modules together. Do not flash only `boot.img` onto an older
image, its modules would not match. The release notes list the other packages that belong
to a release (camera, VoLTE). Check the charging with `dmesg | grep pm8150b-charger`: from
v2026.11.15 on it must say `charging policy uses bq27411-0`, on older kernels
`float voltage 4350000 uV`.

**Images before v2026.11.10** also miss the boot service that copies the video, compute and
sensor DSP firmware from your phone. As root:

```sh
apk add pil-squasher
wget -O /usr/local/bin/dsp-firmware https://raw.githubusercontent.com/darknagel/oneplus-instantnoodlep-nura-unofficial/main/firmware/dsp-firmware.sh
wget -O /etc/systemd/system/dsp-firmware.service https://raw.githubusercontent.com/darknagel/oneplus-instantnoodlep-nura-unofficial/main/firmware/dsp-firmware.service
chmod 755 /usr/local/bin/dsp-firmware
systemctl enable dsp-firmware
reboot
```

It copies Venus, CDSP and SLPI firmware and the sensor DSP libraries from the slot the
bootloader started, and imports the proximity calibration. Existing copies are kept.
For the compass and sensor setup on old images see [`docs/sensors.md`](docs/sensors.md).

## Troubleshooting

- **Windows does not set up the USB network:** in Device Manager, right-click the device →
  **Update driver** → **Browse my computer** → **Let me pick** → **Network adapters** →
  **Microsoft** → **UsbNcm Host Device**.
- **Proximity stays "far" when covered:** the calibration is missing, see
  [`docs/sensors.md`](docs/sensors.md#proximity).
- **No sensors at all:** `journalctl -u slpi-guard` shows if the sensor DSP crashed three
  times and was stopped ([#1](../../issues/1)); it stays off until the next reboot.
  `unexpected SMEM item size 4684` in `dmesg` means an image older than v2026.11.10.
- **Apps report `Resource busy` for the camera** after testing with `cam` or `media-ctl`:
  `media-ctl -d /dev/media0 -r` (`apk add v4l-utils`).
- **No or very quiet sound in a desktop:** switch to PipeWire, see [Desktop](#desktop). `wpctl status`
  must list "Speaker playback", not only a dummy output.
- **Cameras missing after a libcamera update:** `systemctl --user restart pipewire wireplumber`
- **Black screen after flashing:** check the slot (see [Install](#install)) and the panel,
  [`docs/panel-log.md`](docs/panel-log.md).

## Known issues

- **`apk upgrade` can remove fixes.** The patched kernel, ModemManager, libcamera and
  iio-sensor-proxy can be replaced when Nura publishes a higher version. If modem or data
  break afterwards, check first: `apk policy modemmanager`
- Cameras: colours, shading and exposure come from the stock tuning; white balance is
  automatic only (no colour temperature curve from the stock tuning yet). The main camera
  runs at 4000×3000 and 30 fps, also for the preview, because only that mode has its phase
  detection pixels; it focuses in about 0.5–1 second (`LIBCAMERA_SIMPLE_PDAF=0` gives a
  60 fps preview with the slower contrast autofocus). The ultrawide previews at 2000×1500
  and 60 fps; its autofocus takes about 1 second.
- The last ten percent of a charge take about 50 minutes, longer than on Android, and the
  phone does not sleep while the battery is charging: see [`docs/charging.md`](docs/charging.md).
- Under Plasma Mobile the keyboard did not always open in the SIM PIN popup. Enter the PIN in
  the settings or with `mmcli`.
- Your phone's modem data (`/lib/firmware/postmarketos/qcom/sdx55m`, calibration and IDs)
  is copied at first boot. Never share it.

## Build it yourself

You need Linux (WSL2 works) with [pmbootstrap](https://docs.postmarketos.org/pmbootstrap/).

```sh
git clone https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial.git ~/instantnoodlep-patches
pmbootstrap init            # vendor oneplus, device instantnoodlep
cd "$(pmbootstrap config aports)"
git checkout -b instantnoodlep
git am --whitespace=nowarn ~/instantnoodlep-patches/pmaports-patches/*.patch
pmbootstrap build linux-postmarketos-qcom-sm8250 device-oneplus-instantnoodlep \
    firmware-oneplus-instantnoodlep alsa-ucm-conf-oneplus-instantnoodlep hexagonrpcd
pmbootstrap build --arch aarch64 libcamera modemmanager iio-sensor-proxy
pmbootstrap install
pmbootstrap flasher flash_dtbo
pmbootstrap flasher flash_rootfs
pmbootstrap flasher flash_kernel
```

The pmaports patches already contain the kernel and libcamera patches. Your own image also
needs the services from [`modem/`](modem/) and [`firmware/`](firmware/) (with `pil-squasher`),
the script from [`sensors/`](sensors/) and the files in [`system/`](system/); the prebuilt
image has all of them. Repository layout and how to change the kernel:
[`docs/patches.md`](docs/patches.md).

## License

Each patch keeps the license of the project it applies to. The image contains Nura/Alpine
packages under their own licenses, and the firmware Nura distributes; the kernel source is the tag in
[`docs/patches.md`](docs/patches.md) plus `kernel-patches/`. README: CC0.

No warranty. Flashing your phone is at your own risk.
