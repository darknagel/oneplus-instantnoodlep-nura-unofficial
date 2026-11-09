# OnePlus 8 Pro (instantnoodlep) – unofficial Nura mainline port

Patches and a ready-to-flash image that turn the OnePlus 8 Pro (IN2023, Snapdragon 865) into
a Linux phone running [Nura](https://nura.eco) (formerly postmarketOS) on a mainline kernel.
Unofficial and independent: not affiliated with or supported by the Nura project. Tool and
package names still say `postmarketos`, so the commands here do too.

Questions and reports: [XDA thread](https://xdaforums.com/t/unofficial-mainline-linux-nura-formerly-postmarketos-for-oneplus-8-pro-instantnoodlep.4807386/)

## What works

| Feature | State |
|---|---|
| Display (1440×3168 @ 120 Hz), touch, GPU | works |
| Speakers, 3 microphones | works |
| Wi-Fi, Bluetooth, USB networking | works |
| Modem: SIM with PIN, LTE/5G, SMS | works |
| Mobile data | works, tested on congstar (IPv6 only, up to 90 Mbit/s) |
| GPS | works, fix without SIM |
| NFC | reading tags works |
| Main, ultrawide, telephoto and front camera, colour filter camera | works, autofocus on main, ultrawide and telephoto |
| Accelerometer, light, proximity, gyroscope | works, sensor files included since v2026.11.08, see [Sensors](#sensors) |
| Magnetometer and compass | works in your own build with kernel 0046–0047 and the [compass fix](#compass); not in the image yet |
| Video decoding and encoding in hardware (Venus: H.264, HEVC, VP9 and more) | works in your own build with [`firmware/`](firmware/); not in the image yet, see [Video](#video) |
| Optical image stabilisation (OIS), main camera | works in your own build with kernel 0053–0054; not in the image yet |
| Calls, OIS of the telephoto camera | not done |

Tested on one IN2023 (EU) with the Samsung AMS678UW01 panel. With another panel the screen
may stay black, see [`docs/panel-log.md`](docs/panel-log.md). Technical details and patch
numbers: [`docs/patches.md`](docs/patches.md).

## Install

**You need:**

- an unlocked bootloader (`fastboot flashing unlock`, this wipes the phone)
- `fastboot` from the Android platform tools
- a backup of `super` if you want to go back to Android: the image overwrites it. See the
  [wiki page](https://wiki.nura.eco/wiki/OnePlus_8_Pro_(oneplus-instantnoodlep)).

**Flash:**

1. Download or build the files from [Releases](../../releases) and check them: `sha256sum -c SHA256SUMS`
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

**First login:** connect USB. The phone appears as a network adapter at `172.16.42.1`.

```sh
ssh root@172.16.42.1        # password: root
passwd                      # do this first, anyone on your network can log in until then
nmtui                       # connect to Wi-Fi
```

Then update with `apk update`, but read [Known issues](#known-issues) before `apk upgrade`.

The image is console only. It contains no Wi-Fi networks, SSH keys, personal data or modem
data. At first boot it fills the storage and copies the modem firmware from your phone's
own partitions. Since v2026.11.08 it also contains OnePlus' sensor files, see [Sensors](#sensors).

Windows does not set up the USB network? In Device Manager: right-click the device →
**Update driver** → **Browse my computer** → **Let me pick** → **Network adapters** →
**Microsoft** → **UsbNcm Host Device**.

## Set up

### Mobile data and SMS

As root, about a minute after boot:

```sh
mmcli -i any --pin=YOURPIN                       # only if your SIM has a PIN
nmcli con add type gsm ifname '*' con-name mobile apn YOUR_APN
```

The connection then comes back on its own after the PIN at every boot. On congstar, use
`apn internet.v6.telekom gsm.username congstar gsm.password cs`.

With a desktop, you can also enter the PIN and APN in the settings. If Plasma Mobile then
keeps asking for the APN password, save it in the connection:
`nmcli con mod NAME gsm.password-flags 0 gsm.password YOURPASSWORD`

Send an SMS, with the country code in the number:

```sh
S=$(mmcli -m any --messaging-create-sms="text='Hello',number='+49...'" | sed -n 's|.*/SMS/\([0-9]*\).*|\1|p')
mmcli -s $S --send
mmcli -m any --messaging-list-sms
```

Under Plasma Mobile, use the app: `apk add spacebar`, then log in again. More about the
modem: [`modem/`](modem/).

### GPS

```sh
cat /dev/gnss-sdx55         # NMEA, the first fix takes a few minutes outside
```

For apps: `apk add gpsd && gpsd -n /dev/gnss-sdx55`

### Sensors

Since v2026.11.08 the image contains the files the sensor DSP needs: the DSP libraries and
the sensor configuration from OxygenOS (SLPI firmware `SLPI.HY.3.0-00262`). These are
proprietary OnePlus/Qualcomm files. The sensors work right after flashing, check with
`monitor-sensor`.

Some bootloaders expose a 4684-byte sensor-information item and need kernel patch 0049,
which is not in v2026.11.08. Without it, the kernel reports
`unexpected SMEM item size 4684` and the accelerometer is unavailable.

On an IN2023 with older stock firmware, the packaged SLPI firmware also prevented the
audio DSP from starting (`start timed out`, `-110`). The updated [`firmware/`](firmware/)
service copies this phone's own SLPI firmware before drivers load, alongside Venus and
CDSP; use the [firmware setup below](#video) on older images and reboot.
The copies live in `/lib/firmware/updates/postmarketos`, overriding the packaged firmware
without replacing package-owned files. See [audio testing and limits](docs/audio.md).

SLPI builds of the same version read the sensor list in shared memory (SMEM item 130) in
different layouts: older ones with 2 chips per sensor type, newer ones with 3. Kernel patches
0061–0062 take the layout from the list itself, so the phone's own SLPI firmware finds the
magnetometer. Without them, as in v2026.11.08 and older images, the phone's own SLPI
firmware loses the magnetometer and compass; use the firmware service there only if the
audio DSP does not start.

If the sensor DSP crashes 3 times within 60 seconds, `slpi-guard` stops it instead of
letting the kernel restart it forever, which used to break most of the phone
([#1](../../issues/1)). The sensors are then off until the next reboot,
`journalctl -u slpi-guard` shows if it stepped in.

#### Compass

The magnetometer needs kernel patches 0046–0047, which are not in an image yet. The compass
heading (`monitor-sensor --compass`) also needs the gyro calibration in the sensor DSP, and
OnePlus switches off the software motion detector that it depends on
(`kona_amd_sw_disabled.json`). `setup-sensors` keeps it on. On v2026.11.08, as root:

```sh
C=/usr/share/qcom/sm8250/OnePlus/instantnoodlep/sensors/config
rm $C/kona_amd_sw_disabled.json
printf '{"config":{"hw_platform":["MTP"],"soc_id":["356"]},"sns_amd":{"owner":"sns_amd","enabled":{"ver":"0","type":"int","data":"1"}}}
' > $C/mainline_amd_sw_enabled.json
sed -i 's/"enabled":{"type":"int","ver":"0","data":"0"}/"enabled":{"type":"int","ver":"0","data":"1"}/' /var/lib/hexagonrpcd/sensors-registry/registry/sns_amd
reboot
```

The heading becomes accurate after the calibration has seen the phone moved around (a
figure eight).

**Older images or your own build** need the files from your own phone:

1. **Before flashing**, with Android running and USB debugging on (not tested on Android,
   some files may need root):

   ```sh
   adb pull /vendor/etc/sensors vendor
   adb pull /odm/etc/sensor odm
   ```

2. After flashing, copy them over USB:

   ```sh
   ssh root@172.16.42.1 mkdir -p /root/android-sensors
   scp -r vendor odm root@172.16.42.1:/root/android-sensors/
   ```

3. On the phone. The script also copies the DSP files from the `dsp_a` partition (`dsp_b` if
   the phone started slot b).

   ```sh
   setup-sensors /root/android-sensors
   reboot
   ```

4. Check: `ssccli --sensor accelerometer --timeout 3`

Already on Linux? Get `vendor.img` and `odm.img` from a full OxygenOS update (not tested).
The DSP libraries come from your phone's own `dsp` partition, so they match the OxygenOS
version you had. The `firmware/` service does the same at boot.

### Video

The video codec (Venus) decodes H.264, HEVC, VP8, VP9 and more and encodes H.264 and HEVC,
which saves a lot of CPU and battery. It needs firmware signed for this phone, which is on
your phone's active `modem_a` or `modem_b` partition but may not be passed on.
Images after v2026.11.08 copy it at first boot. On older images, as root:

```sh
apk add pil-squasher
wget -O /usr/local/bin/dsp-firmware https://raw.githubusercontent.com/darknagel/oneplus-instantnoodlep-nura-unofficial/main/firmware/dsp-firmware.sh
wget -O /etc/systemd/system/dsp-firmware.service https://raw.githubusercontent.com/darknagel/oneplus-instantnoodlep-nura-unofficial/main/firmware/dsp-firmware.service
chmod 755 /usr/local/bin/dsp-firmware
systemctl enable dsp-firmware
reboot
```

This also installs the matching sensor-DSP firmware (SLPI), replaces the sensor-DSP
libraries with the ones from your phone's own `dsp` partition, and starts the compute DSP
(CDSP). All copies come from the slot the bootloader started (normally a). Existing local
overrides are kept; rerunning the service does not replace them.
Check with `ls /sys/class/video4linux/*/name | xargs grep venus`.
Players use it through V4L2, for example `mpv --hwdec=v4l2m2m-copy VIDEO` or
`ffmpeg -c:v h264_v4l2m2m -i VIDEO ...`, and GStreamer through `v4l2h264dec`.

### NFC

```sh
systemctl add-wants multi-user.target neard
systemctl start neard
nfctool --device nfc0 --enable
nfctool --device nfc0 --poll=Initiator
```

Reading tags works. Writing and card emulation are not tested. There is no app for it yet.

### Desktop (optional)

| Interface | Package | Notes |
|---|---|---|
| Phosh | `postmarketos-ui-phosh` | tested |
| Plasma Mobile | `postmarketos-ui-plasma-mobile` | tested |
| Sxmo | `postmarketos-ui-sxmo-de-sway` | not tried |

Your user **must have the ID 10000**, Nura starts the interface for exactly this ID. Use a
numeric password, the lock screen shows a number pad.

```sh
apk update
adduser -u 10000 -g "" alice                         # pick your own name
for g in audio input plugdev video netdev feedbackd wheel; do addgroup alice $g 2>/dev/null; done
apk add xdg-user-dirs && su alice -c xdg-user-dirs-update   # camera apps need ~/Pictures
apk add postmarketos-ui-phosh stevia-schemas         # stevia-schemas: Phosh keyboard fix
apk add doas && echo 'permit persist :wheel' > /etc/doas.d/wheel.conf
reboot
```

Install one interface at a time. Camera app: `apk add snapshot`. With your own user you can
switch off root login: `rm /etc/ssh/sshd_config.d/10-oneplus-instantnoodlep-release.conf`

Using the phone as a small server (screen off, charge limit, sleep):
[`docs/server.md`](docs/server.md).

## Known issues

- **`apk upgrade` can remove fixes.** The patched kernel and ModemManager can be replaced when
  Nura publishes a higher version. If modem or data break afterwards, this is the first thing
  to check: `apk policy modemmanager`.
- The screen does not rotate under Phosh or Plasma Mobile: iio-sensor-proxy 3.9 loses a
  claim that arrives while it opens the sensors at boot, so the accelerometer never starts.
  Fixed by [`iio-sensor-proxy-patches/`](iio-sensor-proxy-patches/), not in an image yet.
  Build iio-sensor-proxy 3.9 with the patch and `-Dssc-support=enabled`.
- Under Plasma Mobile the keyboard did not always open in the SIM PIN popup. Enter the PIN
  in the settings or with `mmcli`.
- The front camera is too dark.
- At some boots the front camera failed and all cameras were missing. Fixed by kernel
  patches 0050–0051, which are not in an image yet. Until then:
  `echo 23-0010 > /sys/bus/i2c/drivers/imx471/bind`
- Ultrawide autofocus sometimes failed at boot and then stayed off until the next reboot
  (`Lens initialisation failed` in libcamera). Fixed by kernel patch 0048, which is not in an
  image yet.
- Main and ultrawide camera: one mode each (4000x3000 at 30 fps) and contrast autofocus only,
  which takes about 3 seconds and is not always right. Bright areas clip.
- After testing with `cam` or `media-ctl`, run `media-ctl -d /dev/media0 -r` (`apk add v4l-utils`),
  otherwise apps fail with `Resource busy`.
- After a new libcamera: `systemctl --user restart pipewire wireplumber`
- Modem data is copied with the first boot: `/lib/firmware/postmarketos/qcom/sdx55m` holds your
  calibration and IDs. Never share it.

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
pmbootstrap build --arch aarch64 libcamera modemmanager
pmbootstrap install
pmbootstrap flasher flash_dtbo
pmbootstrap flasher flash_rootfs
pmbootstrap flasher flash_kernel
```

The pmaports patches already contain the kernel and libcamera patches. Your own image also
needs the services from [`modem/`](modem/) and [`firmware/`](firmware/) (with `pil-squasher`) and the
script from [`sensors/`](sensors/), which the prebuilt image already has (`firmware/` from the next image). Repository layout and how to change the kernel:
[`docs/patches.md`](docs/patches.md).

## License

Each patch keeps the license of the project it applies to. The image contains Nura/Alpine
packages under their own licenses, the firmware Nura distributes and, since v2026.11.08,
OnePlus' proprietary sensor files, which none of these licenses cover; the kernel source is
the tag in [`docs/patches.md`](docs/patches.md) plus `kernel-patches/`. README: CC0.

No warranty. Flashing your phone is at your own risk.
