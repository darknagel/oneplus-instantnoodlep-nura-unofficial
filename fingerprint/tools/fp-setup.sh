#!/bin/sh
# Bring up the Goodix G5 TA on mainline: hold device, supplicant (FS/GPFS/RPMB),
# load TA, init chain (as Android HAL), keymaster HMAC key, active group.
umask 077
export NOPOWER=1
systemctl stop fp-auth fp-enroll fp-loader fp-suppl fp-hold 2>/dev/null
systemctl reset-failed fp-auth fp-enroll fp-loader fp-suppl fp-hold 2>/dev/null
mount | grep -q debugfs || mount -t debugfs none /sys/kernel/debug
systemd-run -u fp-hold python3 /root/fp/hold.py >/dev/null; sleep 1
systemd-run -u fp-suppl /root/fp/qsee-supplicant-rpmb --state-dir /var/lib/qsee-fptest >/dev/null; sleep 2
systemd-run -u fp-loader /root/fp/qsee-app-loader gfp9608 >/dev/null; sleep 5
r() { printf "%-11s " "$*"; timeout 30 /root/fp/optest "$@" 8 | grep -o "result@0xc = [0-9]*"; }
for c in "1002 9 32" "1002 0 28" "1002 1 44" "1002 2 272" "1002 11 32" "1001 0 40" "1001 20 40" "1002 8 28" "1000 13 28"; do r $c; done
/root/fp/rawcmd keymaster64 16 0x207 4 5 4 5 0 >/dev/null
OUT=/root/fp/km-rsp.bin /root/fp/rawcmd keymaster64 256 0x205 2 >/dev/null
python3 -c "
a=open('/root/fp/km-rsp.bin','rb').read(); p=bytearray(284); p[0x20:0xc0]=a[4:0xa4]; open('/root/fp/km-live.bin','wb').write(p)
g=bytearray(288); s=b'/data/vendor_de/0/fpdata'; g[0x20:0x20+len(s)]=s; open('/root/fp/setgroup.bin','wb').write(g)"
printf "%-11s " "1000 10 km"; PAYLOAD=/root/fp/km-live.bin /root/fp/optest 1000 10 284 8 | grep -o "result@0xc = [0-9]*"
printf "%-11s " "1000 0 grp"; PAYLOAD=/root/fp/setgroup.bin /root/fp/optest 1000 0 288 8 | grep -o "result@0xc = [0-9]*"
