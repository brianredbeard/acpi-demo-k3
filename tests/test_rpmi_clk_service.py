#!/usr/bin/env python3
"""Host regression test for the K3 RPMI clock service callbacks.

Compiles the service functions from the prepared ESOS source with mocked
RT-Thread/librpmi/CCU APIs and asserts the callback contract:
  - set_state maps ENABLED/DISABLED to clk_prepare_enable/clk_disable_unprepare
  - bounds and legacy-id rejection before any hardware call
  - get_state_and_rate reports real is_enabled + rate, NOTSUPP when unresolved
  - rate_change_match answers exactly when the CCU rate differs
  - set_rate honors platform-exact mode, refuses ROUND_UP/DOWN, propagates
    clk_set_rate errors, never sets rate when the clock is unresolved
  - init publishes every id (stable ABI), resolved or not, as DISCRETE
    with a non-empty rate array
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'build/esos-rpmi-01'
SOURCE = BUILD / 'sources/esos/bsp/spacemit/drivers/rpmi/k3'

COMMON = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
typedef uint32_t rpmi_uint32_t;
typedef uint64_t rpmi_uint64_t;
typedef int rt_bool_t; typedef int rt_err_t; typedef int rt_int32_t; typedef long rt_size_t;
#define RT_TRUE 1
#define RT_FALSE 0
#define RT_EOK 0
#define RT_ERROR 1
#define RT_WAITING_FOREVER -1
enum rpmi_error { RPMI_SUCCESS=0, RPMI_ERR_FAILED=1, RPMI_ERR_NOTSUPP=2,
                  RPMI_ERR_INVALID_PARAM=3, RPMI_ERR_DENIED=4, RPMI_ERR_NOT_FOUND=6 };
enum rpmi_clock_state { RPMI_CLK_STATE_DISABLED=0, RPMI_CLK_STATE_ENABLED=1 };
enum rpmi_clock_rate_match { RPMI_CLK_RATE_MATCH_PLATFORM=0,
                             RPMI_CLK_RATE_MATCH_ROUND_DOWN=1,
                             RPMI_CLK_RATE_MATCH_ROUND_UP=2 };
enum rpmi_clock_type { RPMI_CLK_TYPE_DISCRETE=0, RPMI_CLK_TYPE_LINEAR=1 };
struct rpmi_clock_data {
    rpmi_uint32_t parent_id;
    rpmi_uint32_t transition_latency_ms;
    rpmi_uint32_t rate_count;
    enum rpmi_clock_type clock_type;
    const char *name;
    const rpmi_uint64_t *clock_rate_array;
};
typedef int rpmi_bool_t;
struct spacemit_rpmi_clk_config { int num_clk; struct rpmi_clock_data *clk_data; };
struct clk { const char *name; int enabled; unsigned long rate; };
static char events[128]; static int count;
static void event(char c){events[count++]=c;events[count]=0;}
static int fail_enable, fail_set_rate;
static unsigned long reported_rate = 24000000;
static struct clk twsi = {"twsi0_clk", 1, 31400000};
static struct clk sdh  = {"sdh0_clk",  0, 49152000};
static int clk_prepare_enable(struct clk *c){
    event('E');
    if (fail_enable) return -1;
    c->enabled = 1; return 0;
}
static void clk_disable_unprepare(struct clk *c){ event('D'); c->enabled = 0; }
static rt_bool_t spacemit_ccu_clk_is_enabled(struct clk *c){ return c->enabled; }
static unsigned long clk_get_rate(struct clk *c){ (void)c; return reported_rate; }
static int clk_set_rate(struct clk *c, unsigned long r){
    event('S');
    if (fail_set_rate) return -1;
    c->rate = r; reported_rate = r; return 0;
}
static struct clk *spacemit_ccu_get_clk_by_name(const char *n){
    if (!strcmp(n,"twsi0_clk")) return &twsi;
    if (!strcmp(n,"sdh0_clk")) return &sdh;
    return NULL;
}
static void rt_kprintf(const char *f, ...) { (void)f; }
/* clk_hw shims: set_rate gating probes hw->init->ops->set_rate.
 * twsi (mux/div clock) HAS set_rate; sdh and everything else do not,
 * exercising the no-propagation guard. */
struct clk_ops { int (*set_rate)(void *, unsigned long, unsigned long); };
struct clk_init_data { const char *name; const struct clk_ops *ops; };
struct clk_hw { const struct clk_init_data *init; };
static int stub_set_rate(void *hw, unsigned long r, unsigned long p){ (void)hw;(void)r;(void)p; return 0; }
static const struct clk_ops ops_with_set_rate = { stub_set_rate };
static const struct clk_ops ops_gate_only = { NULL };
static const struct clk_init_data twsi_init = { "twsi0_clk", &ops_with_set_rate };
static const struct clk_init_data sdh_init = { "sdh0_clk", &ops_gate_only };
static struct clk_hw twsi_hw = { &twsi_init }, sdh_hw = { &sdh_init };
static struct clk_hw *__clk_get_hw(struct clk *c){
    return c == &twsi ? &twsi_hw : &sdh_hw;
}
typedef uint64_t rt_uint64_t;
'''

TESTS = r'''
static int checks, failed;
static void require(int cond, const char *what){
    checks++;
    if (!cond) { failed++; printf("FAIL: %s\n", what); }
}
int main(void){
    struct spacemit_rpmi_clk_config cfg;
    /* init: every id published, resolved or not, DISCRETE, rate_count >= 1 */
    require(_k3_os0_clock_init(&cfg) == 0, "init succeeds");
    require(cfg.num_clk == 13, "config carries the full id count");
    require(cfg.clk_data != NULL, "config carries the data array");
    for (int i = 0; i < 13; i++) {
        char what[64];
        snprintf(what, sizeof what, "id %d published", i);
        require(cfg.clk_data[i].name != NULL, what);
        snprintf(what, sizeof what, "id %d discrete with nonempty rates", i);
        require(cfg.clk_data[i].clock_type == RPMI_CLK_TYPE_DISCRETE
                && cfg.clk_data[i].clock_rate_array != NULL, what);
    }
    require(!strcmp(cfg.clk_data[1].name, "twsi0_clk"), "id 1 name is twsi0_clk");
    require(!strcmp(cfg.clk_data[0].name, "rproc_clk"), "id 0 stays the legacy stub");
    /* set_state contract */
    count=0; events[0]=0;
    require(spacemit_set_state(NULL, 1, RPMI_CLK_STATE_ENABLED)==RPMI_SUCCESS, "twsi0 enable succeeds");
    require(twsi.enabled && events[0]=='E', "enable goes through clk_prepare_enable");
    count=0; events[0]=0;
    require(spacemit_set_state(NULL, 1, RPMI_CLK_STATE_DISABLED)==RPMI_SUCCESS, "twsi0 disable succeeds");
    require(!twsi.enabled && events[0]=='D', "disable goes through clk_disable_unprepare");
    require(spacemit_set_state(NULL, 13, RPMI_CLK_STATE_ENABLED)==RPMI_ERR_INVALID_PARAM,
            "out-of-range id rejected before hardware");
    require(spacemit_set_state(NULL, 0, RPMI_CLK_STATE_ENABLED)==RPMI_SUCCESS,
            "legacy rproc id is a no-op stub");
    count=0; events[0]=0;
    require(spacemit_set_state(NULL, 9, RPMI_CLK_STATE_ENABLED)==RPMI_ERR_NOTSUPP,
            "unresolved emac0_bus_clk returns NOTSUPP");
    require(count==0, "unresolved clock never touches hardware");
    fail_enable=-1;
    require(spacemit_set_state(NULL, 5, RPMI_CLK_STATE_ENABLED)==RPMI_ERR_FAILED,
            "clk_prepare_enable failure maps to RPMI_ERR_FAILED");
    fail_enable=0;
    require(spacemit_set_state(NULL, 1, 99)==RPMI_ERR_INVALID_PARAM, "invalid state rejected");
    /* get_state_and_rate contract */
    { enum rpmi_clock_state st; rpmi_uint64_t rate;
      twsi.enabled = 1; reported_rate = 31400000;
      require(spacemit_get_state_and_rate(NULL, 1, &st, &rate)==RPMI_SUCCESS, "state read ok");
      require(st==RPMI_CLK_STATE_ENABLED, "state read from hardware gate");
      require(rate==31400000, "rate read via clk_get_rate");
      require(spacemit_get_state_and_rate(NULL, 9, &st, &rate)==RPMI_ERR_NOTSUPP,
              "unresolved clock state is NOTSUPP");
      require(spacemit_get_state_and_rate(NULL, 13, &st, &rate)==RPMI_ERR_INVALID_PARAM,
              "state read bounds");
    }
    /* rate_change_match contract */
    reported_rate = 31400000;
    require(spacemit_rate_change_match(NULL, 1, 40000000)==RT_TRUE,
            "different rate requires change");
    require(spacemit_rate_change_match(NULL, 1, 31400000)==RT_FALSE,
            "same rate requires no change");
    require(spacemit_rate_change_match(NULL, 9, 40000000)==RT_FALSE,
            "unresolved clock never requires a change");
    require(spacemit_rate_change_match(NULL, 13, 40000000)==RT_FALSE,
            "out-of-range id never requires a change");
    /* set_rate contract */
    count=0; events[0]=0;
    require(spacemit_set_rate(NULL, 1, RPMI_CLK_RATE_MATCH_PLATFORM, 40000000, NULL)==RPMI_SUCCESS,
            "platform-mode set_rate succeeds");
    require(events[0]=='S' && twsi.rate==40000000, "set_rate reaches clk_set_rate on the right clock");
    require(spacemit_set_rate(NULL, 1, RPMI_CLK_RATE_MATCH_ROUND_UP, 50000000, NULL)==RPMI_ERR_NOTSUPP,
            "ROUND_UP refused with NOTSUPP");
    require(spacemit_set_rate(NULL, 1, RPMI_CLK_RATE_MATCH_ROUND_DOWN, 50000000, NULL)==RPMI_ERR_NOTSUPP,
            "ROUND_DOWN refused with NOTSUPP");
    require(spacemit_set_rate(NULL, 13, RPMI_CLK_RATE_MATCH_PLATFORM, 1, NULL)==RPMI_ERR_INVALID_PARAM,
            "set_rate bounds");
    require(spacemit_set_rate(NULL, 9, RPMI_CLK_RATE_MATCH_PLATFORM, 1, NULL)==RPMI_ERR_NOTSUPP,
            "unresolved set_rate is NOTSUPP");
    count=0; events[0]=0; fail_set_rate=-1;
    require(spacemit_set_rate(NULL, 1, RPMI_CLK_RATE_MATCH_PLATFORM, 2000000, NULL)==RPMI_ERR_DENIED,
            "clk_set_rate failure maps to RPMI_ERR_DENIED");
    fail_set_rate=0;
    /* gate-only clock (sdh0, no .set_rate op): refused before hardware */
    count=0; events[0]=0;
    require(spacemit_set_rate(NULL, 5, RPMI_CLK_RATE_MATCH_PLATFORM, 2000000, NULL)==RPMI_ERR_NOTSUPP,
            "gate-only clock set_rate refused without clk_set_rate");
    require(count==0, "gate-only set_rate never reaches clk_set_rate");
    /* set_rate_recalc contract */
    reported_rate = 25000000;
    { rpmi_uint64_t nr = 0;
      require(spacemit_set_rate_recalc(NULL, 1, 0, &nr)==RPMI_SUCCESS, "recalc ok on resolved clock");
      require(nr==25000000, "recalc reports resulting CCU rate");
      require(spacemit_set_rate_recalc(NULL, 9, 0, &nr)==RPMI_ERR_NOTSUPP, "recalc unresolved is NOTSUPP");
    }
    printf("%s: %d checks, %d failures\n", failed ? "FAILED" : "PASS", checks, failed);
    return failed != 0;
}
'''

def extract(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]

import unittest


class RpmiClockServiceTests(unittest.TestCase):
    """Compiles the service callbacks against mocked APIs and runs them.
    Requires a prepared ESOS build (build/esos-rpmi-01 by default, or the
    directory given as the script's argv[1])."""

    def test_service_callbacks(self):
        if not (SOURCE / 'k3-os0_clk.c').exists():
            self.skipTest(f'prepared ESOS sources not found under {SOURCE}; '
                          'run build_esos.py first')
        source = (SOURCE / 'k3-os0_clk.c').read_text()
        ids_header = (SOURCE / 'k3-rpmi-clk-ids.h').read_text()

        resolve = extract(source, 'static struct clk *k3_rpmi_clk_resolve(',
                          'static rt_int32_t _k3_os0_clock_init(void *priv)')
        init_func = extract(source, 'static rt_int32_t _k3_os0_clock_init(void *priv)',
                            'static enum rpmi_error spacemit_set_state(void *priv')
        callbacks = extract(source, 'static enum rpmi_error spacemit_set_state(void *priv',
                            '\nstatic struct rpmi_clock_platform_ops')
        entries = ('static struct k3_rpmi_clk_entry { struct clk *clk; rpmi_uint64_t rate; } k3_rpmi_clks[13];\n'
                   'static rpmi_uint64_t k3_rpmi_unresolved_rate;\n'
                   'static struct rpmi_clock_data k3_os0_clk_data[13];\n')

        program = (COMMON + '\n' + ids_header.replace('#include <', '//#include <') + '\n'
                   + entries + resolve + init_func + callbacks + TESTS)

        with tempfile.TemporaryDirectory(prefix='k3-clk-test-') as tmp:
            c = Path(tmp) / 'test.c'
            exe = Path(tmp) / 'test'
            c.write_text(program)
            build = subprocess.run(['cc', '-o', str(exe), str(c)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:4000])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('0 failures', run.stdout)


if __name__ == '__main__':
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a in ('-v',)]
    unittest.main()
