# Audio and the phone's own DSP firmware

The packaged SLPI firmware does not suit every phone. On an IN2023 whose stock
SLPI is `SLPI.HY.3.0-00234-SM8250AZL-1`, the packaged one damaged the shared
memory allocation table after sensor-feedback item 128, the ADSP then timed out
at start, and there was no audio. With the phone's own SLPI the unchanged
packaged ADSP firmware starts.

The boot service in `firmware/` therefore copies SLPI, Venus and CDSP from the
active modem partition into `/lib/firmware/updates/postmarketos`; the
partitions and the packaged firmware stay as they are.

Analog USB-C headsets and CDSP compute workloads are untested.
