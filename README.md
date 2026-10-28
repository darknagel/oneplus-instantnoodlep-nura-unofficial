# OnePlus 8 Pro (instantnoodlep) – mainline Linux

Patches and a ready-to-flash image that turn the OnePlus 8 Pro (IN2023,
`oneplus-instantnoodlep`, Snapdragon 865 / SM8250) into a Linux phone running
[postmarketOS](https://postmarketos.org) on a mainline kernel.

> **AI disclosure:** These patches and the image were made with substantial help from an AI
> coding assistant (Claude). Everything marked "works" was tested on a real device.
> Because of this, nothing here is submitted to postmarketOS, whose policy forbids
> AI-assisted contributions. Use it, learn from it, or reimplement it – but if you forward
> any of this to a project, check that project's rules on AI-generated code first.

For general information about the device under postmarketOS (partition layout, USB quirks,
how to return to Android) see the wiki page:
**https://wiki.nura.eco/wiki/OnePlus_8_Pro_(oneplus-instantnoodlep)**

---

## 1. Easy flash: the prebuilt image

The [Releases](../../releases) page has a minimal image. It makes the phone a small Linux
computer you reach over SSH; you then install whatever you want on top (see section 2).

**What's in it**

- postmarketOS edge, console only (no desktop), NetworkManager, OpenSSH server
- kernel `linux-postmarketos-qcom-sm8250` 7.2 with all patches from this repository
  (display 1440×3168 @ 120 Hz, GPU, audio, Wi-Fi, Bluetooth, USB networking, cameras,
  telephoto autofocus) – the modem work is **not** included
- firmware: only what postmarketOS distributes anyway (`firmware-oneplus-instantnoodlep`,
  `linux-firmware-ath11k`, `linux-firmware-qcom`)
- **login: user `root`, password `root`, SSH enabled.** Change the password right after the
  first login (`passwd`) – until you do, anyone on your network can log in as root.
- no Wi-Fi networks, no SSH keys, no personal data; SSH host keys are generated on first boot

**Not in it**

- the sensor files (accelerometer, light, proximity): they come from OnePlus' stock firmware
  and may not be redistributed – see "Enable the sensors" below
- modem, calls, SMS, mobile data, GPS
- main and ultrawide camera (C-PHY), optical image stabilisation

**Tested hardware**

Tested on a single device with the **Samsung AMS678UW01** display panel (the panel driver is
written for exactly this panel; Android reports it as `oppo19811_samsung_1440_3168_dsc_cmd`).
If your phone has a different panel, the screen may stay black – the phone is then still
reachable over USB/SSH. Please open an issue with your panel name if that happens.

### Requirements

- unlocked bootloader (`fastboot flashing unlock` – this wipes the phone)
- `fastboot` from the Android platform tools on your PC
- **a backup of the `super` partition if you ever want to go back to Android** – the image
  overwrites it. See the wiki page above for how to save and restore it.

### Flashing

1. Download the release files and check them: `sha256sum -c SHA256SUMS`
2. Boot the phone into fastboot: power off, then hold **Volume up + Volume down + Power**
   (from a fully powered-off state hold for about ten seconds).
3. Flash (run the commands in the folder with the files):

   ```sh
   fastboot set_active a
   fastboot flash dtbo_a dtbo.img
   fastboot flash boot_a boot.img
   fastboot flash super oneplus-instantnoodlep-rootfs.img
   fastboot reboot
   ```

   `fastboot set_active a` matters: if the phone ever boots slot b, it finds the old Android
   boot image there and shows a black screen.

4. The first boot takes a minute. You get a text login on the screen.

### First login

Connect the phone to your PC with a USB cable. It shows up as a network adapter, and the
phone is reachable at `172.16.42.1`:

```sh
ssh root@172.16.42.1        # password: root
passwd                      # set a new root password – do this first
nmtui                       # connect to Wi-Fi
apk update && apk upgrade   # bring the system up to date
```

On Windows, `ssh` works the same in PowerShell. If the USB network does not come up, log in
on the phone's screen with a USB keyboard (USB-C hub with external power).

---

## 2. Install a desktop (Phosh)

Phosh is the GNOME-based phone interface. Phosh does not run as root, so create a normal
user first:

```sh
apk update
adduser -g "" alice                                  # pick your own name
for g in audio input plugdev video netdev feedbackd wheel; do
    addgroup alice $g 2>/dev/null
done
apk add postmarketos-ui-phosh stevia-schemas        # stevia-schemas fixes the on-screen keyboard
apk add doas && echo 'permit persist :wheel' > /etc/doas.d/wheel.conf   # "doas" instead of sudo
reboot
```

After the reboot the Phosh lock screen appears; log in with the user you created. Useful
additions:

```sh
apk add snapshot          # camera app (telephoto and front camera, with autofocus)
apk add gnome-software    # app store
```

Other interfaces work the same way, e.g. `apk add postmarketos-ui-plasma-mobile` or
`postmarketos-ui-sxmo-de-sway` instead of `postmarketos-ui-phosh`.

Once you have your own user, you can switch off the root login over SSH:
`rm /etc/ssh/sshd_config.d/10-oneplus-instantnoodlep-release.conf` and log in as your user.

---

## 3. Status

| Feature | State | Patches |
|---|---|---|
| Display (Samsung AMS678UW01, new panel driver, 1440×3168 @ 120 Hz) | works | kernel 0001–0003, pmaports 0001 |
| GPU (Adreno 650, Mesa freedreno), Phosh accelerated | works | kernel 0004, pmaports 0001 |
| Speakers + 3 microphones (VA macro, mic bias as in vendor DT) | works | kernel 0005, pmaports 0002, 0007 |
| A/B boot counter (qbootctl marks boot successful) | works | pmaports 0003 |
| Accelerometer, light, proximity via SLPI (SMEM item 130 filled by new driver) | works, needs the stock sensor files | kernel 0006–0008, pmaports 0004–0006, hexagonrpc 0001–0005 |
| Telephoto camera Samsung S5K3M5 via CAMSS + libcamera (4208×3120 @ 30, 2104×1184 @ 60, AGC, green tint) | works | kernel 0009–0010, pmaports 0008–0009, libcamera 0001 |
| Front camera Sony IMX471 (new driver, 4656×3496 @ 30, 2328×1748 @ 60) | works, see known issues | kernel 0011–0012, pmaports 0010–0011, libcamera 0002 |
| Full resolution capture on SM8250 CAMSS (camera NoC clock was never set) | fixed | kernel 0013, pmaports 0012 |
| Telephoto autofocus: LC898217XC voice coil driver at 0x74, powered through GPIO 140 | works | kernel 0014–0015, pmaports 0013 |
| Contrast detection autofocus in libcamera (software ISP statistics, lens support in the simple pipeline, soft IPA algorithm `Af`) | works, also in GNOME Snapshot | libcamera 0003–0005, pmaports 0014 |
| Modem (SDX55): boots to mission mode, QMI over QRTR, EFS sync; GPS engine runs but the modem stays offline | work in progress, not in the image | – |
| Main/ultrawide camera (C-PHY), OIS, colour tuning of the front camera, magnetometer, calls | not done | – |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame, while binned modes with shorter lines still worked. Other SM8250 devices using CAMSS
should be affected too.

The telephoto module has two chips next to the sensor: an LC898128 at 0x24, which only
drives the optical image stabilisation, and the LC898217XC at 0x74 that moves the lens.
The autofocus sweeps the lens in coarse and then fine steps and picks the sharpest
position; in continuous mode it scans again when the sharpness changes.

### Known issues

- The front camera (IMX471) occasionally fails to probe at boot with a CCI timeout. All
  cameras are then missing, because CAMSS waits for it. Workaround as root:
  `echo 21-0010 > /sys/bus/i2c/drivers/imx471/bind`
- The first focus command right after the actuator is powered on times out on the CCI bus.
  Later commands work, so this has no visible effect.
- After installing a new libcamera, restart PipeWire (`systemctl --user restart pipewire
  wireplumber`) or log out and in again: WirePlumber keeps the old library loaded.
- `apk upgrade` may replace the patched packages once postmarketOS publishes a higher
  version of the same package. Check `apk policy linux-postmarketos-qcom-sm8250` if
  something stops working after an upgrade.

### Enable the sensors

The sensor DSP needs OnePlus' sensor libraries and configuration (`hexagonfs`), which are
not redistributable. Build `firmware-oneplus-instantnoodlep-hexagonfs` yourself (section 4)
from your own phone's stock firmware and install it with
`apk add --allow-untrusted firmware-oneplus-instantnoodlep-hexagonfs-*.apk`, then reboot.

---

## 4. Build it yourself

You need a Linux PC (WSL2 works) with
[pmbootstrap](https://docs.postmarketos.org/pmbootstrap/) installed.

```sh
pmbootstrap init                      # vendor: oneplus, device: instantnoodlep, kernel: mainline
cd "$(pmbootstrap config aports)"
git checkout -b instantnoodlep
git am /path/to/this/repo/pmaports-patches/*.patch
```

The pmaports patches already contain the kernel and libcamera patches inside the packages,
so no separate kernel tree is needed. For the sensors, put
`oneplus-instantnoodlep-hexagonfs-1.tar.gz` next to the `firmware-oneplus-instantnoodlep`
APKBUILD (a `hexagonfs/` tree with `dsp/sdsp/` from the `dsp` partition and `sensors/` from
the vendor/persist partitions of your stock firmware) and run
`pmbootstrap checksum firmware-oneplus-instantnoodlep`. Without it, drop
`firmware-oneplus-instantnoodlep-hexagonfs` from the `subpackages` of that APKBUILD.

Then build and flash:

```sh
pmbootstrap build linux-postmarketos-qcom-sm8250 device-oneplus-instantnoodlep \
    firmware-oneplus-instantnoodlep alsa-ucm-conf-oneplus-instantnoodlep hexagonrpcd
pmbootstrap build --arch aarch64 libcamera
pmbootstrap install                   # choose your UI, user and password in "init"
pmbootstrap flasher flash_dtbo
pmbootstrap flasher flash_rootfs
pmbootstrap flasher flash_kernel
```

To change the kernel: clone https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux,
check out tag `sm8250-7.2.0_git20261010`, apply `kernel-patches/*.patch` with `git am`,
make your changes and export them again with `git format-patch` into the kernel package
directory (`device/testing/linux-postmarketos-qcom-sm8250/`), add them to `source=` in the
APKBUILD and run `pmbootstrap checksum linux-postmarketos-qcom-sm8250`.

### Contents of this repository

- `kernel-patches/` – against the postmarketOS SM8250 kernel tag `sm8250-7.2.0_git20261010`
  (https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux). Apply with `git am`.
- `pmaports-patches/` – against postmarketOS pmaports `main` (Oct 2026). They also carry
  the kernel and libcamera patches inside the packages.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `libcamera-patches/` – against libcamera v0.7.2 plus the patches already carried in
  postmarketOS `temp/libcamera`: sensor helpers for S5K3M5 and IMX471 (0001–0002) and the
  autofocus series (0003–0005).

Kernel patch 0014 (LC898217XC driver) is not my work: it is v4 of the driver Vasiliy
Doylov posted to the linux-media mailing list in March 2026
(https://lkml.iu.edu/hypermail/linux/kernel/2603.3/02275.html). It was taken from that
archive, which obscures the author's email address; use the original from lore.kernel.org
if you need it.

## License

Each patch keeps the license of the project it applies to (Linux kernel: GPL-2.0, device
tree / bindings as stated in their SPDX headers, hexagonrpc and libcamera as per their
repositories). The image contains postmarketOS/Alpine packages under their own licenses
and the firmware postmarketOS distributes; the kernel source is the tag above plus
`kernel-patches/`. README: CC0.

No warranty. Flashing your phone is at your own risk.
