#!/bin/sh
# Set up the SDX55 modem of the OnePlus 8 Pro (oneplus-instantnoodlep).
# Run once as root on the phone, from the directory that holds these files.
# Needs the modem kernel (pmaports patch 0018) and python3.
#
# Everything proprietary or device specific comes from this phone's own
# partitions and stays on the phone:
#  - the modem firmware from the modem_a partition. It must be the same
#    version as the RF configuration the modem reads from modem_a at run
#    time; a different firmware version (e.g. firmware-oneplus-instantnoodlep-
#    modem) leaves the RF unconfigured and the modem stays offline.
#  - the modem's file system (EFS), the OnePlus NV backup and the DDR
#    training data from mdm1m9kefs1/2, mdm1oemnvbktmp and mdmddr.
set -e
cd "$(dirname "$0")"
FW=/lib/firmware/postmarketos/qcom/sdx55m
MNT=/run/sdx55-modem_a
P=/dev/disk/by-partlabel

command -v python3 >/dev/null || apk add python3

mkdir -p $FW $MNT
mountpoint -q $MNT || mount -o ro $P/modem_a $MNT
for f in $MNT/image/sdx55m/*; do
	case ${f##*/} in efs*|mdmddr.mbn) continue ;; esac
	install -m 600 "$f" $FW/
done

# Sahara image 16/17: the modem's EFS, 20: the OnePlus NV backup (not the
# mostly empty mdm1m9kefs3), 34: DDR training data. Existing copies are kept,
# they may hold newer EFS syncs.
[ -e $FW/efs1.bin ] || dd if=$P/mdm1m9kefs1 of=$FW/efs1.bin status=none
[ -e $FW/efs2.bin ] || dd if=$P/mdm1m9kefs2 of=$FW/efs2.bin status=none
[ -e $FW/efs3.bin ] || dd if=$P/mdm1oemnvbktmp of=$FW/efs3.bin status=none
[ -e $FW/mdmddr.mbn ] || dd if=$P/mdmddr of=$FW/mdmddr.mbn status=none
chmod 600 $FW/*

install -m 755 rfsd.py /usr/local/bin/sdx55-rfsd
install -m 755 efssave.py /usr/local/bin/sdx55-efssave
install -m 755 sdx55-gnss.py /usr/local/bin/sdx55-gnss
install -m 755 modemstate.py /usr/local/bin/sdx55-modemstate
mkdir -p /var/lib/sdx55-rfs/efs /etc/udev/rules.d
chmod 700 /var/lib/sdx55-rfs/efs

cat > /etc/systemd/system/sdx55-rfsd.service <<'UNIT'
[Unit]
Description=SDX55 remote file system (TFTP over QRTR, instance 3)
Before=ModemManager.service

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/sdx55-rfsd 3
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/sdx55-gnss.service <<'UNIT'
[Unit]
Description=SDX55 GNSS: NMEA on /dev/gnss-sdx55
After=sdx55-rfsd.service

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/sdx55-gnss
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

# The modem syncs its EFS through Sahara memory debug; the kernel hands each
# sync over as a devcoredump. Without an answer the modem resets itself.
echo 'SUBSYSTEM=="devcoredump", ACTION=="add", RUN+="/usr/bin/python3 /usr/local/bin/sdx55-efssave %k"' \
	> /etc/udev/rules.d/79-sdx55-efssave.rules
install -m 644 78-mm-sdx55-qrtr.rules /etc/udev/rules.d/

systemctl disable --now tqftpserv 2>/dev/null || true
systemctl daemon-reload
udevadm control --reload
systemctl enable sdx55-rfsd sdx55-gnss
echo "Done. Reboot to start the modem."
