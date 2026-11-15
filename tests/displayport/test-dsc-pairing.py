#!/usr/bin/env python3
"""DSC allocation against the pingpongs a CRTC holds.

Compiles the DSC allocators from drivers/gpu/drm/msm/disp/dpu1/dpu_rm.c against a
small model of the resource manager. On SM8250 (DPU 6.0) the phone panel's DSC
pair must use the DSC blocks with its own pingpongs' indices: with DSC 0/1 fed
from pingpongs 2/3 the panel gets no frame and stays grey. That happens when
DisplayPort still holds pingpongs 0/1 in the commit that enables the panel.
Other DPU versions must keep the even/odd rule unchanged.
"""
from pathlib import Path
import re, subprocess, sys, tempfile

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} KERNEL_CHECKOUT")
src = (Path(sys.argv[1]).resolve() / 'drivers/gpu/drm/msm/disp/dpu1/dpu_rm.c').read_text()

def extract(name):
    m = re.search(r'^static (?:inline )?(?:int|bool|void) ' + name + r'\(', src, re.M)
    assert m, name
    b = src.index('{', m.start()); end = b + 1; depth = 1
    while depth:
        depth += (src[end] == '{') - (src[end] == '}'); end += 1
    return src[m.start():end] + '\n'

code = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DPU_ERROR(...) do { } while (0)
#ifndef ENAVAIL
#define ENAVAIL 119
#endif
enum { PINGPONG_0 = 1, PINGPONG_MAX = PINGPONG_0 + 6, DSC_0 = 1, DSC_MAX = DSC_0 + 4 };
struct dpu_hw_blk { int unused; };
struct dpu_rm {
	struct dpu_hw_blk *dsc_blks[DSC_MAX - DSC_0];
	bool has_legacy_ctls;
	bool dsc_pp_same_index;
};
struct dpu_global_state {
	uint32_t pingpong_to_crtc_id[PINGPONG_MAX - PINGPONG_0];
	uint32_t dsc_to_crtc_id[DSC_MAX - DSC_0];
};
struct msm_display_topology { uint32_t num_dsc, num_intf; };
'''
for name in ('reserved_by_other', '_dpu_rm_pingpong_next_index', '_dpu_rm_pingpong_dsc_check',
             '_dpu_rm_dsc_alloc', '_dpu_rm_dsc_alloc_pair'):
    code += extract(name)
code += r'''
#define PANEL 95
#define DP 96
static struct dpu_hw_blk blk;
static struct dpu_rm rm = { { &blk, &blk, &blk, &blk } };
static struct dpu_global_state gs;

static void hold(uint32_t crtc, int first, int count)
{
	for (int i = first; i < first + count; i++)
		gs.pingpong_to_crtc_id[i] = crtc;
}

static int dsc_of(uint32_t crtc, int i) { return gs.dsc_to_crtc_id[i] == crtc; }

int main(void)
{
	struct msm_display_topology pair = { 2, 1 }, single = { 1, 1 };

	rm.dsc_pp_same_index = true; /* DPU 6.0 */

	/* DisplayPort still holds pingpongs 0/1; the panel got 2/3. */
	memset(&gs, 0, sizeof(gs)); hold(DP, 0, 2); hold(PANEL, 2, 2);
	assert(_dpu_rm_dsc_alloc_pair(&rm, &gs, PANEL, &pair) == 0);
	if (!dsc_of(PANEL, 2) || !dsc_of(PANEL, 3) || dsc_of(PANEL, 0) || dsc_of(PANEL, 1)) {
		printf("FAIL: pingpongs 2/3 got DSC %d%d%d%d (want 0011)\n",
		       dsc_of(PANEL, 0), dsc_of(PANEL, 1), dsc_of(PANEL, 2), dsc_of(PANEL, 3));
		return 1;
	}

	/* The usual case keeps DSC 0/1. */
	memset(&gs, 0, sizeof(gs)); hold(PANEL, 0, 2);
	assert(_dpu_rm_dsc_alloc_pair(&rm, &gs, PANEL, &pair) == 0);
	assert(dsc_of(PANEL, 0) && dsc_of(PANEL, 1) && !dsc_of(PANEL, 2));

	/* One DSC on pingpong 2 takes DSC 2 instead of failing. */
	memset(&gs, 0, sizeof(gs)); hold(DP, 0, 2); hold(PANEL, 2, 1);
	if (_dpu_rm_dsc_alloc(&rm, &gs, PANEL, &single) || !dsc_of(PANEL, 2)) {
		puts("FAIL: a single DSC for pingpong 2 was not found");
		return 1;
	}

	/* Other DPUs keep the even/odd rule, and a single DSC that does not fit fails as before. */
	rm.dsc_pp_same_index = false;
	memset(&gs, 0, sizeof(gs)); hold(DP, 0, 2); hold(PANEL, 2, 2);
	assert(_dpu_rm_dsc_alloc_pair(&rm, &gs, PANEL, &pair) == 0);
	assert(dsc_of(PANEL, 0) && dsc_of(PANEL, 1));
	memset(&gs, 0, sizeof(gs)); hold(DP, 0, 3); hold(PANEL, 3, 1);
	if (_dpu_rm_dsc_alloc(&rm, &gs, PANEL, &single) != -ENAVAIL) {
		puts("FAIL: other DPUs changed: a single DSC for pingpong 3 no longer fails on DSC 0");
		return 1;
	}

	puts("PASS: on DPU 6.0 DSC n pairs with pingpong n, also when DisplayPort holds pingpongs 0/1; other DPUs keep even/odd pairing");
	return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p = Path(d); (p / 't.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Wno-unused-parameter',
                    str(p / 't.c'), '-o', str(p / 't')], check=True)
    sys.exit(subprocess.run([str(p / 't')]).returncode)
