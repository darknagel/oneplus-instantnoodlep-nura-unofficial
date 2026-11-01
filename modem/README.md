# Modem & GPS (SDX55)

**Works:** modem online, LTE + 5G bands, GPS fix without SIM, SIM with PIN,
network registration, mobile data (IPv6 only, up to 90 Mbit/s, tested on congstar),
SMS send and receive.
**Not done:** calls.
Tested on one IN2023 (EU). Not in the prebuilt image.

## Setup

1. Build and flash the kernel with all pmaports patches (0018 and 0020: kernel,
   0019: ModemManager), see
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

Mobile data on congstar, as root (the password is the public one of the APN):

```sh
nmcli con add type gsm ifname '*' con-name congstar apn internet.v6.telekom gsm.username congstar gsm.password cs
```

SMS app for Plasma Mobile: `apk add spacebar`, then log in again. Enter numbers
with the country code (`+49...`).

## Facts

- The modem firmware **must come from your own `modem_a` partition** –
  `install.sh` copies it. The firmware package of the distribution is a
  different version; with it the modem stays offline.
- Modem data (EFS, NV, DDR) is copied from your own partitions too. It
  contains calibration and IDs: **never share it**.
- Without a SIM, ModemManager lists the modem as failed (`sim-missing`); GPS
  still works through `sdx55-gnss`.
- The modem does not activate the SIM on its own; `sdx55-sim` does it. Both
  slots were tested for detection, network registration only in slot 1.
- Data only runs on the `IP_HW0` channel (`mhi_hwip0`). `sdx55-sim` loads
  `mhi_net` and then starts ModemManager, about 30 s after the modem is up.
- Unmodified ModemManager needs pmaports patch 0019: it aborts after a SIM PIN
  unlock and cannot use `mhi_net` over QRTR. A later `apk upgrade` can replace
  the patched package.
- If the modem crashes: reboot.
- Kernel patches 0023–0030 are still debug quality.
