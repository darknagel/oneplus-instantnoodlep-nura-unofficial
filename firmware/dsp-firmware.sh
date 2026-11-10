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
#  - persist: the factory calibration of the proximity sensor. The generated
#    registry has zero offsets, and the sensor then never reports "near".
# No proprietary firmware or calibration is distributed with this script.
set -eu
FW=${DSP_FW:-/lib/firmware/updates/postmarketos}
SDSP=${DSP_LIBS:-/usr/share/qcom/sm8250/OnePlus/instantnoodlep/dsp/sdsp}
SENSORS=/usr/share/qcom/sm8250/OnePlus/instantnoodlep/sensors/persist/registry
REGISTRY=/var/lib/hexagonrpcd/sensors-registry/registry
CAL=stk2232_0_platform.ps.fac_cal
CAL_DONE=/var/lib/hexagonrpcd/.proximity-calibration

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
need_cal=false
[ -e "$CAL_DONE" ] || need_cal=true
"$need_fw" || "$need_libs" || "$need_cal" || exit 0

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
	umount "$MNT"
	mounted=false
fi

# Not every phone keeps the file, so a missing one is not an error. Without
# "noload", even a read-only ext4 mount replays the journal and writes to the
# Android partition.
if "$need_cal"; then
	if part=$(android_part persist) &&
	   mount -t ext4 -o ro,noload,nosuid,nodev,noexec "$part" "$MNT"; then
		mounted=true
		src=$MNT/sensors/registry/registry/$CAL
		if [ -s "$src" ]; then
			# The packaged registry seeds a new install, the writable copy
			# is what the sensor DSP reads on an existing one
			[ -d "$SENSORS" ] && cp "$src" "$SENSORS/$CAL" && chmod 644 "$SENSORS/$CAL"
			if [ -d "$REGISTRY" ]; then
				[ -e "$REGISTRY/$CAL" ] && cp -p "$REGISTRY/$CAL" "$REGISTRY/../$CAL.before-factory" 2>/dev/null || true
				cp "$src" "$REGISTRY/$CAL"
				chown fastrpc:fastrpc "$REGISTRY/$CAL" 2>/dev/null || true
				chmod 644 "$REGISTRY/$CAL"
			fi
			echo "dsp-firmware: imported the proximity calibration from persist"
		else
			echo "dsp-firmware: no proximity calibration on persist"
		fi
		umount "$MNT"
		mounted=false
	else
		echo "dsp-firmware: cannot read persist, keeping the proximity calibration"
	fi
	mkdir -p "${CAL_DONE%/*}"
	touch "$CAL_DONE"
fi
