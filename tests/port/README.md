These fixtures test the changed kernel helpers without phone hardware.

```sh
python3 tests/port/test-kernel-helpers.py /path/to/patched-linux
python3 tests/port/test-dsi-power.py /path/to/patched-linux /path/to/build/drivers/gpu/drm/msm/generated
```

On the Nura systemd image, run `sudo sh system/setup-networkmanager.sh` once to install the generator's Bash dependency and enable dispatcher D-Bus activation.
This does not restart networking.
