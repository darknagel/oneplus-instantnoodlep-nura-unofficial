"""Exercise the actual regulator sequence with GPIO errors injected."""
from pathlib import Path
import sys, tempfile
kernel = Path(sys.argv[1]).resolve()
scratch = tempfile.TemporaryDirectory()
import subprocess

root = Path(scratch.name)
s = (kernel/'drivers/regulator/oneplus-instantnoodlep-vbus.c').read_text()
s = s[s.index('struct instantnoodlep_vbus {'):s.index('static const struct regulator_ops')]
prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct gpio_desc { int id, value; };
struct regulator_dev { void *data; };
static void *rdev_get_drvdata(struct regulator_dev *d) { return d->data; }
static int step, fail_at;
static char events[256];
static int pos;
static int gpiod_set_value_cansleep(struct gpio_desc *g, int value) {
 pos += snprintf(events + pos, sizeof(events)-pos, "%d=%d,", g->id, value);
 if (++step == fail_at) return -EIO;
 g->value = value;
 return 0;
}
static int gpiod_get_value_cansleep(struct gpio_desc *g) { return g->value; }
static void msleep(int n) {
 pos += snprintf(events + pos, sizeof(events)-pos, "wait%d,", n);
}
'''
suffix = r'''
int main(void) {
 struct gpio_desc wireless={.id=8}, boost={.id=172}, output={.id=4};
 struct instantnoodlep_vbus v={&wireless, &boost, &output};
 struct regulator_dev r={&v};
 assert(!instantnoodlep_vbus_is_enabled(&r));
 assert(!instantnoodlep_vbus_enable(&r));
 assert(!strcmp(events,"8=1,wait20,172=1,wait100,4=1,"));
 assert(instantnoodlep_vbus_is_enabled(&r)==1);
 pos=0; events[0]=0;
 assert(!instantnoodlep_vbus_disable(&r));
 assert(!strcmp(events,"4=0,172=0,wait20,8=0,"));
 for (int failure=1; failure<=3; ++failure) {
  wireless.value=boost.value=output.value=0;
  step=pos=0; events[0]=0; fail_at=failure;
  assert(instantnoodlep_vbus_enable(&r)==-EIO);
  assert(!wireless.value && !boost.value && !output.value);
 }
 /* Every shutdown stage is attempted even if an earlier write fails. */
 for (int failure=1; failure<=3; ++failure) {
  wireless.value=boost.value=output.value=1;
  step=pos=0; events[0]=0; fail_at=failure;
  assert(instantnoodlep_vbus_disable(&r)==-EIO);
  assert(!strcmp(events,"4=0,172=0,wait20,8=0,"));
  assert(step==3);
 }
 puts("PASS: vendor enable/disable order and delays; enable rollback; shutdown error propagation");
}
'''
(root/'sequence-test.c').write_text(prefix+s+suffix)
subprocess.run(['cc','-Wall','-Wextra','-Werror','-o',str(root/'sequence-test'),str(root/'sequence-test.c')],check=True)
subprocess.run([str(root/'sequence-test')],check=True)
