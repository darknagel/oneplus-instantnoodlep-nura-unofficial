from pathlib import Path
import sys, tempfile
kernel = Path(sys.argv[1]).resolve()
scratch = tempfile.TemporaryDirectory()
import subprocess
p = Path(scratch.name)
s=(kernel/'drivers/usb/dwc3/dwc3-qcom-legacy.c').read_text()
a=s.index('static int dwc3_qcom_mux_set(')
b=s.index('\nstatic int dwc3_qcom_mux_register',a)
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#define WRITE_ONCE(a,b) ((a)=(b))
#define guard(x) lock_stub
#define TYPEC_STATE_SAFE 0
#define TYPEC_STATE_USB 1
#define TYPEC_DP_STATE_C 4
#define TYPEC_DP_STATE_D 5
#define TYPEC_DP_STATE_E 6
#define TYPEC_DP_STATE_F 7
#define USB_TYPEC_DP_SID 0xff01
struct dwc3_qcom { bool dp_active,dp_only,utmi_pipe_clk,ignore_pipe_clk,pm_suspended;
int pipe_clk_lock; void *dev; void *reconfig_phy; };
struct typec_mux_dev { struct dwc3_qcom *qcom; };
struct alt { int svid; };
struct typec_mux_state { struct alt *alt; int mode; };
static int pm_error,changes;
static void lock_stub(int *p) {}
static void *typec_mux_get_drvdata(struct typec_mux_dev *m) {return m->qcom;}
static int pm_runtime_resume_and_get(void *p) {return pm_error;}
static void pm_runtime_put_autosuspend(void *p) {}
static int dwc3_qcom_phy_prepare_locked(struct dwc3_qcom *q) { return pm_error; }
static void dwc3_qcom_phy_complete_locked(struct dwc3_qcom *q) {}
static void dwc3_qcom_select_utmi_clk(struct dwc3_qcom *q, bool utmi) {
 q->utmi_pipe_clk=utmi; changes++;
}
'''+s[a:b]+r'''
int main(void) {
 for (int guarded=0; guarded<2; guarded++) {
 changes=0; pm_error=0;
 struct dwc3_qcom q={.reconfig_phy=guarded ? (void *)1 : NULL}; struct typec_mux_dev m={&q};
 struct alt dp={USB_TYPEC_DP_SID}; struct typec_mux_state s={&dp,TYPEC_STATE_SAFE};
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk && !q.dp_active);
 s.mode=TYPEC_DP_STATE_C;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk && q.dp_active);
 assert(changes==1);
 s.mode=TYPEC_DP_STATE_D;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk);
 s.mode=TYPEC_STATE_SAFE;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk && !q.dp_active);
 s.mode=TYPEC_STATE_USB;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && !q.utmi_pipe_clk && !q.dp_active);
 q.pm_suspended=true; s.mode=TYPEC_DP_STATE_E;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.dp_only && !q.utmi_pipe_clk);
 q.pm_suspended=false;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk);
 s.mode=TYPEC_STATE_USB; pm_error=-EACCES;
 assert(dwc3_qcom_mux_set(&m,&s)==-EACCES && q.dp_only && q.utmi_pipe_clk);
 pm_error=0;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && !q.utmi_pipe_clk);
 s.mode=TYPEC_STATE_SAFE;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && q.utmi_pipe_clk);
 s.mode=TYPEC_DP_STATE_D;
 assert(dwc3_qcom_mux_set(&m,&s)==0 && !q.utmi_pipe_clk);
 }
 puts("PASS: guarded and legacy mux paths; DP-tagged safe/USB states; C/E UTMI selection; same-state notification; live DP mode preservation; disconnect restoration; deferred selection; PM error propagation; initial two-lane DP");
}
'''
(p/'test-mux.c').write_text(code)
subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Wno-unused-parameter',str(p/'test-mux.c'),'-o',str(p/'test-mux')],check=True)
subprocess.run([str(p/'test-mux')],check=True)
