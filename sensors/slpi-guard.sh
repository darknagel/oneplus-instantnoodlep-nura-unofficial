#!/bin/sh
# Stop the sensor DSP (SLPI) when it keeps crashing. The kernel restarts it
# after every crash, and hundreds of restarts end in RPMh timeouts that break
# most of the phone. After MAX crashes within WINDOW seconds, recovery is
# switched off and the SLPI stays down: no sensors, but the rest keeps working.
MAX=3
WINDOW=60

rp=
for r in /sys/class/remoteproc/remoteproc*; do
	[ "$(cat "$r/name" 2>/dev/null)" = slpi ] && rp=$r
done
[ -n "$rp" ] || { echo "no slpi remoteproc"; exit 0; }

n=0
first=0
# The whole boot's kernel log, so crashes before this service started count too
journalctl -k -b -f -o short-unix | while read -r ts rest; do
	case "$rest" in
	*"crash detected in slpi"*) ;;
	*) continue ;;
	esac
	t=${ts%%.*}
	if [ $((t - first)) -gt $WINDOW ]; then
		n=0
		first=$t
	fi
	n=$((n + 1))
	if [ $n -ge $MAX ]; then
		echo disabled > "$rp/recovery"
		echo stop > "$rp/state" 2>/dev/null
		echo "slpi crashed $n times within ${WINDOW}s, stopped it (sensors are off until reboot)"
		# End the whole script, journalctl -f would keep it running
		kill $$
	fi
done
