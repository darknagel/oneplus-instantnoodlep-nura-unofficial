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
| Telephoto camera Samsung S5K3M5 via CAMSS + libcamera (4208×3120 @ 30, 2104×1184 @ 60, AGC, no AF, green tint) | works | kernel 0009–0010, pmaports 0008–0009, libcamera 0001 |
| Front camera Sony IMX471 (new driver, 4656×3496 @ 30, 2328×1748 @ 60; colours and rotation checked) | works – probed on 3 of 3 boots | kernel 0011–0012, pmaports 0010–0011, libcamera 0002 |
| Full resolution capture on SM8250 CAMSS (camera NoC clock was never set, stayed at 19.2 MHz) | fixed | kernel 0013, pmaports 0012 |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame (the VFE bus reports a CCIF violation for the write master), while binned modes with
shorter lines still worked. Other SM8250 devices using CAMSS should be affected too.
| Main/ultrawide camera (C-PHY), autofocus, magnetometer, modem, calls | not done | – |

## Contents

- `kernel-patches/` – against the postmarketOS SM8250 kernel tag `sm8250-7.2.0_git20261010`
  (https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux). Apply with `git am`.
- `pmaports-patches/` – against postmarketOS pmaports `main` (Oct 2026). They also carry
  the kernel patches inside the kernel package.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `libcamera-patches/` – against libcamera v0.7.2 (sensor helpers for S5K3M5, IMX471).

## Proprietary sensor files (not included)

pmaports patch 0006 expects `oneplus-instantnoodlep-hexagonfs-1.tar.gz` next to the
`firmware-oneplus-instantnoodlep` APKBUILD. It contains a `hexagonfs/` tree with the sensor DSP
libraries (`dsp/sdsp/`) and sensor config/registry files (`sensors/`) from the stock firmware. These are
proprietary and are not distributed here – extract them from your own device's stock firmware.

## Build (short)

```sh
cd "$(pmbootstrap config aports)"
git am /path/to/pmaports-patches/000*.patch
# place the hexagonfs tarball, then:
pmbootstrap checksum firmware-oneplus-instantnoodlep
pmbootstrap build linux-postmarketos-qcom-sm8250 firmware-oneplus-instantnoodlep \
    device-oneplus-instantnoodlep hexagonrpcd libcamera
```

## License

Each patch keeps the license of the project it applies to (Linux kernel: GPL-2.0, device
tree / bindings as stated in their SPDX headers, hexagonrpc and libcamera as per their
repositories). README: CC0.

No warranty. Flashing your phone is at your own risk.
