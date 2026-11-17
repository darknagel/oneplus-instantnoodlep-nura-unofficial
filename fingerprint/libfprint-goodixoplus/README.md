# libfprint driver `goodixoplus`

Driver for the optical under-display Goodix sensor of the OnePlus 8 Pro
(instantnoodlep, SM8250), reached through the Oplus/Goodix QSEE trusted
application (`gfp9608` for G5, `gfp9638` for G6). Match-on-chip: images and
templates never leave TrustZone. Templates are sealed by the TA and stored
through the machine-wide `qsee-supplicant`.

Files go to `libfprint/drivers/goodixoplus/` in wrobelda's libfprint fork
(branch `goodix-qsee`), plus entries in `meson.build` and `libfprint/meson.build`.
The fork's own `goodixqsee` driver matches the same compatible
(`goodix,gf3626`), so build only this one: `-Ddrivers=goodixoplus`.

## Requirements at runtime

- Kernel: wrobelda's QSEECOM TEE driver, the `goodix_fp_spi` misc driver, and a DT
  `firmware-name` of `gfp96xx`.
- `qsee-supplicant` with the FS, GPFS and **RPMB (0x2000)** listeners
  (`../tools/qsee-supplicant-rpmb-gpfs.patch`, which also removes the 500 KiB GPFS
  length cap). Without RPMB, Gatekeeper cannot store anything and enrollment fails.
- `qsee-app-loader gfp9608` running. The TA must be the squashed single-file `.mbn`,
  because mainline `mdt_loader` cannot parse ELF64.
- fprintd drop-in:

```ini
[Service]
DeviceAllow=/dev/goodix_fp rw
DeviceAllow=char-tee rw
DeviceAllow=char-input r
DeviceAllow=/dev/fb0 rw
ReadWritePaths=/var/lib/goodix-oplus
```

## How it works

- **Open:** powers and resets the sensor, then runs the HAL init chain
  (`1002/9`, `1002/0`, `1002/1`, `1002/2`, `1002/11`, `1001/0`, `1001/20`, `1002/8`,
  `1000/13`). Then it fetches the HMAC key from `keymaster64` (`0x207` SET_VERSION,
  then `0x205`), passes it in with `1000/10`, and sets the active group with
  `1000/0` (path `/data/vendor_de/0/fpdata`).
- **Finger detection:** a touch on the sensor area of the touchscreen, the same
  trigger as the Android HAL. While waiting it draws a blue ring at the sensor; for
  each capture it draws a white disk under the sensor, writing to `/dev/fb0`.
- **Enroll:** `1000/2` returns a challenge, Gatekeeper verify produces a HAT, and
  `1000/3` starts the session. Each touch is `1002/9`, `1001/15`, `1002/3`,
  `1002/101`, `1001/1`, until the remaining count reaches 0. `1000/9` saves the
  template.
- **Identify:** `1000/1`, then up to 4 rounds of `1002/3`, `1002/101`, `1001/2`. A
  match returns the finger id at `+0x30`.
- **List:** `1000/7`. **Delete:** `1000/6` (group at `+0x1c`, finger at `+0x20`).

## Limitations / honesty

- **Gatekeeper token:** the driver enrolls a random machine-local secret
  (`/var/lib/goodix-oplus/gatekeeper`, root-only) with Gatekeeper and verifies it
  to mint the HAT. This is a real Gatekeeper-signed token, but it does not prove
  that the user knew their password.
- **Factory calibration:** `gf_persist.so` and the other persist files written by
  Android fail the TA's HMAC check on mainline. The TA runs with default
  calibration and its own auto-calibration, which works, but quality is likely
  below Android.
- **Display:** the ring and the light disk go straight to `/dev/fb0`. Under a
  compositor (Phosh, Plasma, GDM) this needs compositor or KMS support instead,
  plus panel HBM.
- **Sensor position:** hardcoded for the 1440x3168 panel, as fractions of the panel
  size.
