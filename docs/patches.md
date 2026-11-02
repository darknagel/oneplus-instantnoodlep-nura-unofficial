# Patches and technical details

## Status per feature

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
| Bluetooth (no patches needed, `bootmac` sets the address) | works | – |
| Modem (SDX55 over PCIe/MHI): Sahara firmware loading, EFS sync, TFTP file server, online with LTE/5G bands | works, see [`modem/`](../modem/) | kernel 0016–0031 without 0027, pmaports 0018, 0020 |
| GPS (modem GNSS engine, NMEA on `/dev/gnss-sdx55`, fix without SIM) | works, see [`modem/`](../modem/) | same |
| SIM with PIN, network registration (LTE/5G) | works, see [`modem/`](../modem/) | pmaports 0019 |
| Mobile data (IPv6 only, tested on congstar) | works, see [`modem/`](../modem/) | pmaports 0019, 0020 |
| SMS, send and receive (`mmcli`, Spacebar under Plasma Mobile) | works, see [`modem/`](../modem/) | – |
| NFC (NXP chip, reading tags with `neard`; PCIe 1 is disabled because it took the enable pin) | works | kernel 0032, pmaports 0021 |
| C-PHY on SM8250 CAMSS (posted series, see below) | works | kernel 0033–0041, pmaports 0022 |
| Main camera Sony IMX689 (new driver, 3 C-PHY trios, 4000×3000 @ 30) | works | kernel 0042, 0045, pmaports 0022, libcamera 0006 |
| Ultrawide camera Sony IMX586 (new driver, 3 C-PHY trios, 4000×3000 @ 30) | works | kernel 0043, 0045, pmaports 0022, libcamera 0006 |
| Colour filter camera GalaxyCore GC5035 (new driver, 2592×1944, also sees near infrared) | works | kernel 0044, 0045, pmaports 0022, libcamera 0006 |
| Autofocus on main and ultrawide camera (AK7377 actuators with the AK7375 driver) | works, see known issues | kernel 0045, pmaports 0023, libcamera 0007 |
| OIS, colour tuning of the front camera, magnetometer, calls | not done | – |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame, while binned modes with shorter lines still worked. Other SM8250 devices using CAMSS
should be affected too.

The telephoto module has two chips next to the sensor: an LC898128 at 0x24, which only
drives the optical image stabilisation, and the LC898217XC at 0x74 that moves the lens.
The autofocus sweeps the lens in coarse and then fine steps and picks the sharpest
position; in continuous mode it scans again when the sharpness changes.

## Other notes

- The first focus command right after the actuator is powered on times out on the CCI bus.
  Later commands work, so this has no visible effect.
- `bootmac` sets the Bluetooth address at boot, the chip has none of its own. Without it,
  BlueZ ignores the controller.
- Mobile data runs on the MHI channel `IP_HW0` without doorbell burst mode (kernel 0031).
  With burst mode the downlink stalled under load; `IP_SW0` carries no data. ModemManager
  needs the fixes in pmaports 0019 for this modem.

## Changing the kernel

To change the kernel: clone https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux,
check out tag `sm8250-7.2.0_git20261010`, apply `kernel-patches/*.patch` with `git am`,
make your changes and export them again with `git format-patch` into the kernel package
directory (`device/testing/linux-postmarketos-qcom-sm8250/`), add them to `source=` in the
APKBUILD and run `pmbootstrap checksum linux-postmarketos-qcom-sm8250`.

## Repository

- `kernel-patches/` – against the Nura SM8250 kernel tag `sm8250-7.2.0_git20261010`
  (https://gitlab.postmarketos.org/soc/qualcomm-sm8250/linux). Apply with `git am`.
- `pmaports-patches/` – against Nura pmaports `main` (Oct 2026). They also carry
  the kernel and libcamera patches inside the packages. 0018 adds the modem kernel
  patches (kernel 0016–0031 without 0027, partly debug quality, see
  [`modem/`](../modem/)), 0019 fixes ModemManager for this modem, 0020 keeps the
  modem's data channels, 0021 fixes NFC, 0022 adds the C-PHY series and the remaining
  cameras, 0023 adds them to libcamera.
- `modem/` – setup script and small services for the SDX55 modem and GPS.
- `sensors/` – script that sets up the sensors from your own phone.
- `docs/` – this file and details moved out of the README.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `libcamera-patches/` – against libcamera v0.7.2 plus the patches already carried in
  Nura `temp/libcamera`: sensor helpers for S5K3M5 and IMX471 (0001–0002) and the
  autofocus series (0003–0005), sensor helpers for IMX586, IMX689 and GC5035 (0006) and a
  shorter autofocus scan (0007).

Kernel patches 0033–0041 are not my work either: they are the series "media: camss: Add
support for C-PHY" v5 by David Heidelberg, with patches by Casey Connolly and Luca Weiss.
Use the original from lore.kernel.org if you need it.

Kernel patch 0014 (LC898217XC driver) is not my work: it is v4 of the driver Vasiliy
Doylov posted to the linux-media mailing list in March 2026
(https://lkml.iu.edu/hypermail/linux/kernel/2603.3/02275.html). It was taken from that
archive, which obscures the author's email address; use the original from lore.kernel.org
if you need it.
