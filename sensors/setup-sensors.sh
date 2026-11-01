#!/bin/sh
# Set up the accelerometer, light and proximity sensors of the OnePlus 8 Pro.
# Run as root on the phone. The sensor DSP needs OnePlus' own files, which may
# not be redistributed, so they come from your own phone:
#  - the DSP libraries from the dsp_a partition,
#  - the sensor configuration from Android, which you saved before flashing
#    (see the README): vendor/ holds /vendor/etc/sensors, odm/ /odm/etc/sensor.
# Usage: setup-sensors.sh DIR
set -e
SRC=${1:?usage: setup-sensors.sh DIR with vendor/ and odm/}
F=/usr/share/qcom/sm8250/OnePlus/instantnoodlep

# adb pull nests the folder when the target already exists
[ -d "$SRC/vendor/sensors" ] && mv "$SRC"/vendor/sensors/* "$SRC"/vendor/
[ -d "$SRC/odm/sensor" ] && mv "$SRC"/odm/sensor/* "$SRC"/odm/

[ -d "$SRC/vendor/config" ] || { echo "$SRC/vendor/config is missing"; exit 1; }
[ -d "$SRC/odm/config" ] || { echo "$SRC/odm/config is missing"; exit 1; }
command -v sscregistrygen >/dev/null || { echo "sscregistrygen is missing"; exit 1; }

mkdir -p $F/dsp/sdsp $F/sensors/config $F/sensors/persist/registry $F/socinfo

MNT=$(mktemp -d)
mount -o ro /dev/disk/by-partlabel/dsp_a "$MNT"
cp "$MNT"/sdsp/* $F/dsp/sdsp/
umount "$MNT"
rmdir "$MNT"

cp "$SRC"/vendor/config/* $F/sensors/config/
cp "$SRC"/odm/config/* $F/sensors/config/
cp "$SRC"/vendor/sns_reg_config $F/sensors/sns_reg.conf

# This phone reports itself to the sensor DSP like this under Android
printf 'MTP\n' > $F/socinfo/hw_platform
printf 'Unknown\n' > $F/socinfo/platform_subtype
printf '0\n' > $F/socinfo/platform_subtype_id
printf '65536\n' > $F/socinfo/platform_version
printf '2.1\n' > $F/socinfo/revision
printf '356\n' > $F/socinfo/soc_id

# The initial registry: vendor configuration, OnePlus configuration on top
sscregistrygen -p MTP -s 356 "$SRC"/vendor/config $F/sensors/persist/registry
sscregistrygen -p MTP -s 356 "$SRC"/odm/config $F/sensors/persist/registry
printf '%s\n' "$(sed -n 's/^version=//p' $F/sensors/sns_reg.conf)" > $F/sensors/persist/sns_reg_version

find $F -type d -exec chmod 755 {} +
find $F -type f -exec chmod 644 {} +

systemctl stop hexagonrpcd-sdsp 2>/dev/null || true
rm -rf /var/lib/hexagonrpcd/sensors-registry
systemd-tmpfiles --create hexagonrpcd-oneplus-instantnoodlep.conf 2>/dev/null || systemd-tmpfiles --create
echo "Done. Reboot, then check with: monitor-sensor"
