# DisplayPort over USB-C

Video, audio and the display's USB2 hub work over one cable, with all four
lanes carrying DisplayPort. The phone powers a display at 5 V / 500 mA and
takes power from one that supplies it. VBUS comes from the board's external
boost, not the PMIC's OTG boost.

Audio is the `HDMI` device of its own UCM use case `DisplayPort`, 48 kHz
stereo. It is kept out of `HiFi` because, without a display attached, the
DisplayPort port fails to start and PipeWire would drop the whole profile,
speakers and microphones included.

Tested with a GR14BU (2880×1800 at 100 and 120 Hz, touch, hub), powered by
itself and by the phone, in both plug orientations.

## HDR

The connector has `Colorspace` (`Default`, `BT2020_RGB`) and
`HDR_OUTPUT_METADATA`. Setting them marks the stream as BT.2020 in the VSC SDP
and sends the static metadata infoframe; either change causes a modeset. The
link uses 10 bits per channel whenever the display reports it and the mode
fits. The image has no compositor, so a DRM client has to set these.

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
