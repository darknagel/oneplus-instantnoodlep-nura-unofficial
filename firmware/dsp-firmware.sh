#!/bin/sh
# Copy the video codec (Venus) and compute DSP (CDSP) firmware from this
# phone's own modem_a partition. Runs at boot before udev loads the drivers
# (dsp-firmware.service) and does nothing once the copies exist.
#
# Android keeps both split into .mdt/.bNN files; the kernel wants one .mbn,
# which pil-squasher puts together. The files are signed for this phone and
# OnePlus does not allow passing them on, so they are not in the image.
FW=${DSP_FW:-/lib/firmware/postmarketos}
[ -e $FW/venus.mbn ] && [ -e $FW/cdsp.mbn ] && exit 0

# /dev/disk/by-partlabel does not exist yet this early
part() {
	for u in /sys/class/block/*/uevent; do
		grep -qx "PARTNAME=$1" "$u" && echo /dev/$(sed -n 's/^DEVNAME=//p' "$u") && return
	done
	return 1
}

set -e
mkdir -p $FW
MNT=$(mktemp -d)
mount -o ro "$(part modem_a)" $MNT
trap 'umount $MNT; rmdir $MNT' EXIT
for fw in venus cdsp; do
	[ -e $FW/$fw.mbn ] && continue
	pil-squasher $FW/$fw.mbn.tmp $MNT/image/$fw.mdt
	mv $FW/$fw.mbn.tmp $FW/$fw.mbn
done
echo "dsp-firmware: copied the Venus and CDSP firmware from this phone"
