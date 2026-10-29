# SDX55 modem and GPS (work in progress)

The OnePlus 8 Pro has an external Qualcomm SDX55 5G modem on PCIe. It has no
flash of its own: the phone has to load its firmware over MHI/Sahara, serve
its files over TFTP-on-QRTR and store the modem's file system (EFS) when the
modem asks for it. This directory and pmaports patch 0018 do that on Linux.

**State:** the modem boots, comes online and sees its LTE/5G bands (LTE 1, 2,
3, 4, 5, 7, 8, 12, 13, 17, 18, 19, 20, 25, 26, 28, 32, 34, 38, 39, 40, 41, 42,
46, 66; NR n1, n3, n7, n28, n78). **GPS works**: first fix after a few minutes
from a cold start, without SIM. Calls, SMS and mobile data have not been
tested yet (no SIM in the test phone). Only tested on one IN2023 (EU).

## Install

1. Build and flash the modem kernel (`pmaports-patches/0018`, see "Build it
   yourself" in the main README; 0018 is part of the patch set).
2. Copy this directory to the phone and run, as root:

   ```sh
   sh install.sh
   reboot
   ```

`install.sh` takes the modem firmware from the phone's own `modem_a`
partition and the modem data from its own `mdm1m9kefs1/2`,
`mdm1oemnvbktmp` and `mdmddr` partitions. Nothing proprietary or device
specific is shipped here, and none of it should be shared: the EFS and NV
data contain the phone's calibration and identifiers.

After the reboot:

```sh
sdx55-modemstate          # operating mode, registration
cat /dev/gnss-sdx55       # NMEA from the GNSS engine (1 Hz)
```

`/dev/gnss-sdx55` works with gpsd (`gpsd -n /dev/gnss-sdx55`) and anything
else that reads NMEA from a serial port.

## What runs

| Part | Does |
|---|---|
| kernel `mhi_sahara` + `mhi_pci_generic` profile | loads the firmware (Sahara images 6–42), answers the modem's EFS sync (Sahara memory debug on MHI channel 10/11) |
| `sdx55-rfsd` | TFTP over QRTR (service 4096, instance 3): `/readonly` from `modem_a`, `/readwrite` in `/var/lib/sdx55-rfs` |
| udev rule + `sdx55-efssave` | stores every EFS sync in `/var/lib/sdx55-rfs/efs/` (newest ten) |
| `sdx55-gnss` | sets the modem online if nothing else did, unlocks the GNSS engine, enables standard NMEA, starts a 1 Hz session, feeds `/dev/gnss-sdx55` |
| `78-mm-sdx55-qrtr.rules` | lets ModemManager use the modem over QRTR (`qcom-soc` plugin) |

## Things we learned

- **The firmware must come from the phone's own `modem_a`.** The modem loads
  its RF configuration (`modem_pr/so/663_0_0.mbn`) and MCFG files from
  `modem_a` at run time. With a different firmware version, e.g. from the
  `firmware-oneplus-instantnoodlep-modem` package, the modem rejects the RF
  configuration ("RFC MBN version from the device does not match with MBN
  version from full build"), falls into a calibration/test mode and stays
  offline with no bands.
- Sahara image 20 is OnePlus' NV backup (`mdm1oemnvbktmp`), not
  `mdm1m9kefs3`. Without it the modem's `oem_mcfg` task keeps asking for a
  restart.
- The modem syncs its EFS through Sahara memory debug, one 2 MiB image
  (`m9kefs1` or `m9kefs2`) per sync. If nobody answers, it resets itself
  after about three seconds.
- Synced EFS images only work as a pair from the same session; replacing
  only one of `efs1.bin`/`efs2.bin` makes the modem crash while booting.
  `install.sh` keeps the partition copies, so every boot starts from the
  same EFS; the GNSS engine lock is cleared by `sdx55-gnss` each time.
- Without a SIM, ModemManager marks the modem as failed ("sim-missing") and
  offers no location; that is why `sdx55-gnss` talks to QMI LOC directly.

## Known issues

- Kernel patches 0023–0030 are debug quality (verbose logging, GPIO hogs
  instead of proper AP2MDM control, IP_HW0 channels left out).
- No modem restart from the phone side: if the modem crashes, reboot.
- Calls (audio over MHI) are not supported.
