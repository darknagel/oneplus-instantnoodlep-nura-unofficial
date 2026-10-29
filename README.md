# OnePlus 8 Pro (instantnoodlep) – unofficial Nura mainline port

Patches and a ready-to-flash image that turn the OnePlus 8 Pro (IN2023,
`oneplus-instantnoodlep`, Snapdragon 865 / SM8250) into a Linux phone running
[Nura](https://nura.eco) (formerly postmarketOS) on a mainline kernel.
This is an unofficial, independent project – it is not affiliated with or supported by
the Nura project. Package and tool names (`pmbootstrap`, `postmarketos-ui-phosh`,
`linux-postmarketos-qcom-sm8250`, …) still carry the old name (as of October 2026), so the commands below use them.

> **AI disclosure:** These patches and the image were made with substantial help from an AI
> coding assistant (Claude). Everything marked "works" was tested on a real device.
> Because of this, nothing here is submitted to Nura, whose policy forbids
> AI-assisted contributions. Use it, learn from it, or reimplement it – but if you forward
> any of this to a project, check that project's rules on AI-generated code first.

For general information about the device under Nura (partition layout, USB quirks,
how to return to Android) see the wiki page:
**https://wiki.nura.eco/wiki/OnePlus_8_Pro_(oneplus-instantnoodlep)**

---

## 1. Easy flash: the prebuilt image

The [Releases](../../releases) page has a minimal image. It makes the phone a small Linux
computer you reach over SSH; optionally you install a desktop like Phosh or Plasma Mobile on top (see section 2).

**What's in it**

- Nura edge, console only (no desktop), NetworkManager, OpenSSH server
- kernel `linux-postmarketos-qcom-sm8250` 7.2 with all patches from this repository
  (display 1440×3168 @ 120 Hz, GPU, audio, Wi-Fi, USB networking, cameras,
  telephoto autofocus) – the modem work is **not** included
- firmware: only what Nura distributes anyway (`firmware-oneplus-instantnoodlep`,
  `linux-firmware-ath11k`, `linux-firmware-qcom`)
- **login: user `root`, password `root`, SSH enabled.** Change the password right after the
  first login (`passwd`) – until you do, anyone on your network can log in as root.
- no Wi-Fi networks, no SSH keys, no personal data; SSH host keys are generated on first boot

**Not in it**

- the sensor files (accelerometer, light, proximity): they come from OnePlus' stock firmware
  and may not be redistributed – see "Enable the sensors" below
- modem and GPS: they need a kernel built from pmaports patch 0018 and a setup
  script that copies the phone's own modem firmware, see [`modem/`](modem/)
- the packages Bluetooth needs (one `apk add` away, see known issues)
- main and ultrawide camera (C-PHY), optical image stabilisation

**Tested hardware**

Tested on a single device with the **Samsung AMS678UW01** display panel (the panel driver is
written for exactly this panel; Android reports it as `oppo19811_samsung_1440_3168_dsc_cmd`).
If your phone has a different panel, the screen may stay black – the phone is then still
reachable over USB/SSH. Please open an issue with your panel name and a log if that happens.
To create the log, connect the phone over USB (see "First login") and run these two commands
on your PC (they work the same in PowerShell and in a Linux terminal):

```sh
ssh root@172.16.42.1 "{ echo '== panel'; tr ' ' '\n' < /proc/cmdline | grep dsi_display; echo '== kernel log'; dmesg; echo '== warnings this boot'; journalctl -b -p warning --no-pager; } | sed 's/serialno=[^ ]*/serialno=REMOVED/g' > /root/panel-log.txt"
scp root@172.16.42.1:/root/panel-log.txt .
```

`172.16.42.1` is the phone's address over USB. If the phone is on your Wi-Fi, you can use its
Wi-Fi address instead (shown by `ip -4 addr show wlan0` on the phone, or in your router).
Then attach `panel-log.txt` to the issue.

The `sed` removes the device serial number that the bootloader passes on the kernel command
line. Look through the file before you upload it.

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

On Windows, `ssh` works the same in PowerShell. If Windows does not set up the USB network by
itself (the phone shows up under "Other devices" or with a yellow warning sign in Device
Manager), assign the driver by hand: right-click the device → **Update driver** → **Browse my
computer for drivers** → **Let me pick from a list of available drivers on my computer** →
**Network adapters** → manufacturer **Microsoft** → **UsbNcm Host Device** (on older Windows
10 versions without it: **Remote NDIS Compatible Device**). If the USB network still does not
come up, log in on the phone's screen with a USB keyboard (USB-C hub with external power).

---

## 2. Optional: install a desktop (Phosh or another interface)

This step is optional – the image works as it is over SSH. If you want a touch interface on
the screen, pick one of the phone interfaces Nura offers:

| Interface | Package | Notes |
|---|---|---|
| Phosh | `postmarketos-ui-phosh` | GNOME-based; tested (GPU accelerated, camera works in Snapshot) |
| Plasma Mobile | `postmarketos-ui-plasma-mobile` | KDE-based; tested (GPU accelerated, camera works in Snapshot) |
| Sxmo | `postmarketos-ui-sxmo-de-sway` | minimal, button and menu driven; not tried |

Desktop interfaces do not run as root, so create a normal user first. **The user must have
the user ID 10000** – Nura starts the interface for exactly this ID, with any other ID it
fails to start. Pick a **numeric password (PIN)**: the lock screens show a number pad first.
Example with Phosh – replace the package name for another interface:

```sh
apk update
adduser -u 10000 -g "" alice                         # pick your own name; password = PIN
for g in audio input plugdev video netdev feedbackd wheel; do
    addgroup alice $g 2>/dev/null
done
apk add xdg-user-dirs && su alice -c xdg-user-dirs-update   # ~/Pictures etc., or camera apps cannot save
apk add postmarketos-ui-phosh stevia-schemas        # stevia-schemas fixes Phosh's on-screen keyboard
apk add doas && echo 'permit persist :wheel' > /etc/doas.d/wheel.conf   # "doas" instead of sudo
reboot
```

After the reboot the interface starts and asks for the PIN of the user you created. Useful
additions for Phosh:

```sh
apk add snapshot          # camera app (telephoto and front camera, with autofocus)
apk add gnome-software    # app store
```

Install only one interface at a time; to switch, `apk del` the old `postmarketos-ui-…`
package before adding the new one.

Once you have your own user, you can switch off the root login over SSH:
`rm /etc/ssh/sshd_config.d/10-oneplus-instantnoodlep-release.conf` and log in as your user.

---

## 3. FAQ: using the phone as a small server

All commands run as root on the phone.

**How do I turn the screen off?**

```sh
echo 1 > /sys/class/graphics/fb0/blank     # off
echo 0 > /sys/class/graphics/fb0/blank     # on again
```

This does not survive a reboot: the screen comes back on at every start, so run the command
again after each reboot (for example over SSH).

**Can charging stop at 80 % when the phone is always plugged in?**

There is no ready-made charge limit for this charger yet (no `charge_control_end_threshold`).
The PMIC charger can be switched off, though, so a small service can stop charging at 80 %
and resume at 75 %:

```sh
cat > /usr/local/bin/charge-limit <<'EOF'
#!/bin/sh
# Stop charging at STOP %, resume at START %.
STOP=80; START=75
CAP=/sys/class/power_supply/bq27411-0/capacity
EN=/sys/class/power_supply/pm8150b-charger/charging_enabled
while true; do
    c=$(cat $CAP)
    if [ "$c" -ge "$STOP" ]; then echo 0 > $EN
    elif [ "$c" -le "$START" ]; then echo 1 > $EN
    fi
    sleep 60
done
EOF
chmod +x /usr/local/bin/charge-limit

cat > /etc/systemd/system/charge-limit.service <<'EOF'
[Unit]
Description=Keep the battery between 75 and 80 percent

[Service]
ExecStart=/usr/local/bin/charge-limit
ExecStopPost=/bin/sh -c 'echo 1 > /sys/class/power_supply/pm8150b-charger/charging_enabled'
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now charge-limit
```

This is **experimental**: with charging switched off the charger reports "Not charging", but
the fuel gauge still measured about 50 mA flowing into the battery, so the level may creep
above 80 % slowly. Check it after a day with
`cat /sys/class/power_supply/bq27411-0/capacity`. To undo:
`systemctl disable --now charge-limit`.

**Will the phone go to sleep?**

Not with the console image. If you installed a desktop, switch suspend off:
`systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`

**SSH over Wi-Fi drops out or is slow to respond.**

Switch off Wi-Fi power saving for your network (name as shown by `nmcli connection`):

```sh
nmcli connection modify "YOUR-WIFI" 802-11-wireless.powersave 2
nmcli connection up "YOUR-WIFI"
```

**How do I find the phone's address in my network?**

`ip -4 addr show wlan0` on the phone, or look it up in your router. For a fixed address, set
it in the router (DHCP reservation) – that is easier than a static IP on the phone.

**How do I check battery and temperature?**

```sh
cat /sys/class/power_supply/bq27411-0/capacity   # battery in %
cat /sys/class/power_supply/bq27411-0/status     # Charging / Discharging
cat /sys/class/power_supply/bq27411-0/temp       # battery temperature in 0.1 °C
cat /sys/class/thermal/thermal_zone*/temp        # SoC sensors in m°C
```

**Name resolution (DNS) does not work.**

The image switches DNSSEC off (`/etc/systemd/resolved.conf.d/10-dnssec-off.conf`), because
many home routers break DNSSEC validation. If `apk update` still reports DNS errors right
after connecting to Wi-Fi, wait a minute or run `resolvectl flush-caches`.

---

## 4. Status

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
| Modem (SDX55 over PCIe/MHI): Sahara firmware loading, EFS sync, TFTP file server, online with LTE/5G bands | works, not in the image, see [`modem/`](modem/) | kernel 0016–0030, pmaports 0018 |
| GPS (modem GNSS engine, NMEA on `/dev/gnss-sdx55`, fix without SIM) | works, see [`modem/`](modem/) | same |
| SMS, mobile data | untested (needs a SIM) | – |
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

- **Bluetooth needs three extra packages in the prebuilt image.** The chip has no Bluetooth
  address of its own; `bootmac` sets one at boot, without it BlueZ ignores the controller.
  Install them and reboot:
  `apk add firmware-oneplus-instantnoodlep-bluetooth bluez bootmac && systemctl enable bluetooth && reboot`
  Afterwards `bluetoothctl list` shows the controller. (Plasma Mobile and Phosh pull in BlueZ
  themselves, but not `bootmac`.)
- The front camera (IMX471) occasionally fails to probe at boot with a CCI timeout. All
  cameras are then missing, because CAMSS waits for it. Workaround as root:
  `echo 21-0010 > /sys/bus/i2c/drivers/imx471/bind`
- The first focus command right after the actuator is powered on times out on the CCI bus.
  Later commands work, so this has no visible effect.
- Under Plasma Mobile, Snapshot crashes with the front camera (GTK's GL renderer). Start it
  with the software renderer: `GSK_RENDERER=cairo snapshot`
- After installing a new libcamera, restart PipeWire (`systemctl --user restart pipewire
  wireplumber`) or log out and in again: WirePlumber keeps the old library loaded.
- `apk upgrade` may replace the patched packages once Nura publishes a higher
  version of the same package. Check `apk policy linux-postmarketos-qcom-sm8250` if
  something stops working after an upgrade.

### Enable the sensors

The sensor DSP needs OnePlus' sensor libraries and configuration (`hexagonfs`), which are
not redistributable. Build `firmware-oneplus-instantnoodlep-hexagonfs` yourself (section 5)
from your own phone's stock firmware and install it with
`apk add --allow-untrusted firmware-oneplus-instantnoodlep-hexagonfs-*.apk`, then reboot.

---

## 5. Build it yourself

You need a Linux PC (WSL2 works) with
[pmbootstrap](https://docs.postmarketos.org/pmbootstrap/) installed.

```sh
# 1. get this repository
git clone https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial.git ~/instantnoodlep-patches

# 2. set up pmbootstrap: vendor "oneplus", device "instantnoodlep", kernel "mainline"
pmbootstrap init

# 3. apply all patches to pmbootstrap's pmaports checkout
cd "$(pmbootstrap config aports)"
git checkout -b instantnoodlep
git am --whitespace=nowarn ~/instantnoodlep-patches/pmaports-patches/*.patch
```

If `git am` stops with "Please tell me who you are", set your name once with
`git config --global user.name "Your Name"` and `git config --global user.email you@example.com`
and run the `git am` line again.

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

- `kernel-patches/` – against the Nura SM8250 kernel tag `sm8250-7.2.0_git20261010`
  (https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux). Apply with `git am`.
- `pmaports-patches/` – against Nura pmaports `main` (Oct 2026). They also carry
  the kernel and libcamera patches inside the packages. 0018 adds the modem kernel
  patches (kernel 0016–0030, partly debug quality, see [`modem/`](modem/)).
- `modem/` – setup script and small services for the SDX55 modem and GPS.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `libcamera-patches/` – against libcamera v0.7.2 plus the patches already carried in
  Nura `temp/libcamera`: sensor helpers for S5K3M5 and IMX471 (0001–0002) and the
  autofocus series (0003–0005).

Kernel patch 0014 (LC898217XC driver) is not my work: it is v4 of the driver Vasiliy
Doylov posted to the linux-media mailing list in March 2026
(https://lkml.iu.edu/hypermail/linux/kernel/2603.3/02275.html). It was taken from that
archive, which obscures the author's email address; use the original from lore.kernel.org
if you need it.

## License

Each patch keeps the license of the project it applies to (Linux kernel: GPL-2.0, device
tree / bindings as stated in their SPDX headers, hexagonrpc and libcamera as per their
repositories). The image contains Nura/Alpine packages under their own licenses
and the firmware Nura distributes; the kernel source is the tag above plus
`kernel-patches/`. README: CC0.

No warranty. Flashing your phone is at your own risk.
