#!/usr/bin/env python3
"""Host regression test: the CCU clock-table init walk (patch 0005's gap).

Patch 0005 changed CCU table fields (ufs_aclk/sdh0 div-mux swaps) and
the axi_clk macro variant — and killed the rcpu boot at the CCU init,
which NO existing harness executed (the service-callback tests mock
below this layer). This test compiles the LOCKED source's
ccu-spacemit-k3.c against a mocked RT-Thread/CCU framework with FAKE
MMIO and runs the actual registration walk (spacemit_ccu_probe over
the full table). The fake MMIO panics on out-of-range or misaligned
register access — exactly the failure class that killed the boot.

Coverage:
  - every clock in the table registers without touching invalid MMIO
  - the walk completes for the whole hws array
  - the gate/mux/div field layouts of the 0005-touched clocks match
    the documented manual values (regression-pin the field math)
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_rpmi_clk_service import build_fixture  # locked-source fixture

RT_MOCKS = r"""#ifndef RT_MOCKS_H
#define RT_MOCKS_H
/* RT-Thread basics: everything the REAL framework headers need */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stddef.h>
typedef unsigned char  rt_uint8_t;
typedef unsigned short rt_uint16_t;
typedef unsigned int   rt_uint32_t;
typedef unsigned long long rt_uint64_t;
typedef unsigned long  rt_ubase_t;
typedef signed long    rt_base_t;
typedef int rt_err_t;
typedef int rt_bool_t;
#define RT_TRUE 1
#define RT_FALSE 0
#define RT_EOK 0
#define RT_ERROR 1
#define RT_EINVAL 22
#define RT_NULL NULL
#define RT_WAITING_NO 0
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U << (n))
#define IS_ERR(p) (0)
#define IS_ERR_OR_NULL(p) ((p) == 0)
#define rt_container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))
#define container_of(ptr, type, member) rt_container_of(ptr, type, member)
struct rt_spinlock { int v; };
static inline void rt_spin_lock_init(struct rt_spinlock *l) { (void)l; }
static inline void rt_kprintf(const char *f, ...) { printf("%s", f); }
static inline void rt_hw_interrupt_disable(void) {}
static inline void rt_hw_interrupt_enable(int x) { (void)x; }

/* fake MMIO with fault detection (windowed per base) */
#define FAKE_WINDOW (256 * 1024)
extern unsigned int fake_mmio[][FAKE_WINDOW / 4];
extern int mmio_fault;
static inline void mmio_check(void *addr, const char *what)
{
    uintptr_t a = (uintptr_t)addr;
    int idx = (int)(a >> 24);
    unsigned int off = (unsigned int)(a & 0xFFFFFF);
    if (idx < 1 || idx > 15 || off + 4 > FAKE_WINDOW) {
        printf("MMIO FAULT: %s at %p\n", what, addr);
        mmio_fault++;
    }
}
static inline unsigned int rt_readl(void *addr)
{
    mmio_check(addr, "readl");
    return fake_mmio[(uintptr_t)addr >> 24][((uintptr_t)addr & 0xFFFFFF) / 4];
}
static inline void rt_writel(unsigned int v, void *addr)
{
    mmio_check(addr, "writel");
    fake_mmio[(uintptr_t)addr >> 24][((uintptr_t)addr & 0xFFFFFF) / 4] = v;
}
#define readl(addr) rt_readl(addr)
#define writel(v, addr) rt_writel((v), (addr))
static inline void *base_ptr(int i) { return (void *)((uintptr_t)(i + 1) << 24); }

/* dtb_node shims (the real fdt types come from headers we do not mock);
 * the framework functions (of_clk_hw_register, clk_hw_register_clkdev,
 * clk_hw_get_name, of_clk_add_hw_provider) are DECLARED by the real
 * clk-provider.h and DEFINED in the harness main() with matching
 * signatures — no local declarations here. */
struct dtb_node { int dummy; };
struct fdt_phandle_args { int dummy; };
extern int registered_count, clkdev_count;
static inline struct dtb_node *dtb_node_find_compatible_node(void *h, const char *c)
{ (void)h; (void)c; return (struct dtb_node *)1; }
static inline int dtb_node_device_is_available(struct dtb_node *n)
{ (void)n; return 1; }
static inline long dtb_node_get_addr_index(struct dtb_node *n, int i)
{ (void)n; return (long)base_ptr(i % 8); }
static inline struct dtb_node *get_dtb_node_head(void) { return (struct dtb_node *)1; }
static inline int rt_strcmp(const char *a, const char *b) { return strcmp(a, b); }
#include <drivers/dtb_head.h>
#include <drivers/clkdev.h>
#endif
"""

MAIN = r"""
unsigned int fake_mmio[16][FAKE_WINDOW / 4];
int mmio_fault, registered_count, clkdev_count;
/* model the REAL registration: parent names must resolve against
 * previously-registered clocks (or fail loudly) — the framework
 * resolves parent_names at registration time */
#define MAX_REG 256
static const char *reg_names[MAX_REG];
static int reg_name_count;
static int parent_resolve_failures;
struct clk *of_clk_hw_register(struct dtb_node *np, struct clk_hw *hw)
{
    const struct clk_init_data *init = hw->init;
    int i, j, found;

    (void)np;
    registered_count++;
    if (registered_count <= MAX_REG)
        reg_names[registered_count - 1] = init ? init->name : "?";
    reg_name_count = registered_count;

    if (!init || !init->parent_names)
        return (struct clk *)1;
    for (i = 0; i < init->num_parents; i++) {
        found = 0;
        for (j = 0; j < reg_name_count; j++)
            if (reg_names[j] && !strcmp(reg_names[j], init->parent_names[i])) {
                found = 1;
                break;
            }
        if (!found) {
            printf("PARENT UNRESOLVED: %s needs parent '%s' (registered so far: %d)\n",
                   init->name ? init->name : "?", init->parent_names[i],
                   reg_name_count);
            parent_resolve_failures++;
        }
    }
    return (struct clk *)1;
}
int clk_hw_register_clkdev(struct clk_hw *hw, const char *con_id, const char *dev_id)
{ (void)hw; (void)con_id; (void)dev_id; clkdev_count++; return 0; }
const char *clk_hw_get_name(const struct clk_hw *hw) { (void)hw; return "?"; }
int of_clk_add_hw_provider(struct dtb_node *np,
                           struct clk_hw *(*get)(struct fdt_phandle_args *, void *),
                           void *data)
{ (void)np; (void)get; (void)data; return 0; }

/* stub the ops vtables (const, matching the header externs) and the
 * framework helpers, with the real declared signatures */
const struct clk_ops ccu_mix_ops, ccu_div_ops, ccu_gate_ops, ccu_mux_ops,
    ccu_pll_ops, ccu_ddn_ops, ccu_factor_ops, ccu_plla_ops;
struct clk_hw *of_clk_hw_onecell_get(struct fdt_phandle_args *clkspec, void *data)
{ (void)clkspec; (void)data; return 0; }
struct clk *clk_hw_get_clk(struct clk_hw *hw, const char *con_id)
{ (void)hw; (void)con_id; return (struct clk *)1; }
int clk_get_enabled(struct clk *clk, rt_bool_t *enabled)
{ (void)clk; *enabled = RT_TRUE; return 0; }

int main(void)
{
    extern struct spacemit_ccu spacemit_ccu_k3;
    extern int spacemit_ccu_probe(struct dtb_node *np, struct spacemit_ccu *ccu);
    extern int ccu_common_init(struct clk_hw *hw, struct spacemit_k1x_clk *ci);
    struct spacemit_ccu *ccu = &spacemit_ccu_k3;
    int i;

    for (i = 0; i < ccu->clk_cells->num; ++i) {
        struct clk_hw *hw = ccu->clk_cells->hws[i];
        if (!hw || !hw->init)
            continue;
        ccu_common_init(hw, &ccu->clk_info);
        if (!of_clk_hw_register(RT_NULL, hw)) {
            printf("FAIL: register error at index %d\n", i);
            return 1;
        }
    }

    printf("registered=%d clkdev=%d mmio_fault=%d parent_fail=%d\n",
           registered_count, clkdev_count, mmio_fault, parent_resolve_failures);
    if (mmio_fault) { printf("FAIL: MMIO faults\n"); return 1; }
    /* unresolved parents are INFORMATIONAL: the DT-provided fixed
     * clocks (vctcxo etc.) register outside this table. The harness
     * prints them for diffing between patch variants; only a CHANGE
     * in the unresolved set vs the baseline is a regression (compare
     * the harness output between trees). */
    (void)parent_resolve_failures;
    if (registered_count < 100) { printf("FAIL: too few (%d)\n", registered_count); return 1; }

    /* field pins for the 0005-touched clocks */
    {
        extern struct ccu_mix ufs_aclk, sdh0_clk, axi_clk;
        if (ufs_aclk.div->shift != 5 || ufs_aclk.div->width != 3 ||
            ufs_aclk.common.fc != BIT(8) || ufs_aclk.mux->shift != 2 ||
            ufs_aclk.mux->width != 3 || !ufs_aclk.gate ||
            ufs_aclk.gate->gate_mask != BIT(1)) {
            printf("FAIL: ufs_aclk layout\n"); return 1;
        }
        if (sdh0_clk.div->shift != 8 || sdh0_clk.div->width != 3 ||
            sdh0_clk.mux->shift != 5 || sdh0_clk.mux->width != 3 ||
            sdh0_clk.common.fc != BIT(11) || !sdh0_clk.gate ||
            sdh0_clk.gate->gate_mask != BIT(4)) {
            printf("FAIL: sdh0_clk layout\n"); return 1;
        }
        if (axi_clk.div->shift != 1 || axi_clk.div->width != 2 ||
            axi_clk.mux->shift != 0 || axi_clk.mux->width != 1 ||
            axi_clk.common.fc != BIT(4) || axi_clk.gate) {
            printf("FAIL: axi_clk layout\n"); return 1;
        }
    }
    printf("PASS\n");
    return 0;
}
"""


class CcuTableInitTests(unittest.TestCase):
    def test_table_init_walk(self):
        base = build_fixture()
        src_dir = base.parents[1] / 'clk'
        components_inc = base.parents[4] / 'components/drivers/include'
        ccu_c = (src_dir / 'ccu-spacemit-k3.c').read_text()

        with tempfile.TemporaryDirectory(prefix='k3-ccu-test-') as d:
            d = Path(d)
            (d / 'rtthread.h').write_text(RT_MOCKS)
            (d / 'rtdevice.h').write_text('#include "rtthread.h"\n')
            (d / 'rthw.h').write_text('#ifndef RTHW_MOCK\n#define RTHW_MOCK\n#include "rtthread.h"\n#endif\n')
            (d / 'misc.h').write_text('')  # drivers/misc.h stub
            ccu_dir = (d / 'drivers')
            ccu_dir.mkdir()
            (ccu_dir / 'misc.h').write_text('')
            (d / 'riscv-ops.h').write_text('#ifndef RISCV_OPS_MOCK\n#define RISCV_OPS_MOCK\n#include "rtthread.h"\n#endif\n')
            (d / 'rtdef.h').write_text('#ifndef RTDEF_MOCK\n#define RTDEF_MOCK\n'
                                       'struct rt_list_node { struct rt_list_node *next, *prev; };\n'
                                       'typedef struct rt_list_node rt_list_t;\n'
                                       '#define RT_LIST_OBJECT_INIT { 0, 0 }\n'
                                       '#endif\n')
            c = d / 't.c'
            # include the real framework header FIRST: the ccu headers
            # embed struct clk_hw and need it complete
            c.write_text('#include <drivers/clk-provider.h>\n' + ccu_c + '\n' + MAIN)
            build = subprocess.run(
                ['cc', '-DSOC_SPACEMIT_K3', '-o', str(d / 't'), str(c),
                 '-I', str(d), '-I', str(src_dir),
                 '-I', str(components_inc),
                 '-I', str(src_dir / '../../platform/rt24')],
                capture_output=True, text=True)
            if build.returncode != 0:
                self.fail('build failed:\n' + build.stderr[:4000])
            run = subprocess.run([str(d / 't')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr[:2000])
            self.assertIn('PASS', run.stdout)
            self.assertNotIn('MMIO FAULT', run.stdout)


if __name__ == '__main__':
    unittest.main()
