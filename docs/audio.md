# Audio with older stock firmware

On the test IN2023, its stock SLPI firmware restores ADSP startup, and the audio
kernel patches fix false headset detection and codec errors once audio starts.
The firmware service copies SLPI, Venus and CDSP from the active modem partition
into `/lib/firmware/updates/postmarketos`, leaving the original partitions and
packaged firmware unchanged.
Use the [firmware setup instructions](../README.md#video) and reboot; the audio
patches are included by pmaports patch 0030.

Runtime tests used `7.2.0-nura-codec2`: speakers, ordinary USB attachment, codec
runtime suspend/resume, accelerometer streaming, CDSP startup and H.264
encode/decode passed.
The drivers and board tree compile after rebasing onto current main, but that
combined kernel has not been flashed.
Analog USB-C headset playback, microphone/buttons, full system suspend/resume
and CDSP compute workloads remain untested; four SoundWire port-count warnings
remain.

DisplayPort audio uses the UCM profile in pmaports patch 0047; see the
[DisplayPort integration notes](displayport.md).

<details>
<summary>Firmware evidence and test details</summary>

With packaged SLPI, SMEM allocation metadata was damaged immediately after
sensor-feedback item 128; stock SLPI removed that damage and allowed the
unchanged packaged ADSP firmware to start.
This implicates incompatible sensor firmware/shared memory; the offending
instruction was not traced.

| Evidence | Result |
|---|---|
| Stock SLPI, both modem slots | `SLPI.HY.3.0-00234-SM8250AZL-1` |
| SLPI documented for the release image | `SLPI.HY.3.0-00262` |
| Stock ADSP metadata | `ADSP.HT.5.3-00523-SM8250-1` |
| Working SLPI SHA-256 | `a32da1ea48b5e26a349c7d774fac68b4b60046e5f185a02a121441159bfbeece` |
| Preserved OEM log partition `op2` | Successful OxygenOS `IN2023_11.C.16_1160_202204222258` → `IN2023_11.C.33_1330_202207302309` update, followed by merge from slot B |

C.33 is the latest surviving update record, not proof of the final Android
version before Nura overwrote `super`.

ADSP failure before replacing SLPI:

```text
remoteproc remoteproc2: powering up adsp
remoteproc remoteproc2: Booting fw image postmarketos/adsp.mbn, size 15921292
qcom_q6v5_pas 17300000.remoteproc: start timed out
remoteproc remoteproc2: can't start rproc adsp: -110
remoteproc remoteproc2: Boot failed: -110
```

| Runtime check | Result |
|---|---|
| Codec register-read errors / ADC timeouts / impedance errors / unsorted defaults warning | 51 / 8 / 6 / 1 before; all absent after |
| Headphone/microphone status with ordinary USB attached | Both disconnected; no false detection over three codec suspend/resume cycles |
| Physical USB unplug/reconnect | Tested on the first revision; final revision additionally fixes initialization/cleanup |
| Venus H.264 | All 30 decoded frames byte-identical to software decoding, repeated after reboot |
| CDSP | Running with FastRPC devices; no compute workload tested |

</details>
