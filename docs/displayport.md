# DisplayPort integration

Kernel patches 0088–0095 add DP video with USB2 routing, 0096–0099 add the
external VBUS supply and power-role swaps, and 0100–0103 add DP audio; apply
pmaports patches 0045–0047 after 0044, producing kernel package release 78.

The ALSA UCM device is `HDMI` (DisplayPort stereo playback), using MultiMedia8,
`hw:${CardId},7` and `DP0 Jack` at stereo 48 kHz. The existing speaker and microphone
routes remain available.

The phone advertises a conservative 5 V / 500 mA when supplying monitor power.

The external VBUS sequence follows the [vendor board definitions](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8250/blob/oneplus/SM8250_Q_10.0/arch/arm64/boot/dts/vendor/qcom/instantnoodlep.dtsi)
and [power sequencing](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8250/blob/oneplus/SM8250_Q_10.0/drivers/oneplus/power/supply/wlchg/op_wlchg_policy.c).
The CC orientation hold during power-role swaps follows the [vendor charger policy](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8250/blob/oneplus/SM8250_Q_10.0/drivers/power/supply/qcom/smb5-lib.c).

This is experimental: the TCPM power-role-swap callback and QMP/DWC3
coordination API need review. The PHY/VBUS timeout fixes passed one powered-monitor
reconnect in each plug orientation; hardware results and remaining coverage are in
[the original pull request](https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial/pull/5).
