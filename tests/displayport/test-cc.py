from pathlib import Path
import sys, tempfile
kernel = Path(sys.argv[1]).resolve()
scratch = tempfile.TemporaryDirectory()
import re,subprocess
p = Path(scratch.name)
source=(kernel/'drivers/usb/typec/tcpm/qcom/qcom_pmic_typec_port.c').read_text()
a=source.index('static int qcom_pmic_typec_port_set_cc(');b=source.index('static int qcom_pmic_typec_port_set_vconn',a)
defines='\n'.join(l for l in source[:source.index('struct pmic_typec_port_irq_data')].splitlines() if l.startswith('#define') and not l.endswith('\\'))
prefix=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdbool.h>
#define BIT(n) (1U << (n))
#define GENMASK(h,l) (((~0U) << (l)) & ((~0U) >> (31-(h))))
enum typec_cc_status { TYPEC_CC_OPEN, TYPEC_CC_RA, TYPEC_CC_RD, TYPEC_CC_RP_DEF, TYPEC_CC_RP_1_5, TYPEC_CC_RP_3_0 };
enum typec_cc_polarity { TYPEC_POLARITY_CC1, TYPEC_POLARITY_CC2 };
struct device { int unused; };
struct pmic_typec_port { struct device *dev; void *regmap; unsigned base; int lock,cc,debouncing_cc,vbus_lock; bool external_vbus,power_role_swap,vbus_off_pending,vbus_enabled; void *vdd_vbus; };
struct pmic_typec { struct pmic_typec_port *pmic_typec_port; };
struct tcpc_dev { struct pmic_typec *parent; int (*set_power_role_swap)(struct tcpc_dev *,bool,enum typec_cc_polarity); };
struct tcpm_port { struct tcpc_dev *tcpc; bool power_role_swap_active; enum typec_cc_polarity polarity; };
#define tcpm_log_force(...) ((void)0)
#define tcpc_to_tcpm(t) ((t)->parent)
#define spin_lock_irqsave(l,f) do { (void)(l); (f)=0; } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(l); (void)(f); } while(0)
#define dev_dbg(d,...) ((void)(d))
#define dev_warn(d,...) ((void)(d),warnings++)
static int warnings,polls,last_poll_cc,regulator_error,regulator_calls;
typedef unsigned u32;
static void mutex_lock(int *p) { assert(!*p); *p=1; }
static void mutex_unlock(int *p) { assert(*p); *p=0; }
static int regulator_enable(void *p) { regulator_calls++; return regulator_error; }
static int regulator_disable(void *p) { regulator_calls++; return regulator_error; }
static unsigned regs[0x2000];
static int writes,fail_write,fail_read;
#define regmap_read_poll_timeout(map,addr,v,cond,delay,timeout) ({ \
 (void)(map); (void)(delay); assert((timeout)==250000); \
 polls++; last_poll_cc=regs[0x1544]; (v)=regs[addr]; (cond)?0:-ETIMEDOUT; })
static int regmap_read(void *map,unsigned addr,unsigned *v) { (void)map; if(fail_read) return -EIO; *v=regs[addr]; return 0; }
static int regmap_write(void *map,unsigned addr,unsigned v) { (void)map; if(++writes==fail_write) return -EIO; regs[addr]=v; return 0; }
static int regmap_update_bits(void *map,unsigned addr,unsigned mask,unsigned v) { return regmap_write(map,addr,(regs[addr]&~mask)|(v&mask)); }
static void qcom_pmic_set_cc_debounce(struct pmic_typec_port *p) { p->debouncing_cc=1; }
'''
suffix=r'''
int main(void) {
 struct device d={0}; struct pmic_typec_port p={.dev=&d,.base=0x1500};
 struct pmic_typec t={&p}; struct tcpc_dev c={.parent=&t};
 int inputs[]={TYPEC_CC_OPEN,TYPEC_CC_RD,TYPEC_CC_RP_DEF,TYPEC_CC_RP_1_5,TYPEC_CC_RP_3_0};
 unsigned modes[]={TYPEC_DISABLE_CMD,EN_SNK_ONLY,EN_SRC_ONLY,EN_SRC_ONLY,EN_SRC_ONLY};
 unsigned currents[]={0,0,TYPEC_SRC_RP_SEL_80UA,TYPEC_SRC_RP_SEL_180UA,TYPEC_SRC_RP_SEL_330UA};
 for(unsigned i=0;i<5;i++) {
  regs[0x1544]=0xff; writes=0; fail_write=0;
  assert(!qcom_pmic_typec_port_set_cc(&c,inputs[i]));
  assert(regs[0x1544]==modes[i]); assert(p.cc==inputs[i]);
  if(i>=2) assert(regs[0x1552]==currents[i]);
  for(int f=1; f<=((i==0 || i>=2)?2:1); f++) {
   writes=0;fail_write=f;p.cc=99;
   assert(qcom_pmic_typec_port_set_cc(&c,inputs[i])==-EIO);
   assert(p.cc==99);
  }
 }
 writes=0;fail_write=0;fail_read=1;p.cc=99;
 assert(qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_RD)==-EIO);
 assert(p.cc==99 && writes==0);
 fail_read=0;
 assert(qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_RA)==-EINVAL);
 fail_write=0;writes=0;
 assert(!qcom_pmic_typec_port_set_power_role_swap(&c,true,TYPEC_POLARITY_CC2));
 assert((regs[0x1548]&7)==7);
 assert(!qcom_pmic_typec_port_set_power_role_swap(&c,true,TYPEC_POLARITY_CC1));
 assert((regs[0x1548]&7)==5);
 assert(!qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_OPEN));
 assert(!(regs[0x1548]&TYPEC_CCOUT_SRC));
 writes=0;fail_write=1;
 assert(qcom_pmic_typec_port_set_power_role_swap(&c,true,TYPEC_POLARITY_CC2)==-EIO);
 fail_write=0;writes=0;
 assert(!qcom_pmic_typec_port_set_power_role_swap(&c,false,TYPEC_POLARITY_CC1));
 assert(!(regs[0x1548]&TYPEC_CCOUT_SRC));
 assert(!qcom_pmic_typec_port_set_polarity(&c,TYPEC_POLARITY_CC2));
 assert(!(regs[0x1548]&TYPEC_CCOUT_SRC));
 c.set_power_role_swap=qcom_pmic_typec_port_set_power_role_swap;
 struct tcpm_port tp={.tcpc=&c,.polarity=TYPEC_POLARITY_CC2};
 assert(!tcpm_set_power_role_swap(&tp,true)); assert(tp.power_role_swap_active);
 int previous=writes;
 assert(!tcpm_set_power_role_swap(&tp,true)); assert(writes==previous);
 fail_write=writes+1;
 assert(tcpm_set_power_role_swap(&tp,false)==-EIO); assert(tp.power_role_swap_active);
 fail_write=0;
 assert(!tcpm_set_power_role_swap(&tp,false)); assert(!tp.power_role_swap_active);
 assert(!(regs[0x1548]&TYPEC_CCOUT_SRC));

 /* External source-to-sink: no VSAFE0 poll until Rd is programmed. */
 p.external_vbus=true; p.power_role_swap=true; p.cc=TYPEC_CC_RP_DEF;
 polls=warnings=0; regs[0x150a]=TYPEC_SM_VBUS_VSAFE5V;
 assert(!qcom_pmic_typec_port_vbus_toggle(&p,false));
 assert(p.vbus_off_pending && polls==0);
 p.vbus_enabled=false; regs[0x150a]=TYPEC_SM_VBUS_VSAFE0V;
 assert(!qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_RD));
 assert(!p.vbus_off_pending && polls==1 && last_poll_cc==EN_SNK_ONLY && warnings==0);
 /* Failed CC writes retain the check for recovery; OPEN checks after disable. */
 p.cc=TYPEC_CC_RP_DEF; assert(!qcom_pmic_typec_port_vbus_toggle(&p,false));
 fail_write=writes+1;
 assert(qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_RD)==-EIO);
 assert(p.vbus_off_pending && polls==1);
 fail_write=0;
 assert(!qcom_pmic_typec_port_set_power_role_swap(&c,false,TYPEC_POLARITY_CC1));
 assert(!qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_OPEN));
 assert(!p.vbus_off_pending && polls==2 && last_poll_cc==TYPEC_DISABLE_CMD);
 /* A real deferred voltage timeout remains visible. */
 p.cc=TYPEC_CC_RP_DEF; p.power_role_swap=true;
 assert(!qcom_pmic_typec_port_vbus_toggle(&p,false));
 regs[0x150a]=TYPEC_SM_VBUS_VSAFE5V;
 assert(!qcom_pmic_typec_port_set_cc(&c,TYPEC_CC_RD));
 assert(warnings==1 && polls==3);
 /* Internal supply, non-swap shutdown and enable retain immediate checks. */
 p.external_vbus=false; p.cc=TYPEC_CC_RP_DEF;
 assert(!qcom_pmic_typec_port_vbus_toggle(&p,false)); assert(polls==4);
 p.external_vbus=true; p.power_role_swap=false;
 assert(!qcom_pmic_typec_port_vbus_toggle(&p,false)); assert(polls==5);
 p.vbus_off_pending=true;
 assert(!qcom_pmic_typec_port_vbus_toggle(&p,true));
 assert(polls==6 && !p.vbus_off_pending);
 /* A failed physical switch must not alter the deferred-check state. */
 p.vbus_off_pending=true; regulator_error=-EIO;
 assert(qcom_pmic_typec_port_vbus_toggle(&p,false)==-EIO);
 assert(p.vbus_off_pending && polls==6);
 puts("PASS: external PR_SWAP defers the voltage check until Rd; failed CC writes retain it for recovery; OPEN checks after disabling CC; timeouts remain visible; other supply transitions and regulator failures preserve their behavior");
 puts("PASS: swap-only hold, completion release, duplicate suppression, cleanup retry; CC1/CC2 hold and detach release; open/Rd/all Rp levels program hardware; read/write errors propagate without changing cached CC");
}
'''
tcpm=(kernel/'drivers/usb/typec/tcpm/tcpm.c').read_text()
c=tcpm.index('static int tcpm_set_power_role_swap(');d=tcpm.index('static void tcpm_ams_finish(',c)
(p/'cc-test.c').write_text(prefix+defines+'\n'+source[source.index('static void qcom_pmic_typec_port_wait_vbus('):source.index('static int qcom_pmic_typec_port_get_vbus(')]+source[a:b]+tcpm[c:d]+suffix)
subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-o',str(p/'cc-test'),str(p/'cc-test.c')],check=True)
subprocess.run([str(p/'cc-test')],check=True)
