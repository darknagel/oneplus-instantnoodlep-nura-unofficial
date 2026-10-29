# Modem & GPS (SDX55)

**Works:** modem online, LTE + 5G bands, GPS fix without SIM.
**Untested:** SMS, mobile data (no SIM yet). **Not done:** calls.
Tested on one IN2023 (EU). Not in the prebuilt image.

## Setup

1. Build and flash the kernel with all pmaports patches (includes 0018), see
   "Build it yourself" in the [main README](../README.md).
2. On the phone, as root:

   ```sh
   apk add git
   git clone https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial.git
   sh oneplus-instantnoodlep-nura-unofficial/modem/install.sh
   reboot
   ```

3. Check:

   ```sh
   sdx55-modemstate        # should say "online"
   cat /dev/gnss-sdx55     # NMEA, first fix after a few minutes outside
   ```

GPS for apps: `apk add gpsd && gpsd -n /dev/gnss-sdx55`.

## Facts

- The modem firmware **must come from your own `modem_a` partition** –
  `install.sh` copies it. The firmware package of the distribution is a
  different version; with it the modem stays offline.
- Modem data (EFS, NV, DDR) is copied from your own partitions too. It
  contains calibration and IDs: **never share it**.
- Without a SIM, ModemManager ignores the modem; GPS still works through
  `sdx55-gnss`.
- If the modem crashes: reboot.
- Kernel patches 0023–0030 are still debug quality.
