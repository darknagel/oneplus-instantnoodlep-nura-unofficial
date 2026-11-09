#!/bin/sh
# Copy the DSP firmware from this phone's own partitions of the active slot,
# before udev loads the drivers (dsp-firmware.service). Does nothing once the
# copies exist.
#
#  - modem_<slot>: sensor DSP (SLPI), video codec (Venus) and compute DSP
#    (CDSP). pil-squasher joins Android's .mdt/.bNN files without changing
#    the signed segments. The updates directory overrides packaged firmware,
#    which can be incompatible with the shared-memory layout of this phone's
#    bootloader.
#  - dsp_<slot>/sdsp: the libraries the sensor DSP loads through hexagonrpcd.
#    They belong to the SLPI firmware above, so they come from the same phone
#    and replace any copies from elsewhere.
# No proprietary firmware is distributed with this script.
set -eu
FW=${DSP_FW:-/lib/firmware/updates/postmarketos}
SDSP=${DSP_LIBS:-/usr/share/qcom/sm8250/OnePlus/instantnoodlep/dsp/sdsp}

# The slot the bootloader started; all firmware services read the same one
android_slot() {
	for arg in $(cat /proc/cmdline); do
		case "$arg" in
		androidboot.slot_suffix=_a) echo a; return 0 ;;
		androidboot.slot_suffix=_b) echo b; return 0 ;;
		esac
	done
	return 1
}

# /dev/disk/by-partlabel does not exist yet this early
android_part() {
	for u in /sys/class/block/*/uevent; do
		if grep -qx "PARTNAME=$1" "$u"; then
			printf '/dev/%s\n' "$(sed -n 's/^DEVNAME=//p' "$u")"
			return 0
		fi
	done
	return 1
}

slot=$(android_slot) || { echo "dsp-firmware: cannot determine the Android firmware slot" >&2; exit 1; }

need_fw=false
for fw in slpi venus cdsp; do
	[ -s "$FW/$fw.mbn" ] || need_fw=true
done
need_libs=false
[ -e "$SDSP/.from-dsp_$slot" ] || need_libs=true
"$need_fw" || "$need_libs" || exit 0

mkdir -p "$FW" "$SDSP"
TMP=$(mktemp -d "$FW/.dsp-firmware.XXXXXX")
MNT=$TMP/source
mkdir "$MNT"
mounted=false
cleanup() {
	if "$mounted"; then umount "$MNT" || return; fi
	rmdir "$MNT"
	rm -rf "$TMP"/*.mbn "$TMP"/sdsp
	rmdir "$TMP"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

if "$need_fw"; then
	mount -t vfat -o ro,nosuid,nodev,noexec "$(android_part "modem_$slot")" "$MNT"
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
	umount "$MNT"
	mounted=false
fi

if "$need_libs"; then
	mount -o ro,nosuid,nodev,noexec "$(android_part "dsp_$slot")" "$MNT"
	mounted=true
	[ -d "$MNT/sdsp" ]
	mkdir "$TMP/sdsp"
	cp "$MNT"/sdsp/* "$TMP/sdsp/"
	chmod 644 "$TMP"/sdsp/*
	rm -f "$SDSP"/* "$SDSP"/.from-dsp_*
	mv "$TMP"/sdsp/* "$SDSP/"
	touch "$SDSP/.from-dsp_$slot"
	echo "dsp-firmware: copied the sensor DSP libraries from dsp_$slot"
fi
