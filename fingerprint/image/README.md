# Fingerprint sensor

The OnePlus 8 Pro has an optical Goodix sensor under the display. Images and
templates never leave TrustZone: a Goodix trusted application (TA) in QSEE does
the imaging, enrollment and matching. Linux reaches it through:

- the kernel's QSEECOM TEE driver and the Goodix misc driver (power, reset, IRQ),
  from Dawid Wróbel's work (kernel patches 0174 to 0221), plus the device-tree
  node (0222);
- `qsee-supplicant`, which stores the TA's sealed files and serves the RPMB
  partition (Gatekeeper needs it), and `qsee-app-loader@gfp9608`, which keeps the
  TA loaded;
- `fprintd` with a libfprint build that contains the `goodixoplus` driver.

## The trusted application

The TA is proprietary OnePlus/Goodix firmware and is **not** part of the image.

**Automatic (default):** at boot, `oneplus-ota-fetch.service` downloads it once the
phone has internet, together with the sensor DSP configuration (see
`firmware/oneplus-ota-fetch`). It takes only the parts of OnePlus' official
OxygenOS 13 full OTA on Google's OTA server that hold these files (about 40 MB of
4.4 GB), with HTTP range requests. Every chunk is checked against the OTA
manifest, and every file and the TA against fixed hashes. Then it installs
`/lib/firmware/gfp9608.mbn` and starts the loader. If there is no network yet, it
tries again every 10 minutes. Progress:

```sh
journalctl -u oneplus-ota-fetch
```

**By hand (no internet, or your own Android files):** Android keeps the TA on the
`odm` partition, which the installation replaced, so it has to come from your own
phone, e.g. from a backup made under Android:

```sh
# under Android (root): copy the files from the phone
adb shell su -c 'tar -C /odm/vendor/firmware -cf - gfp9608.mdt $(cd /odm/vendor/firmware && ls gfp9608.b*)' > gfp9608.tar
```

Copy `gfp9608.tar` to the phone running postmarketOS, unpack it into a folder and
install it:

```sh
mkdir ta && tar -C ta -xf gfp9608.tar
sudo fingerprint-ta-install ta
```

The script joins the split image into `/lib/firmware/gfp9608.mbn` and starts the
loader. After that, set up a finger:

```sh
fprintd-enroll -f right-thumb
fprintd-verify
```

Place the finger on the blue ring at the bottom of the screen. The screen lights
up under the finger while it captures.

## Limits

- Only the G5 sensor variant (TA `gfp9608`) has been tested. Units with the G6
  sensor (`gfp9638`) need a different `firmware-name` and are untested.
- The driver draws the ring and the light on the framebuffer, which only the
  text console shows. Under Plasma Mobile, `goodix-fp-overlay` (see below) draws
  them instead; Phosh has no such helper yet.
- Enrollment uses a Gatekeeper token made from a random machine secret
  (`/var/lib/goodix-oplus/gatekeeper`), not from your password.
- The factory calibration that Android wrote does not pass the TA's integrity
  check on Linux. The TA works with its own calibration instead.

## Plasma Mobile

Package `goodix-fp-overlay` (source in [`../overlay`](../overlay) and
[`../pam`](../pam)) adds:

- `goodix-fp-overlay`, started with the session: a transparent, input-transparent
  window on the layer-shell overlay layer. It follows fprintd's `finger-needed`
  and `finger-present` properties and draws the blue ring, then the white disk
  under the finger. It stays mapped and marks its surface with KWin's
  `kde_lockscreen_overlay_v1`, so it also shows over the lock screen. KWin only
  accepts that mark for a surface that has a window but no buffer yet, i.e.
  right after `show()`.
- `/etc/pam.d/fingerprint-auth` and `/etc/pam.d/postlogin`. Alpine's
  `kscreenlocker` installs `/etc/pam.d/kde-fingerprint`, which includes these
  two Fedora files, but nothing provides them, so fingerprint unlock always
  failed.

Adding fingers in Settings → Users needs the user's password (fprintd's polkit
rule `auth_self_keep`), the same as on Android.
