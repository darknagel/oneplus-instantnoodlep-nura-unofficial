# OnePlus 8 Pro (instantnoodlep) – mainline Linux patches

Patches that bring up the OnePlus 8 Pro (IN2023, `oneplus-instantnoodlep`, SM8250) on a
mainline kernel with postmarketOS. Tested on my own device, October 2026.

> **AI disclosure:** These patches were written with substantial help from an AI coding
> assistant (Claude). I tested everything marked "works" on the device myself.
> Because of this, they are **not** submitted to postmarketOS, whose policy forbids
> AI-assisted contributions. Use them, learn from them, or reimplement them – but if you
> forward any of this to a project, check that project's rules on AI-generated code first.

## Status

| Feature | State | Patches |
|---|---|---|
| Display (Samsung AMS678UW01, new panel driver, 1440×3168 @ 120 Hz) | works | kernel 0001–0003, pmaports 0001 |
| GPU (Adreno 650, Mesa freedreno), Phosh accelerated | works | kernel 0004, pmaports 0001 |
| Speakers + 3 microphones (VA macro, mic bias as in vendor DT) | works | kernel 0005, pmaports 0002, 0007 |
| A/B boot counter (qbootctl marks boot successful) | works | pmaports 0003 |
| Accelerometer, light, proximity via SLPI (SMEM item 130 filled by new driver) | works | kernel 0006–0008, pmaports 0004–0006, hexagonrpc 0001–0005 |
| Telephoto camera Samsung S5K3M5 via CAMSS + libcamera (4208×3120 @ 30, 2104×1184 @ 60, AGC, green tint) | works | kernel 0009–0010, pmaports 0008–0009, libcamera 0001 |
| Front camera Sony IMX471 (new driver, 4656×3496 @ 30, 2328×1748 @ 60; colours and rotation checked) | works, see known issues | kernel 0011–0012, pmaports 0010–0011, libcamera 0002 |
| Full resolution capture on SM8250 CAMSS (camera NoC clock was never set, stayed at 19.2 MHz) | fixed | kernel 0013, pmaports 0012 |
| Telephoto autofocus: LC898217XC voice coil driver at 0x74, powered through GPIO 140 | works | kernel 0014–0015, pmaports 0013 |
| Contrast detection autofocus in libcamera (sharpness statistics in the software ISP, lens support in the simple pipeline, new soft IPA algorithm `Af`) | works, also in GNOME Snapshot | libcamera 0003–0005, pmaports 0014 |
| Main/ultrawide camera (C-PHY), OIS, colour tuning of the front camera, magnetometer, modem, calls | not done | – |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame (the VFE bus reports a CCIF violation for the write master), while binned modes with
shorter lines still worked. Other SM8250 devices using CAMSS should be affected too.

The telephoto module has two chips next to the sensor: an LC898128 at 0x24, which only
drives the optical image stabilisation, and the LC898217XC at 0x74 that moves the lens.
The autofocus sweeps the lens in coarse and then fine steps and picks the sharpest
position; in continuous mode it scans again when the sharpness changes. A scan takes about
2 s at 60 fps.

### Known issues

- The front camera (IMX471) occasionally fails to probe at boot with a CCI timeout. All
  cameras are then missing, because CAMSS waits for it. Workaround as root:
  `echo 21-0010 > /sys/bus/i2c/drivers/imx471/bind`
- The first focus command right after the actuator is powered on times out on the CCI bus
  (`master 0 queue 0 timeout`), even with a 200 ms start-up delay. Later commands work, and
  the autofocus sets the lens position itself, so this has no visible effect.
- After installing a new libcamera, restart PipeWire (`systemctl --user restart pipewire
  wireplumber`) or log out and in again: WirePlumber keeps the old library loaded.

## Contents

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

## Proprietary sensor files (not included)

pmaports patch 0006 expects `oneplus-instantnoodlep-hexagonfs-1.tar.gz` next to the
`firmware-oneplus-instantnoodlep` APKBUILD. It contains a `hexagonfs/` tree with the sensor DSP
libraries (`dsp/sdsp/`) and sensor config/registry files (`sensors/`) from the stock firmware. These are
proprietary and are not distributed here – extract them from your own device's stock firmware.

## Build (short)

```sh
cd "$(pmbootstrap config aports)"
git am /path/to/pmaports-patches/*.patch
# place the hexagonfs tarball, then:
pmbootstrap checksum firmware-oneplus-instantnoodlep
pmbootstrap build linux-postmarketos-qcom-sm8250 firmware-oneplus-instantnoodlep \
    device-oneplus-instantnoodlep hexagonrpcd
pmbootstrap build --arch aarch64 libcamera
```

To try the cameras, install GNOME Snapshot (`apk add snapshot`).

## License

Each patch keeps the license of the project it applies to (Linux kernel: GPL-2.0, device
tree / bindings as stated in their SPDX headers, hexagonrpc and libcamera as per their
repositories). README: CC0.

No warranty. Flashing your phone is at your own risk.
