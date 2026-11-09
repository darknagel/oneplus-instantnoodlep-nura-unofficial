# Forwarded QRTR client deletions

Kernel patch 0064 fixes `failed while handling packet from 2:-2` on the
tested IN2023 by accepting legitimate forwarded `DEL_CLIENT` notifications.
The modem sends them from node 2 about clients on node 3, but the name service
previously required the sender and client node IDs to match and returned
`-EINVAL` (`-22`).

Both nodes resolve to the same MHI transport endpoint. The patch permits
forwarding only from the QRTR control port, between remote nodes with known
routes through the same endpoint; remote senders cannot remove local clients
or clients on another endpoint, and local clients can remove only their own
port. The displayed `-2` is the control port `4294967294` printed as signed.

## Before and after

| Measurement | Before | After |
|---|---:|---:|
| Kernel | `7.2.0-nura-ois1` | `7.2.0-nura-qrtr1` |
| Capture duration | 90 s | 90 s |
| Forwarded notifications from node 2 about node 3 | 1,122 | 1,122 |
| Handler return code for those notifications | `-22` | `0` |
| Rate-limited packet warnings | 100 | 0 |
| Local client deletions, all returning `0` | 1,164 | 1,166 |

The [before](qrtr-capture/before.csv) and [after](qrtr-capture/after.csv) CSVs
contain every captured `DEL_CLIENT` result, including timestamps, sender and
client node/port IDs, and return codes. [Trace excerpts](qrtr-capture/trace-excerpts.txt)
also identify `qcom_mhi_qrtr_send` as the incoming transport.

Kprobes recorded the incoming packets, route assignments and the name-service
handler result during startup; the inlined handler required offsets verified
against each build's disassembly. Neither capture overwrote its trace buffer,
and the probes reported no missed hits. A second boot without tracing had no
packet warnings through 114.9 seconds, beyond the original 10–64 second window.

## Regression checks

All ten [QRTR_TUN tests](qrtr-capture/regression.py) passed using isolated virtual
endpoints: forwarding with both v1 and v2 headers, ordinary remote deletion,
normal local socket closure, and six invalid sender/target combinations.
The invalid cases cover cross-endpoint deletion, a remote sender targeting a
local client, a local sender targeting another local port or a remote client,
forwarding from a non-control port, and forwarding for an unmapped node.
They still returned `-EINVAL`; the tests verified that registered targets
remained and that local servers received no false deletion notification.

The [test results](qrtr-capture/regression-results.json) and
[captured rejection codes](qrtr-capture/regression-rejections.json) are included.
The test script requires root and `CONFIG_QRTR_TUN`; load `qrtr_tun` before
running it, and use `--baseline` when testing the original rejection behavior.

Runtime captures used the kernel series through 0060, with only this QRTR
change added for the after capture. The PR is based on newer main containing
0061–0063; those sensor/OIS changes were not part of the runtime comparison.
The full updated series applies, and the QRTR code compiles against it.
Accelerometer readings, DSP startup and silent PCM playback also passed on
the tested kernel; OIS remained disabled.

## Packaging

Pmaports patch 0032 includes kernel patch 0064 and bumps the package to r63.
It also refreshes 34 stale checksums for earlier packaged patch files left by
0031, using the actual files produced by the pmaports patch series.
The [machine-readable capture summary](qrtr-capture/summary.json) records the
packet counts, timing and clean-boot checks.
