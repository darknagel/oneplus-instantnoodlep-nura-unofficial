#!/usr/bin/env python3
"""Exercise DP mux transactions from a kernel checkout with stubbed hardware.

The transaction, mux traversal, Attention and VDM/worker handlers are extracted
from the checkout. Only hardware operations and status-parser inputs are stubbed.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} KERNEL_CHECKOUT")
root = Path(sys.argv[1]).resolve()
variant = 'fixed' if 'static void dp_altmode_restore(' in (
    root / 'drivers/usb/typec/altmodes/displayport.c').read_text() else 'original'

def extract(file, name):
    source = (root / file).read_text()
    match = re.search(r'^.*\b' + re.escape(name) + r'\(', source, re.M)
    assert match, name
    start = source.rfind('\n\n', 0, match.start()) + 2
    begin = source.index('{', match.end())
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define guard(x) lock_stub
#define WRITE_ONCE(a,b) ((a)=(b))
#define TYPEC_STATE_SAFE 0
#define TYPEC_STATE_USB 1
#define TYPEC_DP_STATE_C 4
#define TYPEC_DP_STATE_D 5
#define TYPEC_DP_STATE_E 6
#define TYPEC_DP_STATE_F 7
#define TYPEC_MODAL_STATE(x) ((x)+2)
#define DP_CONF_GET_PIN_ASSIGN(x) (((x)>>8)&0xff)
#define CONF_C ((1u<<2)<<8)
#define CONF_D ((1u<<3)<<8)
#define USB_TYPEC_DP_SID 0xff01
#define DP_PHY_PD_CTL_PSR_PWRDN 0
#define QSERDES_DP_PHY_PD_CTL 0
#define DP_HEADER(...) 0
#define DP_CMD_CONFIGURE 0
#define CMD_ENTER_MODE 1
#define CMD_EXIT_MODE 2
#define DP_CMD_STATUS_UPDATE 3
#define CMDT_RSP_ACK 1
#define CMDT_RSP_NAK 2
#define PD_VDO_CMDT(h) ((h)>>8)
#define PD_VDO_CMD(h) ((h)&0xff)
#define connector_status_disconnected 0
#define TYPEC_PLUG_SOP_P 0
#define IS_ERR_OR_NULL(x) (!(x))
#define dev_dbg(...) do {} while (0)
#define dev_warn(...) do {} while (0)
#define dev_err(dev,fmt,...) record_error(fmt)
static int errors, restore_errors, configure_vdms, cable_vdms, enter_vdms, exit_vdms, hardware_changes;
static int dropped_cables;
static u32 last_configure;
static int fail_restore, configure_error;
static void record_error(const char *fmt) {
    errors++;
    if (strstr(fmt,"restore connector")) restore_errors++;
}
static void lock_stub(int *p) {}
static unsigned get_count_order(unsigned v) {
    unsigned n=0;
    while ((1u<<n)<v) n++;
    return n;
}
struct device { struct device *parent; bool is_port; int kobj; };
struct typec_altmode;
struct typec_altmode_ops {
    int (*notify)(struct typec_altmode *, unsigned long, void *);
    int (*enter)(struct typec_altmode *, u32 *);
    int (*exit)(struct typec_altmode *);
};
struct typec_altmode {
    struct device dev;
    int svid;
    bool active;
    const struct typec_altmode_ops *ops;
    void *drvdata;
};
struct typec_mux_state { struct typec_altmode *alt; unsigned long mode; void *data; };
struct typec_mux_dev { void *data; int (*set)(struct typec_mux_dev *, struct typec_mux_state *); };
struct typec_mux { struct typec_mux_dev *mux_devs[3]; unsigned num_mux_devs; };
struct altmode {
    struct typec_altmode adev;
    struct typec_mux *mux;
    void *retimer;
    struct altmode *partner;
};
#define to_altmode(x) ((struct altmode *)((char *)(x)-offsetof(struct altmode,adev)))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static bool is_typec_port(struct device *d) { return d && d->is_port; }
struct typec_retimer_state { struct typec_altmode *alt; unsigned long mode; void *data; };
static int typec_retimer_set(void *r, struct typec_retimer_state *s) { return 0; }
static void *typec_mux_get_drvdata(struct typec_mux_dev *m) { return m->data; }
struct dwc3_qcom {
    bool dp_active, dp_only, utmi_pipe_clk, ignore_pipe_clk, pm_suspended;
    int pipe_clk_lock;
    void *dev; void *reconfig_phy;
};
static int dwc3_qcom_phy_prepare_locked(struct dwc3_qcom *q) { return 0; }
static void dwc3_qcom_phy_complete_locked(struct dwc3_qcom *q) {}
static int pm_runtime_resume_and_get(void *p) { return 0; }
static void pm_runtime_put_autosuspend(void *p) {}
static void dwc3_qcom_select_utmi_clk(struct dwc3_qcom *q, bool utmi) {
    q->utmi_pipe_clk=utmi;
}
enum qmpphy_mode { QMPPHY_MODE_USB3DP, QMPPHY_MODE_DP_ONLY, QMPPHY_MODE_USB3_ONLY, QMPPHY_MODE_SAFE };
struct qmp_combo;
struct qmp_phy_cfg { void (*dp_aux_init)(struct qmp_combo *); };
struct qmp_combo {
    const struct qmp_phy_cfg *cfg;
    enum qmpphy_mode qmpphy_mode;
    int phy_mutex, init_count, usb_init_count, dp_init_count;
    bool dp_powered_on;
    void *dev, *usb_phy;
    char *dp_dp_phy;
};
static void writel(unsigned v, void *p) { hardware_changes++; }
static void aux_init(struct qmp_combo *q) { hardware_changes++; }
static int qmp_combo_usb_power_off(void *p) { hardware_changes++; return 0; }
static int qmp_combo_usb_power_on(void *p) { hardware_changes++; return 0; }
static int qmp_combo_com_init(void *p, bool force) { hardware_changes++; return 0; }
static int qmp_combo_com_exit(void *p, bool force) { hardware_changes++; return 0; }
enum { DP_STATE_IDLE, DP_STATE_CONFIGURE, DP_STATE_CONFIGURE_PRIME,
       DP_STATE_UPDATE, DP_STATE_EXIT_PRIME, DP_STATE_EXIT, DP_STATE_ENTER, DP_STATE_ENTER_PRIME };
struct work_struct { int unused; };
struct dp_altmode { struct typec_altmode *alt, *plug_prime;
    struct { u32 conf, status; } data, data_prime; u32 applied_conf;
    int state, lock; struct work_struct work; bool hpd; void *connector_fwnode; };
static void *typec_altmode_get_drvdata(struct typec_altmode *a) { return a->drvdata; }
static void mutex_lock(int *p) {}
static int qmp_combo_reconfig_begin(struct qmp_combo *q) { return 0; }
static void qmp_combo_reconfig_end(struct qmp_combo *q) {}
static void mutex_unlock(int *p) {}
static void schedule_work(struct work_struct *p) {}
static int typec_cable_altmode_enter(struct typec_altmode *a,int sop,void *data) { return 0; }
static int typec_cable_altmode_exit(struct typec_altmode *a,int sop) { return 0; }
static void typec_altmode_put_plug(struct typec_altmode *a) { dropped_cables++; }
static void typec_altmode_update_active(struct typec_altmode *a,bool active) { a->active=active; }
static void drm_connector_oob_hotplug_event(void *p,int state) {}
static void sysfs_notify(int *p,const char *group,const char *attr) {}
static int dp_altmode_configured(struct dp_altmode *dp) { return 0; }
/* Model the mutation performed by the actual status parser; the attention
 * entry point, notification ordering and all transaction functions are extracted. */
static u32 pending_conf;
static int dp_altmode_status_update(struct dp_altmode *dp) {
    dp->data.conf=dp->data_prime.conf=pending_conf;
    dp->state=DP_STATE_CONFIGURE;
    return 0;
}
static int typec_altmode_get_svdm_version(struct typec_altmode *a) { return 1; }
static int typec_altmode_get_cable_svdm_version(struct typec_altmode *a) { return 1; }
static int typec_altmode_vdm(struct typec_altmode *a, u32 header, const u32 *conf, int n) {
    configure_vdms++;
    last_configure=*conf;
    return configure_error;
}
static int typec_cable_altmode_vdm(struct typec_altmode *a, int sop, u32 header, const u32 *conf, int n) {
    cable_vdms++;
    return configure_error;
}
static int send_exit(struct typec_altmode *a) { exit_vdms++; return 0; }
static int send_enter(struct typec_altmode *a,u32 *vdo) { enter_vdms++; return 0; }
'''

for file, names in [
    ('drivers/phy/qualcomm/phy-qcom-qmp-combo.c', ['qmp_combo_set_mux', 'qmp_combo_typec_mux_set']),
    ('drivers/usb/dwc3/dwc3-qcom-legacy.c', ['dwc3_qcom_mux_set']),
    ('drivers/usb/typec/mux.c', ['typec_mux_set']),
    ('drivers/usb/typec/bus.c', ['typec_altmode_set_retimer', 'typec_altmode_set_mux',
                        'typec_altmode_set_switches', 'typec_altmode_set_state',
                        'typec_altmode_notify', 'typec_altmode_enter', 'typec_altmode_exit']),
    ('drivers/usb/typec/altmodes/displayport.c',
        (['dp_altmode_notify_config', 'dp_altmode_restore', 'dp_altmode_notify', 'dp_altmode_exit']
            if variant == 'fixed' else ['dp_altmode_notify']) +
        ['dp_altmode_configure_vdm', 'dp_altmode_configure_vdm_cable', 'dp_altmode_attention',
         'dp_altmode_vdm', 'dp_altmode_work']),
]:
    for name in names:
        code += extract(file, name)

if variant == 'original':
    code += 'static int dp_altmode_exit(struct dp_altmode *dp) { return typec_altmode_exit(dp->alt); }\n'

code += r'''
static int checked_dwc3(struct typec_mux_dev *m, struct typec_mux_state *s) {
    if (fail_restore && s->mode != TYPEC_STATE_SAFE) return -EIO;
    return dwc3_qcom_mux_set(m,s);
}
struct fixture {
    struct dwc3_qcom glue;
    struct qmp_combo phy;
    struct typec_mux_dev glue_mux, phy_mux;
    struct typec_mux mux;
    struct device port_dev, partner_dev;
    struct altmode port, partner;
    struct dp_altmode dp;
};
static void setup(struct fixture *f, int reverse, bool four, bool powered) {
    static const struct qmp_phy_cfg cfg={aux_init};
    static const struct typec_altmode_ops ops={.exit=send_exit,.enter=send_enter};
    memset(f,0,sizeof(*f));
    errors=restore_errors=configure_vdms=cable_vdms=enter_vdms=exit_vdms=hardware_changes=0;
    fail_restore=configure_error=0;
    dropped_cables=0;
    last_configure=0;
    f->glue.dp_active=true;
    f->glue.dp_only=f->glue.utmi_pipe_clk=four;
    f->phy=(struct qmp_combo){.cfg=&cfg,
        .qmpphy_mode=four?QMPPHY_MODE_DP_ONLY:QMPPHY_MODE_USB3DP,
        .dp_powered_on=powered, .init_count=1, .usb_init_count=1, .dp_init_count=1};
    f->glue_mux=(struct typec_mux_dev){&f->glue,checked_dwc3};
    f->phy_mux=(struct typec_mux_dev){&f->phy,qmp_combo_typec_mux_set};
    f->mux.num_mux_devs=2;
    f->mux.mux_devs[reverse?1:0]=&f->glue_mux;
    f->mux.mux_devs[reverse?0:1]=&f->phy_mux;
    f->port_dev.is_port=true;
    f->port.adev=(struct typec_altmode){.dev.parent=&f->port_dev,
        .svid=USB_TYPEC_DP_SID,.active=true,.ops=&ops};
    f->partner.adev=(struct typec_altmode){.dev.parent=&f->partner_dev,
        .svid=USB_TYPEC_DP_SID,.active=true};
    f->port.partner=&f->partner;
    f->partner.partner=&f->port;
    f->port.mux=&f->mux;
    f->dp.alt=&f->partner.adev;
    f->dp.data.conf=four?CONF_C:CONF_D;
    f->dp.data_prime.conf=f->dp.applied_conf=f->dp.data.conf;
    f->partner.adev.drvdata=&f->dp;
}
static void assert_original_state(struct fixture *f,bool four) {
    assert(f->glue.dp_active);
    assert(f->glue.utmi_pipe_clk==four);
    assert(f->glue.dp_only==four);
    assert(f->phy.qmpphy_mode==(four?QMPPHY_MODE_DP_ONLY:QMPPHY_MODE_USB3DP));
    assert(f->dp.data.conf==(four?CONF_C:CONF_D));
    assert(f->dp.data_prime.conf==f->dp.data.conf);
    assert(f->dp.applied_conf==f->dp.data.conf);
    assert(hardware_changes==0);
}
int main(void) {
    struct fixture f;
    for (int reverse=0;reverse<2;reverse++) {
        for (int four=0;four<2;four++) {
            setup(&f,reverse,four,true);
            assert(dp_altmode_configure_vdm(&f.dp,four?CONF_D:CONF_C)==-EBUSY);
            assert(configure_vdms==0);
            assert_original_state(&f,four);

            /* Automatic status paths overwrite pending configuration first. */
            for (int usb=0;usb<2;usb++) {
                u32 pending=usb?0:(four?CONF_D:CONF_C);
                setup(&f,reverse,four,true);
                f.dp.data.conf=f.dp.data_prime.conf=pending;
                assert(dp_altmode_configure_vdm(&f.dp,pending)==-EBUSY);
                assert(configure_vdms==0);
                assert_original_state(&f,four);

                /* Attention must not push pending configuration before SAFE. */
                setup(&f,reverse,four,true);
                pending_conf=pending;
                dp_altmode_attention(f.dp.alt,0);
                assert(f.glue.utmi_pipe_clk==four);
                assert(f.dp.applied_conf==(four?CONF_C:CONF_D));
                assert(f.dp.data.conf==pending);
                assert(dp_altmode_configure_vdm(&f.dp,pending)==-EBUSY);
                assert_original_state(&f,four);

                /* An active cable must not change before the SAFE check. */
                setup(&f,reverse,four,true);
                f.dp.data.conf=f.dp.data_prime.conf=pending;
                assert(dp_altmode_configure_vdm_cable(&f.dp,pending)==-EBUSY);
                assert(cable_vdms==0);
                assert_original_state(&f,four);
            }

            setup(&f,reverse,four,true);
            assert(dp_altmode_exit(&f.dp)==-EBUSY);
            assert(exit_vdms==0);
            assert_original_state(&f,four);

            /* Untagged physical detach retains the existing deferred-PHY path. */
            setup(&f,reverse,four,true);
            struct typec_mux_state detach={.mode=TYPEC_STATE_SAFE};
            assert(typec_mux_set(&f.mux,&detach)==0);
            assert(f.glue.utmi_pipe_clk && !f.glue.dp_active);
            f.phy.dp_powered_on=false;
            detach.mode=TYPEC_STATE_USB;
            assert(typec_mux_set(&f.mux,&detach)==0);
            assert(!f.glue.utmi_pipe_clk && f.phy.qmpphy_mode==QMPPHY_MODE_USB3_ONLY);
            f.dp.data.conf=CONF_C;
            assert(dp_altmode_configure_vdm(&f.dp,CONF_C)==0);
            assert(dp_altmode_notify(&f.dp)==0);
            assert(f.glue.utmi_pipe_clk && f.phy.qmpphy_mode==QMPPHY_MODE_DP_ONLY);

            /* DRM-off reconfiguration completes SAFE then the ACK notification. */
            setup(&f,reverse,four,false);
            u32 target=four?CONF_D:CONF_C;
            assert(dp_altmode_configure_vdm(&f.dp,target)==0);
            assert(configure_vdms==1 && f.phy.qmpphy_mode==QMPPHY_MODE_SAFE);
            f.dp.data.conf=target;
            assert(dp_altmode_notify(&f.dp)==0);
            assert(f.glue.utmi_pipe_clk==!four);
            assert(f.phy.qmpphy_mode==(four?QMPPHY_MODE_USB3DP:QMPPHY_MODE_DP_ONLY));
            assert(f.dp.applied_conf==target);

            setup(&f,reverse,four,false);
            f.dp.data.conf=f.dp.data_prime.conf=target;
            assert(dp_altmode_configure_vdm_cable(&f.dp,target)==0);
            assert(cable_vdms==1 && f.phy.qmpphy_mode==QMPPHY_MODE_SAFE);
            assert(dp_altmode_configure_vdm(&f.dp,target)==0);
            assert(dp_altmode_notify(&f.dp)==0);
            assert(f.glue.utmi_pipe_clk==!four && f.dp.applied_conf==target);

            setup(&f,reverse,four,false);
            assert(dp_altmode_exit(&f.dp)==0 && exit_vdms==1);
            f.dp.data.conf=0;
            assert(dp_altmode_notify(&f.dp)==0);
            assert(!f.glue.utmi_pipe_clk && f.phy.qmpphy_mode==QMPPHY_MODE_USB3_ONLY);

            /* Failed rollback is logged; the original error survives it. */
            setup(&f,reverse,four,true);
            fail_restore=1;
            assert(dp_altmode_configure_vdm(&f.dp,target)==-EBUSY);
            assert(configure_vdms==0 && restore_errors==1);
            setup(&f,reverse,four,true);
            fail_restore=1;
            assert(dp_altmode_exit(&f.dp)==-EBUSY);
            assert(exit_vdms==0 && restore_errors==1);

            /* Preserve the existing rollback on a failed Configure transmission. */
            setup(&f,reverse,four,false);
            configure_error=-ETIMEDOUT;
            assert(dp_altmode_configure_vdm(&f.dp,target)==-ETIMEDOUT);
            assert(configure_vdms==1 && f.glue.utmi_pipe_clk==four);
            assert(f.phy.qmpphy_mode==(four?QMPPHY_MODE_DP_ONLY:QMPPHY_MODE_USB3DP));

            /* A fresh altmode retains existing entry behavior during old teardown. */
            setup(&f,reverse,four,true);
            f.dp.applied_conf=0;
            f.dp.data.conf=f.dp.data_prime.conf=0;
            f.partner.adev.active=false;
            assert(typec_altmode_enter(f.dp.alt,NULL)==0 && enter_vdms==1);
            f.partner.adev.active=true;
            pending_conf=CONF_C;
            dp_altmode_attention(f.dp.alt,0);
            assert(f.dp.applied_conf==0 && f.dp.data.conf==CONF_C);
            assert(dp_altmode_configure_vdm(&f.dp,CONF_C)==0 && configure_vdms==1);

            setup(&f,reverse,four,true);
            f.dp.applied_conf=0;
            f.dp.data.conf=f.dp.data_prime.conf=CONF_C;
            assert(dp_altmode_configure_vdm_cable(&f.dp,CONF_C)==0 && cable_vdms==1);

            /* Exit ACK ends the committed session even while teardown runs. */
            setup(&f,reverse,four,true);
            f.dp.hpd=true;
            f.dp.data.status=1;
            assert(dp_altmode_vdm(f.dp.alt,(CMDT_RSP_ACK<<8)|CMD_EXIT_MODE,NULL,0)==0);
            assert(!f.partner.adev.active && !f.dp.hpd);
            assert(f.dp.data.status==0 && f.dp.data.conf==0 && f.dp.applied_conf==0);
            assert(typec_altmode_enter(f.dp.alt,NULL)==0 && enter_vdms==1);
            f.partner.adev.active=true;
            f.dp.data.conf=f.dp.data_prime.conf=CONF_C;
            configure_error=-EIO;
            assert(dp_altmode_configure_vdm(&f.dp,CONF_C)==-EIO && configure_vdms==1);
            assert(f.dp.data.conf==0 && f.dp.data_prime.conf==0 && f.dp.applied_conf==0);

            /* Cable send failure keeps the desired SOP fallback configuration. */
            setup(&f,reverse,four,false);
            f.dp.plug_prime=&f.port.adev;
            f.dp.data.conf=f.dp.data_prime.conf=target;
            f.dp.state=DP_STATE_CONFIGURE_PRIME;
            configure_error=-EIO;
            dp_altmode_work(&f.dp.work);
            assert(dropped_cables==1 && !f.dp.plug_prime);
            assert(f.dp.state==DP_STATE_CONFIGURE && f.dp.data.conf==target);
            assert(f.dp.applied_conf==(four?CONF_C:CONF_D));
            configure_error=0;
            dp_altmode_work(&f.dp.work);
            assert(configure_vdms==1 && last_configure==target);

            /* Busy preflight restores old state without dropping the cable. */
            setup(&f,reverse,four,true);
            f.dp.plug_prime=&f.port.adev;
            f.dp.data.conf=f.dp.data_prime.conf=target;
            f.dp.state=DP_STATE_CONFIGURE_PRIME;
            dp_altmode_work(&f.dp.work);
            assert(!dropped_cables && f.dp.plug_prime && !cable_vdms);
            assert(f.dp.state==DP_STATE_IDLE);
            assert_original_state(&f,four);
        }
    }
    puts("PASS: both mux orders; C/D/USB/Exit/cable preflight and rollback; pending attention; detach/reconnect; powered-off changes; initial entry during teardown; rollback errors; Exit ACK/re-entry cache; cable-send failure preserves requested SOP fallback");
}
'''
with tempfile.TemporaryDirectory(prefix="dp-mux-test-") as directory:
    scratch = Path(directory)
    source, binary = scratch / 'test.c', scratch / 'test'
    source.write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-parameter',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], cwd=scratch, check=True)
