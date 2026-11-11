# Charging

Kernel patches 0082–0087 make the PM8150B charger follow USB-C limits; apply
pmaports patch 0044 after 0043, producing kernel package release 75.

Kernel patch 0085 starts a fresh charger-detection cycle after cable changes or PD,
keeps empty results Unknown, and handles late completion through bounded
polling and the source-change interrupt.
It also honors the battery current from the device tree; patch 0087 names the
Type-C port as the charger's supplier and sets this
board to the stock normal 2 A ceiling while retaining the 4.35 V battery ceiling
(kernel patch 0068) and 5 V USB input policy.

Short bench tests on one IN2023 on 2026-11-10, with the same USB-A charger
and cable that previously appeared as SDP:

| Connection | Detection / contract | Measured input | Measured battery charging |
|---|---|---|---|
| Computer through USB-A hub | SDP, 500 mA limit | 0.49 A | Discharging under the phone's load |
| Standalone USB-A charger | DCP, 1.5 A limit | 1.48 A | About 1.1 A, stable for 98 seconds |
| USB-C PD charger | 5 V / 3 A | About 2.49 A | 1.99 A, stable after settling |
| Same USB-A charger after PD | Fresh DCP result, 1.5 A limit | 1.48 A | About 1.1 A, stable after settling |

The PD source advertised 5, 9, 15 and 20 V, and the phone selected 5 V.
These measurements used the tested integration kernel with the phone's
existing sensor overrides and separate DSI fixes; the rebased package series,
other charger models and long-duration charging have not been tested on hardware.

Run the charger regression test against a kernel with this patch series applied:

```sh
python3 tests/displayport/test-policy.py /path/to/kernel
```
