# Patches and technical details

## Status per feature

| Feature | State | Patches |
|---|---|---|
| Display (Samsung AMS678UW01, new panel driver, 1440×3168 @ 120 Hz) | works | kernel 0001–0003, pmaports 0001 |
| GPU (Adreno 650, Mesa freedreno), Phosh accelerated | works | kernel 0004, pmaports 0001 |
| USB-C DisplayPort: video with USB2 alongside, VBUS supply and power-role swap, audio | works | kernel 0088–0103, pmaports 0045–0047, 0049; [notes](displayport.md) |
| DisplayPort HBR3 and HDR signalling (`Colorspace`, `HDR_OUTPUT_METADATA`) | draft; HDR shown by the ASUS PG32UCDMR, picture looked right | kernel 0138–0143, 0159–0160, pmaports 0059, 0078; [notes](displayport.md#hdr) |
| DisplayPort over system sleep: the DP PHY loses its setup while the controller is suspended but was still taken as initialised, so the display was dropped after resume; a link that failed to train was pushed to idle without a link clock, which reset the phone; detect() and the HPD plug handler leaked runtime PM references when HPD comes from the USB-C connector | draft | kernel 0144–0145, 0157–0158, pmaports 0060, 0077; [notes](displayport.md#system-sleep) |
| Switching between the phone panel and an external DisplayPort monitor: disabling the command-mode panel left its interface, mixers and both DSC blocks active, and DisplayPort underran with a blue screen; after a boot with the monitor attached, the phone panel stayed grey on the first switch back | Tested at 2880×1800, 120 Hz on the GR14BU | kernel 0146–0147, 0161–0163, pmaports 0061, 0079; [notes](displayport.md#switching-back-to-the-phone-panel) |
| DisplayPort audio with nothing plugged in: preparing the PCM started the DSP's DisplayPort port, and the DSP took q6afe's whole command timeout to answer; every probe at boot waited for it | draft; tested on the phone with PulseAudio | kernel 0148–0150, pmaports 0076; [notes](displayport.md#audio-with-no-display) |
| Charger input limit from USB-C/PD or USB-A detection, 2 A battery current | works | kernel 0082–0087, pmaports 0044; [notes](charging.md) |
| Speakers + 3 microphones (VA macro, mic bias as in vendor DT) | works | kernel 0005, pmaports 0002, 0007 |
| False headset detection with an ordinary USB cable, codec runtime-PM errors and unsorted RX register defaults | fixed; analog USB-C headsets untested | kernel 0055–0060, pmaports 0030; [notes](audio.md) |
| USB hub or monitor touchscreen attached at boot stayed off until plugged in again: usb-signaller switched the USB role from host to device when it applied its default mode and when it stopped | fixed | pmaports 0080, usb-signaller 0001 |
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
| Voice calls: Q6Voice with a PCIe mailbox for the external modem, QRTR forwarding between modem and ADSP (flow control release to the right modem node), MHI satellite, vocproc without Tx topology, amplifier switch and gain for the earpiece | work, outgoing tested over VoLTE and 2G; patches still WIP, see [`modem/`](../modem/) | kernel 0117–0137, pmaports 0058 |
| VoLTE: 81voltd (IMS Data service for the modem) accepts the SDX55 on QRTR node 3 (`qrtr3`) | works, tested on congstar | pmaports 0069 |
| Mobile data together with VoLTE: the modem has one data channel, and with the IMS connection of 81voltd on it the internet connection never came up (Start Network: NoEffect). ModemManager now multiplexes that channel by default (QMAP, one `rmnet` link per connection, `CONFIG_RMNET`); 81voltd tries again when ModemManager is still initialising the modem after the SIM unlock, instead of leaving VoLTE off until a restart | works | pmaports 0085–0087 |
| Modem over system sleep, wakeup by an incoming call: the PCIe links stayed in L1.2 over suspend because the root ports stay in D0, and when the modem had to leave L1.2 for a call the link went down and the modem was gone until a reboot. Only the endpoints now decide whether the host takes the link down for suspend; the modem is a wakeup device, and the controller takes WAKE# (GPIO 87) as wakeup interrupt while a wakeup device sits below it. The link goes off for suspend and comes back on resume with the modem still registered | works | kernel 0171–0173, pmaports 0088 |
| VoLTE after the SIM unlock and after resume: a bearer that 81voltd connected right after the SIM unlock derailed ModemManager (modem enabled but never registered, no mobile data), and ModemManager cancels a connection attempt that runs while it enables or resynchronises the modem, which left VoLTE off (calls on 2G, no data during a call). 81voltd waits until the modem is registered and repeats a cancelled attempt | works | pmaports 0089 |
| IMS connection over system sleep: NetworkManager disconnects all bearers when it brings mobile data down, also before suspend; the modem lost its IMS connection, asked for it again and woke the phone within seconds. A disconnect of all bearers now only covers the ones the Simple interface connected. ModemManager also no longer asks for WDS event reports, which it only logged: the dormancy report woke the phone ten seconds after it went to sleep | works | pmaports 0090 |
| Mobile data over system sleep: NetworkManager took mobile data down before every suspend and brought it back after the resume with a new address. It now leaves modem devices connected, and data that arrives for the phone wakes it | works | pmaports 0103 |
| ModemManager without a SIM over system sleep: after each resume ModemManager treats the missing SIM as a SIM swap and recreates the modem; the data port reset then also took the ignored `mhi_swip0` port, and the qcom-soc plugin aborted ModemManager on an assertion. The reset now only takes net ports | works | pmaports 0105 |
| Wake-on-WLAN (`iw phy phy0 wowlan enable magic-packet`): the host took the link of the QCA6390 down for suspend under the running firmware, because the chip reports PME from D3cold, and the phone crashed on the first suspend. The chip now keeps its power, link and interconnect votes while it is to wake the system, stays in D0 with MHI out of M3 as with the vendor driver (in M3 the firmware cannot page code in and woke the phone at once with a page fault), and WAKE# (GPIO 81) is not armed for it. The firmware learns from the QMI host capabilities which MSI wakes the host, ath11k listens to that MSI over system sleep, WoW is enabled for a system suspend, and only SA Query action frames wake the host. The modem keeps waking the system with WAKE# on GPIO 87 | works: a magic packet wakes the phone within a few seconds | kernel 0232–0240, pmaports 0104, 0106 |
| GNSS over system sleep: the 1 Hz tracking session kept the modem talking, which woke the phone at once; `sdx55-gnss-sleep.service` stops `sdx55-gnss` before suspend and starts it after resume | works | `modem/sdx55-gnss-sleep.service` |
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
| Hardware video decoding and encoding: with the display off the video core ran at 1332 MHz on a LOW_SVS vote and decoded frames came out corrupted; Venus scaled the wrong clock; the Iris encoder squeezed the aligned buffer into the picture | fixed; H.264, HEVC and VP9 up to 2160p50 frame-exact with the display on and off | kernel 0223–0226, pmaports 0094; [notes](#video-codec-clocks-and-voltage) |
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
| Charging: at least 500 mA of USB input while VBUS is present and the phone is not the source; before, the input was cut off when TCPM reported the source offline and the phone ran from the battery with the charger attached | works | kernel 0165, pmaports 0075 |
| Charging: USB-A detection also when USB-C does not attach. A USB-A to USB-C cable that pulls up both CC pins looks like a debug accessory to the PMIC, TCPM never attaches, and the input stayed at 500 mA; after two seconds of VBUS without an attach the charger now runs BC1.2 detection, so a USB-A charger gets 1.5 A. Reported by gavin8112-web in issue #17 | works, confirmed by the reporter | kernel 0230, pmaports 0101 |
| Charging: charge by the bq27411 fuel gauge with the temperature zones and limits of the stock firmware; the battery stopped at about 88 % because the PM8150B ends each charge cycle early without its own fuel gauge. See [charging.md](charging.md) | works | kernel 0166–0167, pmaports 0075 |
| Charging: the PM8150B terminates on its analog current sense. The ADC termination needs the battery current of the PMIC fuel gauge, which mainline does not run, so the charger ended each cycle a few seconds into constant voltage and the last ten percent took about 50 minutes | works, tested from a computer port | kernel 0231, pmaports 0102 |
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
| Autofocus faster and calmer: statistics for every second frame, and a climb from the current lens position (large steps where the image is evenly blurred, coarse steps near the peak, Gaussian fit instead of a fine sweep) instead of a full sweep from the far end for every scan; time to focus main 4.6 → 1.2 s, ultrawide 4.3 → 1.1 s, telephoto 2.7 → 0.6 s | works | libcamera 0009–0010, pmaports 0066 |
| OIS of the telephoto camera: its LC898128 has no gyroscope of its own and runs as a slave of the main camera's controller, which passes the gyroscope data on (as in the vendor kernel); the main controller gets its core supply PM8009 L1 | works, about 10 % sharper hand-held telephoto frames | kernel 0152–0153, pmaports 0067 |
| Faster preview: 2000×1500 4×4 binned modes for main and ultrawide over the full field of view, built from the stock 2000×1128 settings at the link rate of the 4000×3000 mode; libcamera picks them for previews up to 1280×960 | works, 60 fps instead of 30; the 4×4 mode needs about twice the analogue gain | kernel 0154–0155, pmaports 0067 |
| Telephoto sensor supply `afvdd` was missing (dummy regulator) | works | kernel 0156, pmaports 0067 |
| White balance: the AWB uses the pixels that look nearly grey with the current gains, so large coloured areas no longer tint the picture; gains below 1.0 allowed (`minGain`), which removes the red cast of the colour filter camera; colour matrices of the stock tuning for the front camera, where the nearly grey pixels count only half (`greyWeight` 0.5): it mostly sees display light | works | libcamera 0011–0012, pmaports 0068 |
| Phase detection autofocus on the main camera: in the 4000×3000 mode the IMX689 sends its phase detection pixels as a second CSI-2 stream (virtual channel 1, data type 0x30, 2000×1500); the CSID passes it to its second RDI (module parameters `rdi_vc` and `rdi_dt`), and stopping one RDI no longer resets the whole VFE. libcamera captures that stream, measures the shift between the left and right pixels of its even lines in the area of the sharpness measure and jumps the lens there, then fits the sharpness peak from two fine steps | works, time to focus 1.7 → 1.0 s; only in the 4000×3000 mode at 30 fps, the 60 fps preview mode has no phase data | kernel 0168, libcamera 0013–0015, pmaports 0081–0082, `system/qcom-camss-pdaf.conf` |
| Main camera preview in the mode with phase detection: libcamera picks the 4000×3000 mode for processed streams of the main camera, so previews get the faster autofocus at 30 fps instead of 60; `LIBCAMERA_SIMPLE_PDAF=0` keeps the 2000×1500 mode. In the binned mode the sensor stops sending images when its phase detection output (register 0x3005) is on | works | libcamera 0016, pmaports 0084 |
| All cameras missing now and then after boot: the first CCI transfer to a sensor timed out (seen with the front camera and with the ultrawide), its probe failed and CAMSS, which waits for all five sensors, registered none; the CCI driver now runs a transfer that timed out again, and the IMX471 driver powers the sensor up again and retries | works | kernel 0169–0170, pmaports 0083, 0085 |

Kernel patch 0013 is a generic CAMSS fix, not specific to this phone: on SM8250 the
`camnoc_axi_src` clock was never scaled, so full resolution RDI capture never completed a
frame, while binned modes with shorter lines still worked. Other SM8250 devices using CAMSS
should be affected too.

Kernel patch 0049 accepts the 4684-byte sensor-information layout found on an IN2023
OnePlus 8 Pro: two hardware sources per sensor and seven algorithm records. It bounds
virtual-sensor writes to those seven records and preserves the existing layout rules.
Without it, the sensor device-info driver fails to bind with `-EINVAL`.

The telephoto module has two chips next to the sensor: an LC898128 at 0x24 for the optical
image stabilisation and the LC898217XC at 0x74 that moves the lens. The module has no
gyroscope; the main camera's LC898128 reads the gyroscope and passes the data on over SPI
(command 0xf017), so it is powered while the telephoto camera runs, without moving its
own lens.
While the telephoto camera streams, its bus also answers at 0x75, which no driver uses.
It reads back only zeros and is most likely a second address of the LC898217XC, not
another actuator. Main (AK7377 at 0x0c) and ultrawide (AK7377 at 0x0f) are the other
cameras with a focus actuator; the stock module files list none for the front camera
and the colour filter camera, which have fixed focus.

The autofocus starts at the current lens position and climbs the sharpness curve: large
steps while the image is evenly blurred, coarse steps near the peak, a turn when the
first step makes the image clearly less sharp. The final position is the top of a
Gaussian through the sharpest position and its neighbours. In continuous mode it scans
again when the sharpness changes for 0.4 s.

## Video codec clocks and voltage

The SM8250 device tree gave the video codec MX as its only performance domain and listed
the OPPs in rates of the clock source `video_cc_mvs0_clk_src` (720–1332 MHz). The video
core also runs from MMCX, and both drivers set the OPP rate on a clock behind a fixed
divider: Iris on `vcodec0_core` (source / 3), Venus on `core` (source / 2). The RCG
rounded every request to a 1332 MHz source while the voted corner followed the OPP down
to LOW_SVS, and MMCX was not voted at all. With the display on, the display controller
holds MMCX at NOM and hides this. With the display off, 4K decoding went wrong from a
point in the stream onwards, also with Venus, and 720p VP9 through Iris often; 1080p
H.264 and HEVC stayed clean in the tests.

- Kernel 0223 adds MMCX to the codec's power domains, with the same corner as MX per OPP.
- Kernel 0224 lists the core clock rates the stock firmware allows (240, 338, 366 and
  444 MHz) with the corners of the stock `videocc-kona` table.
- Kernel 0225 makes Venus scale `vcodec0_core`, the clock its frequency table is in.
  Venus now picks the clock by load (240 MHz core for 4K50, still more than three times
  real time) instead of running at the top rate on a low vote.
- Kernel 0226: S_FMT on the encoder's raw side set the crop and the coded size to the
  aligned buffer (720 lines to 736), and HFI gen1 passed the aligned size to the firmware
  as the input frame size, so the firmware scaled the padding lines into the picture.
  The encoder now codes the requested size.

Tested with ffmpeg against libavcodec, every frame by MD5: VP9 720p30 and 2160p50, H.264
and HEVC 1080p and 2160p50, 20 runs with the display off and more with it on. H.264 and
HEVC with Iris and Venus, VP9 with Iris only.
The encoder reaches 47–49 dB PSNR at 8 Mbit/s for 360p to 1080p in H.264 and HEVC.

ffmpeg's V4L2 encoder copies every plane with the buffer's aligned height instead of the
frame's height and reads past the end of a 720- or 1080-line frame (segfault).
`ffmpeg-patches/0001-avcodec-v4l2-copy-frames-into-padded-buffers.patch` fixes that; until
an ffmpeg with it is installed, encode with heights that are a multiple of 32. ffmpeg also
waits forever when the V4L2 encoder feeds a Matroska file, which needs the stream headers
before the first frame; write a raw `.h264` or `.hevc` stream and remux it.

## Other notes

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

## Iris VP9 experiment

Kernel patches 0227–0229 and package patch 0095 carry the SM8250 VP9 firmware fixes
and zero-delay decoder controls (renumbered on merge, they were 0174–0176 and 0091 in
the pull request); the package keeps Venus selected and leaves Iris disabled.
The November 14 r88 tests produced reference-exact 720p VP9 through Iris and the
QCOM VA-API bridge, and direct V4L2 playback rendered all 240 frames at 2160p50;
VA-API rendering dropped frames and screen-off decoding corrupted pixels. The
screen-off corruption was the video core's clock and voltage, also with Venus; kernel
0223–0225 fix it, see [Video codec clocks and voltage](#video-codec-clocks-and-voltage).
The separate `qcom-va-driver-patches/0001-export-the-versioned-libva-entry-point.patch`
applies to bridge commit `0980a1d`, whose current master still lacks the fix;
installing the bridge and rebuilding QtWebEngine with VA-API remain separate work.
On November 18 the stack was tested on the phone with Iris enabled: VP9 720p30 and
2160p50, H.264 and HEVC up to 2160p50 decoded frame-exact with the display on and off.
VA-API was not tested again.

Attribution for this experiment:

- Kernel 0228: Xilin Wu's [upstream HFI Gen2 display-delay patch](https://lore.kernel.org/linux-media/20261029-iris-va-fixes-v1-1-44a2783f782b@radxa.com/), with the original author, commit message and sign-off retained; the backport changes surrounding context only.
- Kernel 0229: Roman Kuraev's SM8250 HFI Gen1 adaptation of Xilin Wu's patch, with the borrowed capability definitions and control handling credited in its commit message.
- Kernel 0227: Roman Kuraev's port-specific implementation, using the firmware protocol in the [Qualcomm driver published by OnePlus](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8250/blob/cad09e061ef6cf689a4a1e54d27562e0f042236a/techpack/video/msm/vidc/msm_vdec.c), whose source credits The Linux Foundation.
- The libva entry-point change: Roman Kuraev's local compatibility fix for the separate [qcom-va-driver project](https://github.com/radxa-pkg/qcom-va-driver/tree/0980a1decf26d34c9aa71cd0a4a0d25703a7a17f), whose MIT license credits the libva-v4l2 contributors as the base project's copyright holders.

## Patch numbers in use

The next free numbers are kernel 0241 and package 0107. Kernel 0164 is kept for the
DisplayPort DSC draft. Most package patches change the release and the checksums of the
kernel package, so a new one has to be made on top of the last one; package numbers
0070–0074 cannot be filled in later.

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
  follows these patches; see the table above. 0066 adds libcamera 0009–0010 (faster autofocus)
  and its tuning, 0067 adds kernel 0152–0156 (telephoto OIS, binned modes) and 0068
  adds libcamera 0011–0012 (white balance) with the tuning. 0075 adds kernel
  0165–0167 (charging). From 0076 on the DisplayPort patches continue; see the table above.
  0081 adds kernel 0168 and 0082 libcamera 0013–0015 with the tuning (phase detection
  autofocus), 0083 adds kernel 0169 (front camera probe) and 0084 libcamera 0016 (preview
  in the mode with phase detection). 0085 adds kernel 0170 (CCI transfer retry) and
  enables `CONFIG_RMNET`, 0086 and 0087 change ModemManager and 81voltd (mobile data
  together with VoLTE). 0088 adds kernel 0171–0173 (modem over system sleep), 0089 and
  0090 change 81voltd and ModemManager for it. 0094 adds kernel 0223–0226 (video
  codec clocks and voltage, Iris encoder size), 0095 adds 0227–0229 (Iris VP9
  experiment, Iris stays off). 0101 adds kernel 0230 (charger detection without a
  USB-C attach), 0102 adds 0231 (charge termination on the analog current sense).
  0103 changes NetworkManager (mobile data over system sleep), 0104 adds kernel 0232–0234
  (Wake-on-WLAN without a crash), 0105 changes ModemManager (no abort when the modem is
  recreated), 0106 adds kernel 0235–0240 (wake by Wake-on-WLAN).
  Package numbers 0050, 0051, 0053, 0062–0065 and 0070–0074 and kernel numbers 0105–0113,
  0151 and 0164 are unused.
- `modem/` – setup script and small services for the SDX55 modem and GPS.
- `sensors/` – script that sets up the sensors from your own phone.
- `firmware/` – boot service that copies SLPI, Venus and CDSP firmware from your own phone.
- `docs/` – this file and details moved out of the README.
- `iio-sensor-proxy-patches/` – against https://gitlab.freedesktop.org/hadess/iio-sensor-proxy tag `3.9`.
- `hexagonrpc-patches/` – against https://github.com/linux-msm/hexagonrpc tag `v0.5.0`.
  Adds a writable sensor registry (`-w DIR`), needed by the OnePlus sensor DSP.
- `usb-signaller-patches/` – against https://codeberg.org/DylanVanAssche/usb-signaller tag
  `v0.4.3`, carried in `temp/usb-signaller` by package patch 0080. Keeps the USB host role
  that the Type-C port controller picks when a hub or monitor is attached at boot.
- `qcom-va-driver-patches/` – against https://github.com/radxa-pkg/qcom-va-driver commit
  `0980a1d`, not in any package yet. Exports the versioned libva entry point.
- `ffmpeg-patches/` – against FFmpeg 9.0.2, not in any package. Lets the V4L2 encoders
  take frames whose height is not a multiple of 32.
- `libcamera-patches/` – against libcamera v0.8.0 plus the patches already carried in
  Nura `temp/libcamera`: sensor helpers for S5K3M5 (0001) and IMX586, IMX689 and GC5035
  (0002), the autofocus series (0003–0005), a shorter autofocus scan (0006), a noise
  robust sharpness measure (0007) and whole-frame statistics for the GPU debayer (0008),
  statistics for every second frame (0009), an autofocus that climbs from the current
  lens position (0010), a white balance on nearly grey pixels (0011), a `minGain`
  tuning value for the AWB (0012) and the phase detection autofocus of the main camera
  (0013–0015), also for its preview (0016). The IMX471
  helper is upstream since v0.8.0. The autofocus and image tuning is in the sensor files of
  pmaports patches 0034, 0055, 0066, 0068 and 0082.
- `system/` – small files the image adds: the `ois-gyro` service, which keeps the
  gyroscope running while the main camera's OIS is active, the AK7375 option without the
  lens ramp, the CSID option for the phase detection stream of the main camera, camera
  names for PipeWire and 16-bit samples for the speakers.

Kernel patches 0033–0041 are not my work either: they are the series "media: camss: Add
support for C-PHY" v5 by David Heidelberg, with patches by Casey Connolly and Luca Weiss.
Use the original from lore.kernel.org if you need it.

Kernel patch 0101 is not my work: it is v2 of "drm/display: add hw_params callback
function to drm_connector_hdmi_audio_ops" by Jianfeng Liu, carried unchanged
(https://lore.kernel.org/r/20250925040530.20731-1-liujianfeng1994@gmail.com).

Kernel patches 0146–0147 and 0161–0162 are not my work: they are patches 2, 3, 1 and 4
of v2 of "drm/msm/dpu: various dpu resource allocation/release mismatch fix" by Xi Zhang,
carried unchanged (https://lore.kernel.org/r/20261026-msm-dpu-res-clean-v2-1-3d864435186e@gmail.com).
Patches 5 (modeset on every colour management change) and 6 (DSC 1.2 hardware, which
SM8250 does not have) are left out.

Kernel patch 0148 is not my work: it is upstream commit d858770e86e7 ("drm/msm/dp: return
0 from audio_prepare when cable is disconnected") by Kumar Anurag.

Kernel patch 0145 is not my work: it is "drm/msm/dp: skip PUSH_IDLE when the link was
never enabled" by Jesse Casco, reviewed by Dmitry Baryshkov
(https://lore.kernel.org/r/20260808171325.133041-1-jesse.casco@gmail.com), with a note
on where its hunk lands in 7.2. Kernel patch 0157 is patch 6 of v8 of "drm: handle
IRQ_HPD events correctly" by Dmitry Baryshkov
(https://lore.kernel.org/r/20261024-hpd-irq-events-v8-6-6ee949e7a384@oss.qualcomm.com).
Kernel patch 0158 is v3 of "drm/msm/dp: hold one runtime PM reference per plugged state"
by Joonhoe Kim, also reviewed by Dmitry Baryshkov
(https://lore.kernel.org/r/20261024051952.2006-1-26rote@gmail.com), which depends on 0157.
The code of all three is unchanged.

Kernel patch 0014 (LC898217XC driver) is not my work: it is v4 of the driver Vasiliy
Doylov posted to the linux-media mailing list in March 2026
(https://lkml.iu.edu/hypermail/linux/kernel/2603.3/02275.html). It was taken from that
archive, which obscures the author's email address; use the original from lore.kernel.org
if you need it.
