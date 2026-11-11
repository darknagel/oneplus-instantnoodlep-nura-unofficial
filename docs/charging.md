# Charging

The charger takes its input limit from the USB-C port: the PD contract or the
Type-C current where there is one, otherwise USB-A detection (500 mA from a
computer port, 1.5 A from a charger). The input stays at 5 V; from a PD source
the phone requests up to 3 A. The battery charges at up to 2 A and stops at
4.35 V.
