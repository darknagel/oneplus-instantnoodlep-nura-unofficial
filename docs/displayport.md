# DisplayPort over USB-C

Video, audio and the display's USB2 hub work over one cable, with all four
lanes carrying DisplayPort. The phone powers a display at 5 V / 500 mA and
takes power from one that supplies it. VBUS comes from the board's external
boost, not the PMIC's OTG boost.

Audio is the `HDMI` UCM device, 48 kHz stereo.

Tested with a GR14BU (2880×1800 at 100 and 120 Hz, touch, hub), powered by
itself and by the phone, in both plug orientations.
