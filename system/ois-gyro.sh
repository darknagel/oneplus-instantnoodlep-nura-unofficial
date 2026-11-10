#!/bin/sh
# The OIS controller of the main camera reads the gyroscope directly, but the
# gyroscope only runs while the sensor DSP streams it. Android's camera keeps
# a gyroscope stream open while the camera runs; do the same here, so that
# stabilisation does not work from zero readings and let the lens drift.
OIS=/sys/bus/i2c/devices/20-0024/power/runtime_status
pid=

stop() {
	[ -n "$pid" ] && kill "$pid" 2>/dev/null
	pid=
}
trap 'stop; exit 0' INT TERM

while :; do
	if [ "$(cat "$OIS" 2>/dev/null)" = active ]; then
		if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
			ssccli --sensor gyroscope --timeout 86400 >/dev/null 2>&1 &
			pid=$!
		fi
	else
		stop
	fi
	sleep 0.5
done
