#!/bin/sh
# Set up the accelerometer, gyroscope, light, proximity and magnetometer
# (with compass) sensors of the OnePlus 8 Pro.
# Run as root on the phone. The sensor DSP needs OnePlus' own files, which may
# not be redistributed, so they come from your own phone:
#  - the DSP libraries from the dsp partition of the active slot,
#  - the sensor configuration from Android, which you saved before flashing
#    (see the README): vendor/ holds /vendor/etc/sensors, odm/ /odm/etc/sensor.
#  - the proximity calibration from this phone's persist partition.
# Usage: setup-sensors.sh DIR | --proximity-calibration
set -e
SRC=${1:?usage: setup-sensors.sh DIR with vendor/ and odm/, or --proximity-calibration}
F=/usr/share/qcom/sm8250/OnePlus/instantnoodlep
CAL=stk2232_0_platform.ps.fac_cal

copy_proximity_calibration() (
	MNT=$(mktemp -d)
	trap 'rmdir "$MNT"' EXIT
	trap 'exit 1' HUP INT TERM
	# ro alone can still replay the ext4 journal; leave Android persist untouched.
	mount -t ext4 -o ro,noload /dev/disk/by-partlabel/persist "$MNT"
	trap 'umount "$MNT"; rmdir "$MNT"' EXIT
	SOURCE=$MNT/sensors/registry/registry/$CAL
	[ -s "$SOURCE" ] || { echo "Missing proximity calibration: $SOURCE" >&2; exit 1; }
	cp "$SOURCE" "$F/sensors/persist/registry/$CAL"
)

# Repair an existing install without extracting vendor/odm or resetting other sensors.
if [ "$SRC" = --proximity-calibration ]; then
	REGISTRY=/var/lib/hexagonrpcd/sensors-registry/registry
	[ -f "$REGISTRY/$CAL" ] && [ -d "$F/sensors/persist/registry" ] || {
		echo "Sensor registry is missing; run the full sensor setup first" >&2
		exit 1
	}
	copy_proximity_calibration
	systemctl stop hexagonrpcd-sdsp
	BACKUP=/var/lib/hexagonrpcd/$CAL.before-factory
	[ -e "$BACKUP" ] || cp -p "$REGISTRY/$CAL" "$BACKUP"
	cp "$F/sensors/persist/registry/$CAL" "$REGISTRY/$CAL"
	chown fastrpc:fastrpc "$REGISTRY/$CAL"
	chmod 644 "$REGISTRY/$CAL"
	echo "Done. Reboot to reload proximity calibration, then check with: monitor-sensor --proximity"
	exit 0
fi

# adb pull nests the folder when the target already exists
[ -d "$SRC/vendor/sensors" ] && mv "$SRC"/vendor/sensors/* "$SRC"/vendor/
[ -d "$SRC/odm/sensor" ] && mv "$SRC"/odm/sensor/* "$SRC"/odm/

[ -d "$SRC/vendor/config" ] || { echo "$SRC/vendor/config is missing"; exit 1; }
[ -d "$SRC/odm/config" ] || { echo "$SRC/odm/config is missing"; exit 1; }
command -v sscregistrygen >/dev/null || { echo "sscregistrygen is missing"; exit 1; }

mkdir -p $F/dsp/sdsp $F/sensors/config $F/sensors/persist/registry $F/socinfo

SLOT=a
for arg in $(cat /proc/cmdline); do
	case "$arg" in androidboot.slot_suffix=_b) SLOT=b ;; esac
done
MNT=$(mktemp -d)
mount -o ro /dev/disk/by-partlabel/dsp_$SLOT "$MNT"
rm -f $F/dsp/sdsp/* $F/dsp/sdsp/.from-dsp_*
cp "$MNT"/sdsp/* $F/dsp/sdsp/
touch $F/dsp/sdsp/.from-dsp_$SLOT
umount "$MNT"
rmdir "$MNT"

# OnePlus switches the software motion detector (AMD) off on SM8250. Gyro
# calibration needs it, and the magnetometer calibration and the compass
# (rotation vector) need the gyro calibration, so keep it on.
TMP=$(mktemp -d)
mkdir $TMP/vendor $TMP/odm
cp "$SRC"/vendor/config/* $TMP/vendor/
cp "$SRC"/odm/config/* $TMP/odm/
rm -f $TMP/vendor/kona_amd_sw_disabled.json $TMP/odm/kona_amd_sw_disabled.json
cat > $TMP/odm/mainline_amd_sw_enabled.json <<'JSON'
{
  "config": {
    "hw_platform": ["MTP"],
    "soc_id": ["356"]
  },
  "sns_amd": {
    "owner": "sns_amd",
    "enabled": { "ver": "0", "type": "int", "data": "1" }
  }
}
JSON

rm -f $F/sensors/config/*
cp $TMP/vendor/* $F/sensors/config/
cp $TMP/odm/* $F/sensors/config/
cp "$SRC"/vendor/sns_reg_config $F/sensors/sns_reg.conf

# This phone reports itself to the sensor DSP like this under Android
printf 'MTP\n' > $F/socinfo/hw_platform
printf 'Unknown\n' > $F/socinfo/platform_subtype
printf '0\n' > $F/socinfo/platform_subtype_id
printf '65536\n' > $F/socinfo/platform_version
printf '2.1\n' > $F/socinfo/revision
printf '356\n' > $F/socinfo/soc_id

# The initial registry: vendor configuration, OnePlus configuration on top
sscregistrygen -p MTP -s 356 $TMP/vendor $F/sensors/persist/registry
sscregistrygen -p MTP -s 356 $TMP/odm $F/sensors/persist/registry
rm -rf $TMP
printf '%s\n' "$(sed -n 's/^version=//p' $F/sensors/sns_reg.conf)" > $F/sensors/persist/sns_reg_version

# Generated defaults have zero offsets; proximity needs this unit's factory values.
copy_proximity_calibration

find $F -type d -exec chmod 755 {} +
find $F -type f -exec chmod 644 {} +

systemctl stop hexagonrpcd-sdsp 2>/dev/null || true
rm -rf /var/lib/hexagonrpcd/sensors-registry
systemd-tmpfiles --create hexagonrpcd-oneplus-instantnoodlep.conf 2>/dev/null || systemd-tmpfiles --create
echo "Done. Reboot, then check with: monitor-sensor"
