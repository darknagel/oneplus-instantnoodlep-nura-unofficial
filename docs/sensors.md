# Sensors

The sensors run on the sensor DSP (SLPI) and are read through `hexagonrpcd`, `libssc` and
`iio-sensor-proxy`. Check them with `monitor-sensor`, or directly with
`ssccli --sensor accelerometer --timeout 3`.

## What the image does

The image contains the sensor configuration from OxygenOS, proprietary OnePlus/Qualcomm
files. Since v2026.11.10 the `dsp-firmware` boot service copies the sensor DSP firmware
(SLPI), its libraries and the proximity calibration from your phone's own partitions at first
boot, so they match the OxygenOS version your phone had. The copies live in
`/lib/firmware/updates/postmarketos`, overriding the packaged firmware without replacing
package-owned files.

## Firmware layouts

SLPI builds of the same version read the sensor list in shared memory (SMEM item 130) in
different layouts: older ones with 2 chips per sensor type, newer ones with 3. Kernel patches
0061–0062 take the layout from the list itself, so the phone's own SLPI firmware finds the
magnetometer. Without them, as in v2026.11.08 and older images, the phone's own SLPI
firmware loses the magnetometer and compass.

Some bootloaders expose a 4684-byte sensor-information item and need kernel patch 0049,
which images have since v2026.11.10. Without it, the kernel reports
`unexpected SMEM item size 4684` and the accelerometer is unavailable.

On an IN2023 with older stock firmware, the packaged SLPI firmware also prevented the audio
DSP from starting (`start timed out`, `-110`). Using the phone's own SLPI firmware fixes it,
see [audio testing and limits](audio.md).

If the sensor DSP crashes 3 times within 60 seconds, `slpi-guard` stops it instead of letting
the kernel restart it forever, which used to break most of the phone
([#1](https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial/issues/1)). The sensors are then off until the next reboot;
`journalctl -u slpi-guard` shows if it stepped in.

## Proximity

If proximity stays "far" when covered, the generated sensor registry may have zeroed
calibration offsets. Images since v2026.11.10 import this phone's factory calibration from
the Android `persist` partition at first boot, mounted read-only without journal replay. On
an existing installation, as root:

```sh
wget -O /tmp/setup-sensors.sh https://raw.githubusercontent.com/darknagel/oneplus-instantnoodlep-nura-unofficial/main/sensors/setup-sensors.sh
sh /tmp/setup-sensors.sh --proximity-calibration && reboot
```

This backs up the current proximity calibration and leaves other sensor settings intact; the
sensor service stays stopped until reboot. Check with `monitor-sensor --proximity` while
covering and uncovering the earpiece area. Calibration is specific to each phone; do not copy
it from another unit.

## Compass

The compass needs the gyro calibration in the sensor DSP, which OnePlus switches off on SM8250
(`kona_amd_sw_disabled.json`); the image and `setup-sensors` keep it on. The heading becomes
accurate after the calibration has seen the phone moved around (a figure eight).

## Setting up sensors on older images or your own build

Images before v2026.11.08 and your own builds need the sensor files from your own phone:

1. **Before flashing**, with Android running and USB debugging on (not tested on Android,
   some files may need root):

   ```sh
   adb pull /vendor/etc/sensors vendor
   adb pull /odm/etc/sensor odm
   ```

2. After flashing, copy them over USB:

   ```sh
   ssh root@172.16.42.1 mkdir -p /root/android-sensors
   scp -r vendor odm root@172.16.42.1:/root/android-sensors/
   ```

3. On the phone. The script also copies the DSP files from the `dsp_a` partition (`dsp_b` if
   the phone started slot b).

   ```sh
   setup-sensors /root/android-sensors
   reboot
   ```

4. Check: `ssccli --sensor accelerometer --timeout 3`

Already on Linux? Get `vendor.img` and `odm.img` from a full OxygenOS update (not tested).
The DSP libraries come from your phone's own `dsp` partition, so they match the OxygenOS
version you had. The `firmware/` service does the same at boot.
