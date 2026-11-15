# Experimental DisplayPort DSC

Display stream compression (DSC) let the OnePlus 8 Pro send 3840×2160 at
103 Hz and 10 bits per channel to an ASUS PG32UCDMR. The same timing used
8 bits per channel without compression. Lower-resolution compressed modes
and returning to uncompressed output still have failures, so this remains
an experiment.

Kernel patch 0164 carries the driver changes tested in integration r88,
adapted from [JS Deck's Qualcomm-based DSC work](https://github.com/xzn/linux_msm/tree/eca1b90b558433fe1e28d9fa804f6ec466fa28b2).
It adds sink capability checks, DSC resource allocation, picture-parameter
transmission, forward error correction (FEC) and compressed transfer-unit
calculation. The SM8250 adaptation uses DSC 1.1 and exposes the source and
sink DSC/FEC state in `dp_debug`.

## Recorded device results

These checks used the earlier integration r88, before rebasing onto the
current PR stack. They used custom DisplayID timings, DRM vblank timestamps,
source/sink register state and a camera pointed at the physical monitor.
The uncompressed column records clean baseline runs; switching back from
DSC can fail as described below.

| Mode | Uncompressed | DSC |
| --- | --- | --- |
| 3840×2160 at 60 Hz | 10 bpc, visible picture | 10 bpc, zero underruns during the recorded checks |
| 3840×2160 at 103 Hz | 8 bpc, visible picture | 10 bpc, measured 103.00 Hz, zero underruns during the recorded checks |
| 2560×1440 at 231 Hz | 8 bpc, visible picture | Failed to start: no advancing vblank and no active source DSC |
| 1920×1080 at 240 Hz | 10 bpc, visible picture | Underruns continued while vblank advanced |

The 4K 103 Hz run used 15 compressed bits per pixel with DSC and FEC enabled
at both ends. A brief HDR run at the same timing showed a picture with
BT.2020 RGB and PQ metadata and no recorded underruns; HDR picture accuracy
has not been established.

Returning to uncompressed 4K at 60, 97 or 103 Hz after the DSC tests left
the output underrunning even though DSC/FEC reported disabled. A normal
reboot cleared the condition. This transition and the lower-resolution
failures need fixing before enabling the experiment for general use.

## Selection and limits

The `dp_prefer_dsc` module parameter defaults to false. Setting it true
prefers compression for compatible modes at the next DRM modeset. Setting
it false restores normal mode selection; it does not globally disable DSC,
because the mode policy can still select compression when needed.

DSC reduces DisplayPort link bandwidth, but the current two-mixer display
engine still limits the pixel clock to about 876 MHz. The tested 4K 103 Hz
timing uses 875 MHz; 4K 120 Hz remains beyond that limit with these timings.
The everyday test mode used in integration r88 was a separately supplied
4K 100 Hz, 10 bpc timing with DSC off.

The prototype was compiled and run with matching modules in integration
r88. It now sits on top of the reordered DisplayPort stack, after Xi Zhang's
DPU cleanup patches. The first of those clears encoder resource slots that a
mode no longer uses; before it, a mode with fewer DSC blocks kept a stale
second block, which `dpu_encoder_use_dsc_merge()` still counted. That may
explain the lower-resolution failures, but it has not been re-tested.

## Before this can be merged

- Split kernel patch 0164: move the transfer-unit calculation into
  `dp_tu_calc.c` unchanged first, then add the DSC changes, so that the change
  to every uncompressed DP mode can be reviewed.
- The resource manager changes also apply to the phone panel's DSC blocks, and
  `dp_prefer_dsc` does not switch the path off; it needs a real off switch or a
  hardware pass on the phone panel.
- Keep the original authors of the adapted code in the patch, with their
  Signed-off-by or Co-developed-by tags.
- Re-test the lower-resolution modes and the switch back to uncompressed output.
