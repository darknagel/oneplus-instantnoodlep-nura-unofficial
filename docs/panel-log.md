# Another display panel

Tested on a single device with the **Samsung AMS678UW01** display panel (the panel driver is
written for exactly this panel; Android reports it as `oppo19811_samsung_1440_3168_dsc_cmd`).
If your phone has a different panel, the screen may stay black – the phone is then still
reachable over USB/SSH. Please open an issue with your panel name and a log if that happens.
To create the log, connect the phone over USB (see "First login" in the README) and run these two commands
on your PC (they work the same in PowerShell and in a Linux terminal):

```sh
ssh root@172.16.42.1 "{ echo '== panel'; tr ' ' '\n' < /proc/cmdline | grep dsi_display; echo '== kernel log'; dmesg; echo '== warnings this boot'; journalctl -b -p warning --no-pager; } | sed 's/serialno=[^ ]*/serialno=REMOVED/g' > /root/panel-log.txt"
scp root@172.16.42.1:/root/panel-log.txt .
```

`172.16.42.1` is the phone's address over USB. If the phone is on your Wi-Fi, you can use its
Wi-Fi address instead (shown by `ip -4 addr show wlan0` on the phone, or in your router).
Then attach `panel-log.txt` to the issue.

The `sed` removes the device serial number that the bootloader passes on the kernel command
line. Look through the file before you upload it.
