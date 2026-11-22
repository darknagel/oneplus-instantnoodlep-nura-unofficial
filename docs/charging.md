# Charging

The charger takes its input limit from the USB-C port: the PD contract or the
Type-C current where there is one, otherwise USB-A detection (500 mA from a
computer port, 1.5 A from a charger). The input stays at 5 V; from a PD source
the phone requests up to 3 A. If the USB-C stack loses track of a source that
still supplies power, the input stays at 500 mA instead of being cut off. If
USB-C does not attach at all while a charger supplies power, for example with a
USB-A cable that pulls up both CC pins, USB-A detection runs after two seconds.

The battery is charged the way the stock firmware does it, with the limits of
the stock device tree. The bq27411 fuel gauge at the cell decides, the PM8150B
only supplies. Every 5 seconds the driver reads the cell voltage, current and
temperature:

| Battery temperature | Charge current | Charger voltage |
| --- | --- | --- |
| below −2 °C | no charging | |
| −2 to 0 °C | 0.3 A | 3.98 V |
| 0 to 5 °C | 1.2 A | 4.43 V |
| 5 to 45 °C | 2 A | 4.43 V |
| 45 to 50 °C | 1.1 A | 4.13 V |
| above 50 °C | no charging | |

The charger voltage is above the level at which the cell is full, because the
PM8150B measures the battery behind the charge path. Between 0 and 45 °C the
battery counts as full when one of these holds:

- the fuel gauge reports it full
- the cell is above 4.385 V with less than 230 mA flowing
- the cell rests above 4.35 V with no current

Charging then stops and starts again when the cell has dropped below 4.235 V.

Limits that do not depend on the above:

- Charging stops at once if the cell reaches 4.46 V.
- Without valid data from the fuel gauge only 3.98 V and 0.5 A are allowed,
  also from boot until the first reading.
- The charger watchdog is on. If the kernel stops looking after the battery,
  the PM8150B stops charging.
- The phone does not sleep while the battery is being charged: a suspend
  attempt fails and the kernel logs `battery is charging, not suspending`.
  Once the battery is full it sleeps as usual.

The PM8150B ends a charge cycle on its own analog current sense. Its default,
the ADC comparison, needs the battery current from the PM8150B's own fuel gauge,
which mainline does not drive; with it the charger ended every cycle a few
seconds into constant voltage and the last ten percent took about 50 minutes.
Now the charger stays in constant voltage until the driver decides the battery
is full: from a computer port it charged from 95 % to full in 54 minutes, 39 of
them at constant voltage without a break.

```sh
cat /sys/class/power_supply/pm8150b-charger/status   # Charging / Full / Not charging
dmesg | grep pm8150b-charger                          # temperature zone, full, recharging
```
