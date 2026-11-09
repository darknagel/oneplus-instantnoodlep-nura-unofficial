#!/bin/sh
# Copy the sensor DSP (SLPI), video codec (Venus) and compute DSP (CDSP)
# firmware from this phone's active modem partition, before udev loads drivers
# (dsp-firmware.service) and does nothing once the copies exist.
#
# pil-squasher joins Android's .mdt/.bNN files without changing signed segments.
# The updates directory overrides packaged SLPI firmware, which can be
# incompatible with the shared-memory layout left by an older bootloader.
# No proprietary firmware is distributed with this script.
set -eu
FW=${DSP_FW:-/lib/firmware/updates/postmarketos}
[ -s "$FW/venus.mbn" ] && [ -s "$FW/cdsp.mbn" ] && [ -s "$FW/slpi.mbn" ] && exit 0

# /dev/disk/by-partlabel does not exist yet this early
part() {
	for u in /sys/class/block/*/uevent; do
		if grep -qx "PARTNAME=$1" "$u"; then
			printf '/dev/%s\n' "$(sed -n 's/^DEVNAME=//p' "$u")"
			return
		fi
	done
	return 1
}

slot=
for arg in $(cat /proc/cmdline); do
	case "$arg" in
		androidboot.slot_suffix=_a) slot=a ;;
		androidboot.slot_suffix=_b) slot=b ;;
	esac
done
[ -n "$slot" ] || { echo "dsp-firmware: cannot determine the Android firmware slot" >&2; exit 1; }
device=$(part "modem_$slot")

mkdir -p "$FW"
TMP=$(mktemp -d "$FW/.dsp-firmware.XXXXXX")
MNT=$TMP/source
mkdir "$MNT"
mounted=false
cleanup() {
	if "$mounted"; then umount "$MNT" || return; fi
	rmdir "$MNT"
	rm -f "$TMP"/*.mbn
	rmdir "$TMP"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
mount -t vfat -o ro,nosuid,nodev,noexec "$device" "$MNT"
mounted=true
for fw in slpi venus cdsp; do
	[ -s "$FW/$fw.mbn" ] && continue
	[ -s "$MNT/image/$fw.mdt" ]
	pil-squasher "$TMP/$fw.mbn" "$MNT/image/$fw.mdt"
	[ -s "$TMP/$fw.mbn" ]
	chmod 644 "$TMP/$fw.mbn"
	mv "$TMP/$fw.mbn" "$FW/$fw.mbn"
	echo "dsp-firmware: copied $fw from modem_$slot"
done
