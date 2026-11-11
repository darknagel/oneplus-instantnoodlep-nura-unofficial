# DisplayPort integration

Kernel patches 0088–0095 add DP video with USB2 routing; apply pmaports patch
0045 after 0044, producing kernel package release 76. The phone does not supply
VBUS at this stage, so the display has to power itself.

This is experimental: the QMP/DWC3 coordination API needs review. The PHY
timeout fixes passed one powered-monitor reconnect in each plug orientation;
hardware results and remaining coverage are in
[the original pull request](https://github.com/darknagel/oneplus-instantnoodlep-nura-unofficial/pull/5).
