# Using the phone as a small server

All commands run as root on the phone.

**How do I turn the screen off?**

```sh
echo 1 > /sys/class/graphics/fb0/blank     # off
echo 0 > /sys/class/graphics/fb0/blank     # on again
```

This does not survive a reboot: the screen comes back on at every start, so run the command
again after each reboot (for example over SSH).

**Can charging stop at 80 % when the phone is always plugged in?**

There is no ready-made charge limit for this charger yet (no `charge_control_end_threshold`).
The PMIC charger can be switched off, though, so a small service can stop charging at 80 %
and resume at 75 %:

```sh
cat > /usr/local/bin/charge-limit <<'EOF'
#!/bin/sh
# Stop charging at STOP %, resume at START %.
STOP=80; START=75
CAP=/sys/class/power_supply/bq27411-0/capacity
EN=/sys/class/power_supply/pm8150b-charger/charging_enabled
while true; do
    c=$(cat $CAP)
    if [ "$c" -ge "$STOP" ]; then echo 0 > $EN
    elif [ "$c" -le "$START" ]; then echo 1 > $EN
    fi
    sleep 60
done
EOF
chmod +x /usr/local/bin/charge-limit

cat > /etc/systemd/system/charge-limit.service <<'EOF'
[Unit]
Description=Keep the battery between 75 and 80 percent

[Service]
ExecStart=/usr/local/bin/charge-limit
ExecStopPost=/bin/sh -c 'echo 1 > /sys/class/power_supply/pm8150b-charger/charging_enabled'
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now charge-limit
```

This is **experimental**: with charging switched off the charger reports "Not charging", but
the fuel gauge still measured about 50 mA flowing into the battery, so the level may creep
above 80 % slowly. Check it after a day with
`cat /sys/class/power_supply/bq27411-0/capacity`. To undo:
`systemctl disable --now charge-limit`.

**Will the phone go to sleep?**

Not with the console image. If you installed a desktop, switch suspend off:
`systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`

**SSH over Wi-Fi drops out or is slow to respond.**

Switch off Wi-Fi power saving for your network (name as shown by `nmcli connection`):

```sh
nmcli connection modify "YOUR-WIFI" 802-11-wireless.powersave 2
nmcli connection up "YOUR-WIFI"
```

**How do I find the phone's address in my network?**

`ip -4 addr show wlan0` on the phone, or look it up in your router. For a fixed address, set
it in the router (DHCP reservation) – that is easier than a static IP on the phone.

**How do I check battery and temperature?**

```sh
cat /sys/class/power_supply/bq27411-0/capacity   # battery in %
cat /sys/class/power_supply/bq27411-0/status     # Charging / Discharging
cat /sys/class/power_supply/bq27411-0/temp       # battery temperature in 0.1 °C
cat /sys/class/thermal/thermal_zone*/temp        # SoC sensors in m°C
```

**Name resolution (DNS) does not work.**

The image switches DNSSEC off (`/etc/systemd/resolved.conf.d/10-dnssec-off.conf`), because
many home routers break DNSSEC validation. If `apk update` still reports DNS errors right
after connecting to Wi-Fi, wait a minute or run `resolvectl flush-caches`.
