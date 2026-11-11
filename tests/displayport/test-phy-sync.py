#!/usr/bin/env python3
"""Exercise controller/PHY exclusion, PM unwind and callback teardown."""
from pathlib import Path
import re, subprocess, sys, tempfile

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} KERNEL_CHECKOUT")
root = Path(sys.argv[1]).resolve()

def extract(path, name):
    s=(root/path).read_text()
    m=re.search(r'^(?:static )?(?:int|void) '+name+r'\(',s,re.M)
    assert m, name
    b=s.index('{',m.start()); end=b+1; depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[m.start():end]+'\n'

code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
typedef uint32_t u32;
typedef pthread_mutex_t mutex;
static void mutex_lock(mutex *m) { assert(!pthread_mutex_lock(m)); }
static void mutex_unlock(mutex *m) { assert(!pthread_mutex_unlock(m)); }
static mutex *locked(mutex *m) { mutex_lock(m); return m; }
static void unlocked(mutex **m) { mutex_unlock(*m); }
#define guard(type) __attribute__((cleanup(unlocked))) mutex *scope_lock=locked
#define DWC3_GUSB3PIPECTL(i) (i)
#define DWC3_GUSB3PIPECTL_SUSPHY (1U<<17)
struct dwc3 { mutex mutex; void *dev; u32 pipe; };
struct platform_device { struct dwc3 *data; };
struct dwc3_qcom { bool pm_suspended; mutex pipe_clk_lock; struct platform_device *dwc3; u32 saved_pipe_susphy; };
struct qcom_qmp_usb_reconfig_ops { int (*prepare)(void *); void (*complete)(void *); };
struct qmp_combo { mutex reconfig_lock; const struct qcom_qmp_usb_reconfig_ops *usb_reconfig_ops; void *usb_reconfig_data; };
struct phy { const void *ops; struct qmp_combo *data; };
static const int qmp_combo_usb_phy_ops=1;
static int pm_error,pm_usage,pm_calls;
static struct dwc3 *platform_get_drvdata(struct platform_device *p) { return p->data; }
static struct qmp_combo *phy_get_drvdata(struct phy *p) { return p->data; }
static int pm_runtime_resume_and_get(void *p) {
 (void)p; pm_calls++; if(pm_error) return pm_error; pm_usage++; return 0;
}
static void pm_runtime_put_autosuspend(void *p) { (void)p; assert(pm_usage>0); pm_usage--; }
static u32 dwc3_readl(struct dwc3 *d,int reg) { (void)reg; return d->pipe; }
static void dwc3_writel(struct dwc3 *d,int reg,u32 val) { (void)reg; d->pipe=val; }
'''
for name in ('dwc3_qcom_phy_prepare_locked','dwc3_qcom_phy_complete_locked',
             'dwc3_qcom_phy_prepare','dwc3_qcom_phy_complete'):
    code+=extract('drivers/usb/dwc3/dwc3-qcom-legacy.c',name)
for name in ('qcom_qmp_usb_reconfig_register','qcom_qmp_usb_reconfig_unregister',
             'qmp_combo_reconfig_begin','qmp_combo_reconfig_end'):
    code+=extract('drivers/phy/qualcomm/phy-qcom-qmp-combo.c',name)
code+=r'''
static struct qcom_qmp_usb_reconfig_ops ops={dwc3_qcom_phy_prepare,dwc3_qcom_phy_complete};
static struct qmp_combo qmp={.reconfig_lock=PTHREAD_MUTEX_INITIALIZER};
static struct phy phy={&qmp_combo_usb_phy_ops,&qmp};
static struct dwc3 dwc={.mutex=PTHREAD_MUTEX_INITIALIZER};
static struct platform_device pdev={&dwc};
static struct dwc3_qcom qcom={.pipe_clk_lock=PTHREAD_MUTEX_INITIALIZER,.dwc3=&pdev};
static atomic_int entered,finished;
static void unlocked_now(mutex *m) {
 assert(!pthread_mutex_trylock(m));mutex_unlock(m);
}
static void *guard_thread(void *p) {
 (void)p; atomic_store(&entered,1);
 assert(!qmp_combo_reconfig_begin(&qmp));
 assert(!(dwc.pipe&DWC3_GUSB3PIPECTL_SUSPHY));
 qmp_combo_reconfig_end(&qmp);atomic_store(&finished,1);return NULL;
}
static void *unregister_thread(void *p) {
 (void)p;atomic_store(&entered,1);
 qcom_qmp_usb_reconfig_unregister(&phy,&qcom);
 atomic_store(&finished,1);return NULL;
}
int main(void) {
 pthread_t thread;
 assert(qcom_qmp_usb_reconfig_register(NULL,&ops,&qcom)==-EOPNOTSUPP);
 assert(qcom_qmp_usb_reconfig_register(&phy,NULL,&qcom)==-EINVAL);
 assert(!qcom_qmp_usb_reconfig_register(&phy,&ops,&qcom));
 assert(qcom_qmp_usb_reconfig_register(&phy,&ops,&qcom)==-EBUSY);
 for(int awake=0;awake<2;awake++) {
  dwc.pipe=0x1000|(awake?0:DWC3_GUSB3PIPECTL_SUSPHY);
  assert(!qmp_combo_reconfig_begin(&qmp));
  assert(!(dwc.pipe&DWC3_GUSB3PIPECTL_SUSPHY) && pm_usage==1);
  assert(pthread_mutex_trylock(&dwc.mutex)==EBUSY);
  dwc.pipe|=0x80;
  qmp_combo_reconfig_end(&qmp);
  assert((dwc.pipe&DWC3_GUSB3PIPECTL_SUSPHY)==(awake?0:DWC3_GUSB3PIPECTL_SUSPHY));
  assert(dwc.pipe&0x80);assert(!pm_usage);
  unlocked_now(&qmp.reconfig_lock);unlocked_now(&qcom.pipe_clk_lock);unlocked_now(&dwc.mutex);
 }
 pm_error=-EIO;dwc.pipe=DWC3_GUSB3PIPECTL_SUSPHY;
 assert(qmp_combo_reconfig_begin(&qmp)==-EIO && !pm_usage);
 assert(dwc.pipe==DWC3_GUSB3PIPECTL_SUSPHY);
 unlocked_now(&qmp.reconfig_lock);unlocked_now(&qcom.pipe_clk_lock);unlocked_now(&dwc.mutex);
 pm_error=0;qcom.pm_suspended=true;
 int before=pm_calls;
 assert(qmp_combo_reconfig_begin(&qmp)==-EBUSY && pm_calls==before);
 unlocked_now(&qmp.reconfig_lock);unlocked_now(&qcom.pipe_clk_lock);
 qcom.pm_suspended=false;
 /* Model the role worker holding the controller mutex during its reset. */
 mutex_lock(&dwc.mutex);entered=finished=0;
 assert(!pthread_create(&thread,NULL,guard_thread,NULL));
 while(!atomic_load(&entered)) sched_yield();
 usleep(10000);assert(!atomic_load(&finished));
 assert(dwc.pipe==DWC3_GUSB3PIPECTL_SUSPHY);
 mutex_unlock(&dwc.mutex);assert(!pthread_join(thread,NULL));
 assert(atomic_load(&finished) && !pm_usage);
 /* Provider teardown cannot invalidate a callback in flight. */
 assert(!qmp_combo_reconfig_begin(&qmp));entered=finished=0;
 assert(!pthread_create(&thread,NULL,unregister_thread,NULL));
 while(!atomic_load(&entered)) sched_yield();
 usleep(10000);assert(!atomic_load(&finished));
 qmp_combo_reconfig_end(&qmp);assert(!pthread_join(thread,NULL));
 assert(!qmp.usb_reconfig_ops && !pm_usage);
 before=pm_calls;assert(!qmp_combo_reconfig_begin(&qmp));qmp_combo_reconfig_end(&qmp);
 assert(pm_calls==before);
 puts("PASS: controller reset excludes PHY startup; suspend bit restored without overwriting other bits; PM failures and system suspend release locks; callback removal waits for an in-flight transaction; unsupported PHY and duplicate registration handled");
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'test.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-pthread',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
