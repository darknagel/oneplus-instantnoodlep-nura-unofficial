#!/usr/bin/env python3
"""DisplayPort over system suspend: PHY state and the disable path after a failed link.

Compiles the real functions from drivers/gpu/drm/msm/dp/dp_display.c against a
model of the controller: a link register may only be written while the link
clocks run, and the PHY loses its setup once the controller is powered down.
"""
from pathlib import Path
import re, subprocess, sys, tempfile

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} KERNEL_CHECKOUT")
root = Path(sys.argv[1]).resolve()

def extract(path, name):
    s=(root/path).read_text()
    m=re.search(r'^(?:static )?(?:int|void|bool) '+name+r'\(',s,re.M)
    assert m, name
    b=s.index('{',m.start()); end=b+1; depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[m.start():end]+'\n'

code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
/* No concurrent users in this controller model. */
#define guard(lock_type) (void)
#define WRITE_ONCE(field, value) ((field) = (value))
#define drm_dbg_dp(dev, ...) do { (void)(dev); } while (0)
struct drm_device;
struct drm_atomic_commit;
struct device { void *drvdata; };
struct platform_device { struct device dev; };
struct drm_dp_aux { int unused; };
struct drm_bridge { int unused; };
struct msm_dp_link { int sink_count; };

/* Hardware model. */
struct msm_dp_ctrl {
 bool core_clk_on, link_clk_on;
 bool phy_setup;        /* PHY holds its AUX and power-down setup */
 int unclocked_writes;  /* link register written without a link clock */
 int phy_inits, phy_exits, idle_pushes;
};
struct msm_dp {
 struct platform_device *pdev; struct drm_device *drm_dev;
 bool is_edp, power_on; int connector_type;
 bool probe_unplugged_audio, audio_link_ready, audio_clock_ready;
 int audio_clock_lock;
};
struct msm_dp_display_private {
 int irq; struct drm_device *drm_dev;
 bool core_initialized, phy_initialized;
 struct msm_dp_ctrl *ctrl; struct drm_dp_aux *aux; struct msm_dp_link *link;
 struct msm_dp msm_dp_display;
};
struct msm_dp_bridge { struct drm_bridge bridge; struct msm_dp *msm_dp_display; };
#define to_dp_bridge(x) container_of((x), struct msm_dp_bridge, bridge)

static int irq_depth, hpd_enabled;
static void disable_irq(int irq) { (void)irq; irq_depth++; }
static void enable_irq(int irq) { (void)irq; irq_depth--; }
static struct msm_dp_display_private *dev_get_dp_display_private(struct device *dev) { return dev->drvdata; }

static void msm_dp_ctrl_core_clk_enable(struct msm_dp_ctrl *c) { c->core_clk_on = true; }
static void msm_dp_ctrl_core_clk_disable(struct msm_dp_ctrl *c) {
 /* Powering the controller down takes the PHY's setup with it. */
 c->core_clk_on = false; c->phy_setup = false;
}
static void msm_dp_ctrl_reset(struct msm_dp_ctrl *c) { assert(c->core_clk_on); }
static void msm_dp_ctrl_enable_irq(struct msm_dp_ctrl *c) { assert(c->core_clk_on); }
static void msm_dp_ctrl_disable_irq(struct msm_dp_ctrl *c) { assert(c->core_clk_on); }
static void msm_dp_ctrl_phy_init(struct msm_dp_ctrl *c) { assert(c->core_clk_on); c->phy_setup = true; c->phy_inits++; }
static void msm_dp_ctrl_phy_exit(struct msm_dp_ctrl *c) { assert(c->core_clk_on); c->phy_setup = false; c->phy_exits++; }
static void msm_dp_ctrl_push_idle(struct msm_dp_ctrl *c) {
 c->idle_pushes++;
 if (!c->link_clk_on) c->unclocked_writes++;
}
static void msm_dp_aux_init(struct drm_dp_aux *a) { (void)a; }
static void msm_dp_aux_deinit(struct drm_dp_aux *a) { (void)a; }
static void msm_dp_aux_hpd_enable(struct drm_dp_aux *a) { (void)a; hpd_enabled++; }
static void msm_dp_aux_hpd_disable(struct drm_dp_aux *a) { (void)a; hpd_enabled--; }
'''
for name in ('msm_dp_display_host_phy_init','msm_dp_display_host_phy_exit',
             'msm_dp_display_host_init','msm_dp_display_host_deinit',
             'msm_dp_pm_runtime_suspend','msm_dp_pm_runtime_resume',
             'msm_dp_bridge_atomic_disable'):
    code+=extract('drivers/gpu/drm/msm/dp/dp_display.c',name)
code+=r'''
static struct msm_dp_ctrl ctrl; static struct drm_dp_aux aux; static struct msm_dp_link link;
static struct msm_dp_display_private dp; static struct platform_device pdev;
static struct msm_dp_bridge bridge;

static void setup(bool is_edp) {
 memset(&ctrl,0,sizeof(ctrl)); memset(&dp,0,sizeof(dp)); irq_depth=hpd_enabled=0;
 dp.ctrl=&ctrl; dp.aux=&aux; dp.link=&link; dp.msm_dp_display.pdev=&pdev;
 dp.msm_dp_display.is_edp=is_edp; pdev.dev.drvdata=&dp;
 bridge.msm_dp_display=&dp.msm_dp_display; link.sink_count=1;
 assert(!msm_dp_pm_runtime_resume(&pdev.dev));
 irq_depth=0;
}

/* An AUX transfer only reaches the sink while the PHY holds its setup. */
static bool aux_works(void) { return ctrl.core_clk_on && ctrl.phy_setup; }

int main(void)
{
 /* A monitor stays plugged in over system sleep. */
 setup(false);
 assert(msm_dp_display_host_phy_init(&dp) && aux_works());
 assert(!msm_dp_pm_runtime_suspend(&pdev.dev));
 assert(!ctrl.core_clk_on && irq_depth==1);
 assert(!msm_dp_pm_runtime_resume(&pdev.dev));
 /* The next detect or enable asks for the PHY; it must really set it up again. */
 msm_dp_display_host_phy_init(&dp);
 if (!aux_works()) { puts("FAIL: PHY still marked initialised after suspend, AUX is dead"); return 1; }
 assert(ctrl.phy_exits==1 && ctrl.phy_inits==2 && irq_depth==0);

 /* Nothing plugged in: suspend has no PHY to shut down. */
 setup(false);
 assert(!msm_dp_pm_runtime_suspend(&pdev.dev));
 assert(ctrl.phy_exits==0 && !dp.phy_initialized);

 /* eDP keeps its behaviour: PHY and HPD follow the controller. */
 setup(true);
 assert(dp.phy_initialized && hpd_enabled==1 && aux_works());
 assert(!msm_dp_pm_runtime_suspend(&pdev.dev));
 assert(!dp.phy_initialized && hpd_enabled==0 && ctrl.phy_exits==1);
 assert(!msm_dp_pm_runtime_resume(&pdev.dev));
 assert(dp.phy_initialized && hpd_enabled==1 && aux_works());

 /* Link training failed in enable: the link clocks are off and power_on is unset. */
 setup(false);
 dp.msm_dp_display.power_on=false; ctrl.link_clk_on=false;
 msm_dp_bridge_atomic_disable(&bridge.bridge, NULL);
 if (ctrl.unclocked_writes) { puts("FAIL: disable wrote a link register without a link clock"); return 1; }

 /* A running link stops advertising audio readiness before it is switched off. */
 setup(false);
 dp.msm_dp_display.power_on=true; ctrl.link_clk_on=true;
 dp.msm_dp_display.probe_unplugged_audio=true;
 dp.msm_dp_display.audio_link_ready=dp.msm_dp_display.audio_clock_ready=true;
 msm_dp_bridge_atomic_disable(&bridge.bridge, NULL);
 assert(ctrl.idle_pushes==1 && !ctrl.unclocked_writes);
 assert(!dp.msm_dp_display.audio_link_ready && !dp.msm_dp_display.audio_clock_ready);

 puts("PASS: PHY is set up again after suspend with a monitor plugged in; suspend without a PHY and eDP unchanged; disable after a failed link leaves the link registers alone; a running link is idled");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'test.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
