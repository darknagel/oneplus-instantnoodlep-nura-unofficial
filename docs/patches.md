# Patches and technical details

## Status per feature

| Feature | State | Patches |
|---|---|---|
| Display (Samsung AMS678UW01, new panel driver, 1440×3168 @ 120 Hz) | works | kernel 0001–0003, pmaports 0001 |
| GPU (Adreno 650, Mesa freedreno), Phosh accelerated | works | kernel 0004, pmaports 0001 |
| USB-C DisplayPort: video with USB2 alongside, VBUS supply and power-role swap, audio | works | kernel 0088–0103, pmaports 0045–0047, 0049; [notes](displayport.md) |
| DisplayPort HBR3 and HDR signalling (`Colorspace`, `HDR_OUTPUT_METADATA`) | draft | kernel 0117–0122, pmaports 0058; [notes](displayport.md#hdr) |
| Charger input limit from USB-C/PD or USB-A detection, 2 A battery current | works | kernel 0082–0087, pmaports 0044; [notes](charging.md) |
| Speakers + 3 microphones (VA macro, mic bias as in vendor DT) | works | kernel 0005, pmaports 0002, 0007 |
| False headset detection with an ordinary USB cable, codec runtime-PM errors and unsorted RX register defaults | fixed; analog USB-C headsets untested | kernel 0055–0060, pmaports 0030; [notes](audio.md) |
| A/B boot counter (qbootctl marks boot successful) | works | pmaports 0003 |
| Accelerometer, light, proximity via SLPI (SMEM item 130 filled by new driver) | works, needs the stock sensor files | kernel 0006–0008, 0049, pmaports 0004–0006, 0026, hexagonrpc 0001–0005 |
| Telephoto camera Samsung S5K3M5 via CAMSS + libcamera (4208×3120 @ 30, 2104×1184 @ 60, AGC, green tint) | works | kernel 0009–0010, pmaports 0008–0009, libcamera 0001 |
| Front camera Sony IMX471 (new driver, 4656×3496 @ 30, 2328×1748 @ 30) | works, see known issues | kernel 0011–0012, 0114, pmaports 0010–0011, 0054, libcamera 0002 |
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
| Magnetometer MMC5603: the SLPI firmware reads SMEM item 130 with 2 chips per sensor type, the driver wrote 3 | works | kernel 0046–0047, pmaports 0024 |
| SMEM item 130 layout per SLPI build: same version string, but older builds read 2 chips per sensor type (stride 0x174, algorithms at 0x1000), newer ones 3 (0x22c, 0x17e8). The phone now runs its own SLPI, so the driver keeps the layout of an item the bootloader created and otherwise creates the 3-chip one | works | kernel 0061–0062, pmaports 0031 |
| Focus actuators: the first CCI transfer after power up can time out, which left the ultrawide lens disabled until the next boot, and the first position write after standby release was sometimes NACKed | works | kernel 0048, pmaports 0025 |
| Front camera missing at some boots: the telephoto actuator used the camera I2C bus without the 1.8 V pull-up supply (L7F), the CCI timed out and reset both masters during the front camera probe | works | kernel 0050–0051, pmaports 0027 |
| Compass heading: rotv needs fmv, which needs mag_cal and gyro_cal, which need the software motion detector that OnePlus switches off on SM8250 (`kona_amd_sw_disabled.json`) | works | `sensors/setup-sensors.sh` |
| SLPI, Venus and CDSP: firmware from the phone's active modem partition, joined with pil-squasher and stored as local overrides | works; CDSP compute workloads untested | `firmware/dsp-firmware.sh` |
| Automatic screen rotation: iio-sensor-proxy 3.9 opens the SSC sensors synchronously at startup; a claim in that window (KWin, Phosh) is stored but the sensor is never started | works | iio-sensor-proxy 0001 |
| Reboot modes: `reboot bootloader` / `reboot recovery`; the unused PM8009 PON registered a second `qcom-pon` reboot mode (-EEXIST warning at boot) | works | kernel 0052, pmaports 0028 |
| OIS of the main camera: onsemi LC898128 at 0x24, runs from its own firmware and reads the module gyroscope itself; new driver starts it whenever the sensor is powered, PM8009 L5 added for its supply | works | kernel 0053–0054, pmaports 0029 |
| QRTR forwarded client deletions: accept notifications from a remote router for clients reached through the same transport endpoint | works | kernel 0064, pmaports 0032 |
| Compass: the MMC5603 sensor-direction of OnePlus's own device tree for this phone (19811) is 0, not 4; found by naorunaoru | works | kernel 0065, pmaports 0033 |
| Lens noise: the AK7375 driver steps the lens to and from its rest position, which buzzes on this phone; a module parameter turns that off, as the vendor kernel does | works | kernel 0066, pmaports 0033, `system/ak7375.conf` |
| OIS: the LC898128 firmware is busy for about 2 s after the servo command and drops the OIS enable meanwhile; it also reads the gyroscope only while the sensor DSP runs it | works | kernel 0067, pmaports 0033, `system/ois-gyro` |
| libcamera 0.8.0: autofocus series ported to the renamed softisp IPA, IMX471 helper now upstream; autofocus rescans only after a 25 % change in four frames, so low light noise no longer makes the lens hunt | works | libcamera 0001–0006, pmaports 0034 |
| Camera names (Main, Ultrawide, Telephoto, Colour Filter, Front) for PipeWire apps | works | `system/60-oneplus-instantnoodlep-cameras.conf` |
| Proximity calibration from the Android `persist` partition, at first boot | works | `firmware/dsp-firmware.sh`, `sensors/setup-sensors.sh` |
| Charging: the PM8150B float voltage register counts from 3.6 V in 10 mV steps, as in the vendor driver; the old encoding selected 4.76 V for the 4.35 V battery. Found by naorunaoru | works | kernel 0068, pmaports 0036 |
| Haptics: AW8697 on I2C11 with the stock LRA0619 tuning (170 Hz, drive level 54) | works | kernel 0074, pmaports 0038 |
| Flash LEDs: both PM8150L channels, first with conservative limits, raised to the stock ones by 0079 | works | kernel 0075, pmaports 0038 |
| Wireless charge pump: the stock part is a BQ2597x, not a BQ25980; the node is corrected and stays disabled until wireless charging is integrated | disabled | kernel 0076, pmaports 0038 |
| Boot warnings: touchscreen axis check, panel brightness access before the panel is ready, PCIe IOMMU map cells, fbdev mapping flag | fixed | kernel 0069–0072, pmaports 0037 |
| USB input voltage and current stay readable while battery charging is paused or finished | fixed | kernel 0073, pmaports 0037 |
| DSI PHY: digital top kept powered for PLL and PHY users, bias references released after a failed PLL lock | works | kernel 0077–0078, pmaports 0040 |
| GPU cooling, Bluetooth PAN and the Qualcomm crypto engine enabled in the kernel config | enabled | pmaports 0039 |
| ModemManager without the MediaTek and Rolling plugins, whose shared module fails to load on musl | works, modem comes up with the `qcom-soc` plugin | pmaports 0041 |
| Flash limits as in the vendor device tree: 1500 mA flash for up to 1280 ms and 500 mA torch per channel | works | kernel 0079, pmaports 0042 |
| Resume from suspend: the freezer interrupted the waiting FastRPC call of `hexagonrpcd`, the restarted system call sent it a second time and the sensor DSP crashed (taking iio-sensor-proxy and the rotation with it); the touchscreen driver enabled its interrupt before powering the controller up, so resume failed with -19 and sensing stayed off | works | kernel 0080–0081, pmaports 0043 |
| iio-sensor-proxy segfaults when the sensor DSP stops (subsystem restart, shutdown) and its unit has `Restart=no`, so rotation stayed dead until reboot | restarted after 3 s | pmaports 0056 |
| Camera buffers: the default 32 MiB CMA pool was too small for full-resolution outputs | 256 MiB, 4000×3000 at 30 fps | pmaports 0056 |
| Torch: the stock camera drives both PM8150L flash channels together as one flash; describing it as one LED with both sources also gives it the name `white:flash`, which the Plasma Mobile and Phosh torch switches look for | works | kernel 0104, pmaports 0048 |
| Sound in PipeWire: DisplayPort audio as its own UCM use case, since without a monitor it made PipeWire drop the speakers and microphones; the speaker amplifiers get 16-bit samples, at 24 bit they play far too quietly | works | pmaports 0049, `system/61-oneplus-instantnoodlep-speaker-s16.conf` |
| Camera tuning from the stock OnePlus tuning: colour matrices (main, ultrawide, telephoto) and lens shading tables (all four), new AGC limits so bright areas no longer clip; noise robust autofocus sharpness, and the GPU debayer statistics now cover the whole frame instead of its top left corner (autofocus, exposure and white balance measured only that corner) | works | libcamera 0007–0008, pmaports 0055 |
| OIS of the telephoto camera (second LC898128), colour tuning of the front camera, calls | not done | – |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame, while binned modes with shorter lines still worked. Other SM8250 devices using CAMSS
should be affected too.

Kernel patch 0049 accepts the 4684-byte sensor-information layout found on an IN2023
OnePlus 8 Pro: two hardware sources per sensor and seven algorithm records. It bounds
virtual-sensor writes to those seven records and preserves the existing layout rules.
Without it, the sensor device-info driver fails to bind with `-EINVAL`.

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
  cameras, 0023 adds them to libcamera, 0024 fixes the magnetometer, 0025 makes the
  focus actuators reliable, 0026 adds the 4684-byte sensor layout, 0027 powers the
  telephoto actuator bus, 0028 adds the reboot modes, 0029 adds the main camera
  OIS, 0030 fixes USB-C audio detection, 0031 takes the sensor layout from SMEM and
  starts the OIS only once the camera stays on, and 0032 accepts forwarded QRTR
  client deletions from nodes on the same transport endpoint. 0033 adds kernel patches
  0065–0067, 0034 updates `temp/libcamera` to 0.8.0 with the autofocus series, and 0035
  adds `temp/iio-sensor-proxy` 3.9 with the rotation fix and SSC support. 0036 adds kernel patch 0068 (charger float voltage).
  0037 adds kernel patches 0069–0073 (boot warnings and USB telemetry), 0038 adds
  0074–0076 (haptics, flash LEDs and the charge pump), 0039 enables GPU cooling,
  Bluetooth PAN and QCE, 0040 adds the DSI PHY fixes 0077–0078, and 0041 builds
  ModemManager without the MediaTek and Rolling plugins. 0042 adds kernel patch 0079 (stock flash
  limits) and 0043 adds 0080–0081 (resume from suspend). 0044 makes the PM8150B
  charger follow USB-C limits, with USB-A detection and this board's 2 A battery
  charge-current ceiling; 0045 adds DisplayPort alt mode with USB2 alongside and
  the PHY fixes; 0046 adds the external VBUS supply and power-role swaps;
  0047 adds DP audio and PCM restart recovery. 0048 drives both flash channels as one
  torch (kernel 0104), 0049 adds the DisplayPort UCM use case and 0052 puts the charger
  ADC into the initramfs. 0054 runs the front camera binned mode at 30 fps (kernel 0114)
  and 0055 adds the camera tuning and libcamera 0007–0008. 0056 reserves 256 MiB CMA
  (full-resolution camera output) and restarts iio-sensor-proxy when it crashes. 0057
  adds kernel 0115 (panel powered off again when the DSC parameters cannot be sent) and
  0116 (bounds check in the sensor devinfo SAR parser). The DisplayPort stack
  follows these patches; see the table above. Package numbers 0050, 0051 and 0053
  and kernel numbers 0105–0113 are unused.
- `modem/` – setup script and small services for the SDX55 modem and GPS.
- `sensors/` – script that sets up the sensors from your own phone.
- `firmware/` – boot service that copies SLPI, Venus and CDSP firmware from your own phone.
- `docs/` – this file and details moved out of the README.
- `iio-sensor-proxy-patches/` – against https://gitlab.freedesktop.org/hadess/iio-sensor-proxy tag `3.9`.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `libcamera-patches/` – against libcamera v0.8.0 plus the patches already carried in
  Nura `temp/libcamera`: sensor helpers for S5K3M5 (0001) and IMX586, IMX689 and GC5035
  (0002), the autofocus series (0003–0005), a shorter autofocus scan (0006), a noise
  robust sharpness measure (0007) and whole-frame statistics for the GPU debayer (0008). The IMX471
  helper is upstream since v0.8.0. The autofocus and image tuning is in the sensor files of
  pmaports patches 0034 and 0055.
- `system/` – small files the image adds: the `ois-gyro` service, which keeps the
  gyroscope running while the main camera's OIS is active, the AK7375 option without the
  lens ramp, camera names for PipeWire and 16-bit samples for the speakers.

Kernel patches 0033–0041 are not my work either: they are the series "media: camss: Add
support for C-PHY" v5 by David Heidelberg, with patches by Casey Connolly and Luca Weiss.
Use the original from lore.kernel.org if you need it.

Kernel patch 0101 is not my work: it is v2 of "drm/display: add hw_params callback
function to drm_connector_hdmi_audio_ops" by Jianfeng Liu, carried unchanged
(https://lore.kernel.org/r/20250925040530.20731-1-liujianfeng1994@gmail.com).

Kernel patch 0014 (LC898217XC driver) is not my work: it is v4 of the driver Vasiliy
Doylov posted to the linux-media mailing list in March 2026
(https://lkml.iu.edu/hypermail/linux/kernel/2603.3/02275.html). It was taken from that
archive, which obscures the author's email address; use the original from lore.kernel.org
if you need it.
