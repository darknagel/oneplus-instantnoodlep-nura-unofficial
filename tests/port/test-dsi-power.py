"""Exercise the actual driver's power paths with mocked MMIO and lock status."""
from pathlib import Path
import re, subprocess, sys, tempfile

root = Path(sys.argv[1]).resolve()
scratch = tempfile.TemporaryDirectory(prefix="dsi-power-")
dest = Path(scratch.name)
source = (root / 'drivers/gpu/drm/msm/dsi/phy/dsi_phy_7nm.c').read_text()
names = ['dsi_pll_7nm_lock_status', 'dsi_pll_disable_pll_bias',
         'dsi_pll_enable_pll_bias', 'dsi_pll_cmn_clk_cfg1_update',
         'dsi_pll_disable_global_clk', 'dsi_pll_enable_global_clk',
         'dsi_pll_phy_dig_reset', 'dsi_pll_7nm_vco_prepare',
         'dsi_pll_disable_sub', 'dsi_pll_7nm_vco_unprepare',
         'dsi_phy_hw_v4_0_is_pll_on', 'dsi_phy_hw_v4_0_config_lpcdrx',
         'dsi_phy_hw_v4_0_lane_settings', 'dsi_7nm_phy_enable', 'dsi_7nm_phy_disable']

def extract(name):
    match = re.search(r'static [^;{}]+?\b' + name + r'\([^;{}]*\)\n\{', source)
    assert match, name
    pos = match.end(); depth = 1
    while depth:
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    return source[match.start():pos]

prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <limits.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint8_t u8;
#define __iomem
#define BIT(n) (1U << (n))
#include "dsi_phy_7nm.xml.h"
#define DSI_PHY_7NM_QUIRK_V4_0 BIT(0)
#define DSI_PHY_7NM_QUIRK_V4_1 BIT(1)
#define DSI_PHY_7NM_QUIRK_V4_2 BIT(2)
#define DSI_PHY_7NM_QUIRK_V4_3 BIT(3)
#define DSI_PHY_7NM_QUIRK_V5_2 BIT(4)
#define DSI_PHY_7NM_QUIRK_V7_2 BIT(5)
struct clk_hw { int unused; };
struct timing {
 u32 hs_exit, clk_prepare, hs_rqst, clk_zero, clk_trail, hs_zero, hs_prepare, hs_trail;
 struct { u32 clk_pre, clk_post; } shared_timings;
};
struct msm_dsi_phy_cfg { u32 quirks; };
struct msm_dsi_phy {
 void *base, *pll_base, *lane_base;
 int id; bool pll_on, cphy_mode;
 struct clk_hw *vco_hw;
 struct msm_dsi_phy_cfg *cfg;
 struct timing timing;
};
#define msm_dsi_dphy_timing timing
struct msm_dsi_phy_clk_request { unsigned long bitclk_rate; };
struct dsi_pll_7nm {
 struct clk_hw clk_hw;
 struct msm_dsi_phy *phy;
 u64 vco_current_rate;
 int pll_enable_cnt, pll_enable_lock, pclk_mux_lock;
 struct dsi_pll_7nm *slave;
};
#define to_pll_7nm(x) ((struct dsi_pll_7nm *)((char *)(x) - offsetof(struct dsi_pll_7nm, clk_hw)))
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags))
#define WARN_ON(x) assert(!(x))
#define DRM_DEV_ERROR_RATELIMITED(...) assert(!"reference underflow")
#define DRM_DEV_ERROR(...) ((void)0)
#define pr_warn(...) assert(!"unexpected PHY/PLL ordering warning")
#define pr_err(...) ((void)0)
#define pr_info_ratelimited(...) ((void)0)
#define DBG(...) ((void)0)
#define ndelay(x) ((void)(x))
#define udelay(x) ((void)(x))
#define wmb() ((void)0)
#define mb() ((void)0)
static u32 readl(const void *p) { return *(const u32 *)p; }
static void writel(u32 value, void *p) { *(u32 *)p=value; }
#define readl_poll_timeout_atomic(addr, value, cond, delay, timeout) \
 ((void)(delay), (void)(timeout), (value)=readl(addr), (cond) ? 0 : -ETIMEDOUT)
static int injected_usecase_error;
static int msm_dsi_cphy_timing_calc_v4(struct timing *t, struct msm_dsi_phy_clk_request *r) { return 0; }
static int msm_dsi_dphy_timing_calc_v4(struct timing *t, struct msm_dsi_phy_clk_request *r) { return 0; }
static int dsi_7nm_set_usecase(struct msm_dsi_phy *phy) { return injected_usecase_error; }
static void dsi_7nm_phy_disable(struct msm_dsi_phy *phy);
'''
tests = r'''
struct fixture {
 struct dsi_pll_7nm pll;
 struct msm_dsi_phy phy;
 struct msm_dsi_phy_cfg cfg;
 u32 regs[1024], pll_regs[1024], lanes[1024];
};
static void setup(struct fixture *f) {
 memset(f, 0, sizeof(*f));
 f->pll.phy=&f->phy;
 f->phy.vco_hw=&f->pll.clk_hw;
 f->phy.base=f->regs; f->phy.pll_base=f->pll_regs; f->phy.lane_base=f->lanes;
 f->phy.cfg=&f->cfg;
 f->cfg.quirks=DSI_PHY_7NM_QUIRK_V4_0;
 writel(1, f->phy.base + REG_DSI_7nm_PHY_CMN_PHY_STATUS);
}
static u32 ctrl(struct fixture *f) { return readl(f->phy.base + REG_DSI_7nm_PHY_CMN_CTRL_0); }
static void set_lock(struct fixture *f, bool locked) {
 writel(locked, f->phy.pll_base + REG_DSI_7nm_PHY_PLL_COMMON_STATUS_ONE);
}
static void check_stopped(struct fixture *f, int refs, u32 power) {
 assert(f->pll.pll_enable_cnt == refs);
 assert((ctrl(f) & 0x60) == power);
 assert(!readl(f->phy.base + REG_DSI_7nm_PHY_CMN_PLL_CNTRL));
 assert(!f->phy.pll_on);
}
int main(void) {
 struct fixture a,b;
 struct msm_dsi_phy_clk_request request={.bitclk_rate=1231855224};
 setup(&a);
 for (int i=0;i<3;i++) {
  assert(dsi_pll_7nm_vco_prepare(&a.pll.clk_hw)==-ETIMEDOUT);
  check_stopped(&a,0,0);
 }
 puts("PASS: repeated standalone lock failures release refs and stop PLL");
 setup(&a); setup(&b); a.pll.slave=&b.pll;
 for (int i=0;i<3;i++) {
  assert(dsi_pll_7nm_vco_prepare(&a.pll.clk_hw)==-ETIMEDOUT);
  check_stopped(&a,0,0); check_stopped(&b,0,0);
 }
 puts("PASS: bonded lock failures release master and slave refs");
 setup(&a);
 set_lock(&a,true);
 assert(dsi_pll_7nm_vco_prepare(&a.pll.clk_hw)==0);
 assert(a.pll.pll_enable_cnt==1 && (ctrl(&a)&0x60)==0x60);
 dsi_pll_7nm_vco_unprepare(&a.pll.clk_hw);
 check_stopped(&a,0,0);
 puts("PASS: early successful prepare/unprepare balances digital power");
 setup(&a); setup(&b); a.pll.slave=&b.pll;
 assert(dsi_7nm_phy_enable(&a.phy,&request)==0);
 assert(dsi_7nm_phy_enable(&b.phy,&request)==0);
 for (int i=0;i<3;i++) {
  assert(dsi_pll_7nm_vco_prepare(&a.pll.clk_hw)==-ETIMEDOUT);
  check_stopped(&a,1,0x60); check_stopped(&b,1,0x60);
 }
 puts("PASS: failed PLL startup preserves native master/slave PHY references");
 dsi_pll_enable_pll_bias(&a.pll); dsi_pll_disable_pll_bias(&a.pll);
 assert(a.pll.pll_enable_cnt==1 && ctrl(&a)==0x7f);
 set_lock(&a,true);
 assert(dsi_pll_7nm_vco_prepare(&a.pll.clk_hw)==0);
 assert(a.pll.pll_enable_cnt==2 && b.pll.pll_enable_cnt==2);
 dsi_pll_7nm_vco_unprepare(&a.pll.clk_hw);
 check_stopped(&a,1,0x60); check_stopped(&b,1,0x60);
 dsi_7nm_phy_disable(&a.phy); dsi_7nm_phy_disable(&b.phy);
 check_stopped(&a,0,0); check_stopped(&b,0,0);
 assert(ctrl(&a)==0 && ctrl(&b)==0);
 puts("PASS: temporary reads and normal clock stops preserve live PHY; PHY disable releases it");
 setup(&a);
 injected_usecase_error=-EINVAL;
 assert(dsi_7nm_phy_enable(&a.phy,&request)==-EINVAL);
 check_stopped(&a,0,0); assert(ctrl(&a)==0);
 puts("PASS: native PHY setup failure releases acquired power reference");
 return 0;
}
'''
cfile = dest / 'power-tests.c'
cfile.write_text(prefix + '\n\n'.join(extract(name) for name in names) + tests)
subprocess.run(['clang', '-std=gnu11', '-O2', '-Wall', '-Werror',
                '-Wno-unused-variable', '-Wno-unused-but-set-variable',
                '-I' + str(Path(sys.argv[2]).resolve()), str(cfile), '-o', str(dest / 'power-tests')], check=True)
subprocess.run([str(dest / 'power-tests')], check=True)
