# DisplayPort over USB-C

Video, audio and the display's USB2 hub work over one cable, with all four
lanes carrying DisplayPort. The phone powers a display at 5 V / 500 mA and
takes power from one that supplies it. VBUS comes from the board's external
boost, not the PMIC's OTG boost.

Audio is the `HDMI` device of its own UCM use case `DisplayPort`, 48 kHz
stereo. It was kept out of `HiFi` because, without a display attached, the
DisplayPort port failed to start and PipeWire dropped the whole profile,
speakers and microphones included. Opening and preparing the PCM now succeed
with nothing plugged in; see [Audio with no display](#audio-with-no-display).

Tested with a GR14BU (2880×1800 at 100 and 120 Hz, touch, hub), powered by
itself and by the phone, in both plug orientations.

The driver reads each monitor’s link capabilities on hotplug. In a GR14BU
to ASUS PG32UCDMR swap, the ASUS previously inherited the GR14BU’s HBR2
rate and showed visible banding at 3840×2160, 97 Hz and 6 bpc. With the
fix, the ASUS trained at four-lane HBR3 and showed smooth gradients at
the same timing with 10 bpc. Switching back restored four-lane HBR2 on
the GR14BU, and reconnecting the ASUS restored HBR3.

## HDR

The connector has `Colorspace` (`Default`, `BT2020_RGB`) and
`HDR_OUTPUT_METADATA`. Setting them marks the stream as BT.2020 in the VSC SDP
and sends the static metadata infoframe; either change causes a modeset.
Metadata whose EOTF the display does not list in its EDID is refused. The
link uses 10 bits per channel whenever the display reports it and the mode
fits; there is no `max bpc` property yet, so HDR is not refused when the link
can only carry 8 or 6 bits. The image has no compositor, so a DRM client has
to set these.

The SM8250 controller (revision 1.2.0.3) latches these packets through
`SDP_CFG3` (kernel 0141). When that was measured, the driver asked the display
engine for a peripheral flush only for YUV 4:2:0, never with these packets. It
now does (kernel 0159); whether the flush alone puts them on the link has not
been measured.

## System sleep

The DP PHY does not keep its registers while the controller is powered down
for system sleep: right after resume `PD_CTL` reads 0x78 and `AUX_CFG1` and
`AUX_CFG2` read 0x00 and 0x04, where 0x67, 0x13 and 0xa4 were programmed. The
controller therefore exits the PHY when it suspends, and the next detect or
enable sets it up again.

A link that failed to train has no link clock. Its registers must not be
written when the output is switched off; that write resets the phone.

HPD on this phone comes from the USB-C connector, so nothing but the plugged
state keeps the DP controller powered. `detect()` used to take a runtime PM
reference on every probe and keep it, and the HPD plug handler took one on
every plug event, which held the controller and the display core power domain
on after the display was unplugged. Kernel 0157 and 0158 keep one reference
per plugged state.

Suspending while DisplayPort audio plays still breaks the stream: after resume
it stalls, and closing it times out in the DSP until a reboot. The AFE port
stays started while the DP controller is powered down, with and without the
change in [Audio with no display](#audio-with-no-display).

## Audio with no display

PipeWire and PulseAudio open and prepare every PCM of the card to probe it,
also with nothing plugged into USB-C. Starting the DSP's DisplayPort port
(AFE port 0x6020) without a stream on the link takes q6afe's whole command
timeout, so every probe used to wait for it.

- The q6afe DAI configures the DisplayPort port in prepare and starts it from
  the back-end trigger, when the stream starts. Probing still opens the stream
  on the DSP but no longer starts the port.
- The SM8250 machine driver runs the back-end triggers of playback front ends
  before the front end. The DSP needs the port running before the ASM stream
  that feeds it starts: started after it, with a 20 ms buffer, every port start
  timed out. The q6afe change relies on this order, which only this machine
  driver sets.
- The machine driver refuses the DisplayPort start with `-ENODEV` while the DP
  jack reports no display. The DP driver reports the jack while a stream runs
  on the link, so a refused start never reaches the AFE either, and a display
  that is switched off counts as no display.
- Opening and preparing the PCM succeed with nothing plugged in, so the profile
  stays available.

`tests/displayport/test-audio-start.py` checks the start order against the
patched source.

## Pixel-rate limits

- Link: four HBR3 lanes carry 864 MHz at 10 bits per channel, 1080 MHz at 8.
- Display engine: about 876 MHz, from two mixers at the 460 MHz core clock less
  the driver's 5 % margin. No topology has more than two mixers per display,
  and DSC would not raise this.
- The DP driver's 675 MHz cap applies after wide bus halves the clock, so it
  allows 1350 MHz.

That is 3840×2160 at about 100 Hz. Displays rarely list modes in that range, so
the DRM client has to supply one.

## Variable refresh

Not implemented, but the timing engine can stretch frames on this output.
`INTF_AVR_VTOTAL` (0x27c) of INTF_0 takes the longest frame in the units of
`INTF_VSYNC_PERIOD_F0`; `INTF_AVR_CONTROL` (0x270) bit 0 with `INTF_AVR_MODE`
(0x274) at 0 enables it after an interface flush. Frames then last exactly the
programmed length, and a display follows without `MSA_TIMING_PAR_IGNORE_EN`.

The limit has to be programmed before enabling, or the frame never ends. How
`INTF_AVR_TRIGGER` (0x278) ends a frame early is not worked out.
