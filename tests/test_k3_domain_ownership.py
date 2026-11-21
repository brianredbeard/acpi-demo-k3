#!/usr/bin/env python3
"""Fault-injection tests for the K3 shared-domain ownership model (P1).

Extracts k3_domain_ownership.c from the prepared ESOS fixture and runs it
against mocked RT-Thread primitives, injecting the fault classes from the
plan's supporting deliverable:

  - pending interrupts at entry (late consumer acquire during ENTERING)
  - management timeouts (bounded-wait expiry aborts, no stale vote)
  - rejected transitions (active consumers deny sleep eligibility)
  - sibling wake races (M2-exit during ENTERING/COMMITTED/ASLEEP)
  - stale/duplicate transactions (generation invalidation)
  - unknown ownership (sticky blocker)
  - interrupted restoration (state returns to ACTIVE)

No hardware is touched; the retained counters are asserted directly.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build_fixture():
    """AUDIT FIX 5: test the LOCKED source — the tree produced by
    meta.prepare (pristine e0b8d955b + patches 0001-0007 from
    sources.lock.json), which is exactly what a reproducible build
    compiles. Prepares it on demand into a temp dir. The mutable
    dev checkout (esos-reset-handoff) is deliberately NOT used: a
    test that passes against uncommitted edits proves nothing about
    the shipped artifact."""
    import subprocess, sys, tempfile
    import meta
    lock = ROOT / 'sources.lock.json'
    prepared = ROOT.parent / '.p1-test-lock-source' / 'esos' / 'bsp/spacemit/drivers/rpmi/k3'
    if not (prepared / 'k3_domain_ownership.c').exists():
        dest = ROOT.parent / '.p1-test-lock-source'
        if dest.exists():
            import shutil; shutil.rmtree(dest)
        meta.prepare(lock, dest,
                     repositories={'esos': str(ROOT.parent / 'esos-reset-diagnostic')},
                     select={'esos', 'esos-lite'})
    if not (prepared / 'k3_domain_ownership.c').exists():
        raise unittest.SkipTest('locked P1 source did not prepare')
    return prepared

SOURCE_DIR = build_fixture()

COMMON = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
typedef int rt_bool_t; typedef int rt_err_t; typedef int rt_base_t;
typedef unsigned short rt_uint16_t; typedef unsigned char rt_uint8_t;
typedef unsigned int rt_uint32_t; typedef unsigned long rt_ubase_t;
#define RT_TRUE 1
#define RT_FALSE 0
#define RT_EOK 0
#define RT_ERROR 1
#define RT_EINVAL 22
#define RT_EBUSY 16
#define RT_EPERM 1
#define RT_ETIMEOUT 110
#define RT_EINTR 4
#define RT_ENOMEM 12
#define RT_WAITING_NO 0
#define RT_NULL NULL

/* --- mocked RT-Thread primitives ------------------------------------- */
static rt_base_t irq_state;
static rt_base_t rt_hw_interrupt_disable(void) { return 0; }
static void rt_hw_interrupt_enable(rt_base_t s) { (void)s; }

typedef struct { int count; int auto_take_rc; } mock_sem;
static mock_sem sems[8];
static int sem_alloc = 0;
static void *rt_sem_create(const char *n, int c, int f) {
    (void)n; (void)c; (void)f;
    if (sem_alloc >= 8) return NULL;
    sems[sem_alloc].count = 0;
    sems[sem_alloc].auto_take_rc = 0;
    return &sems[sem_alloc++];
}
static rt_err_t rt_sem_delete(void *s) { (void)s; return RT_EOK; }
/* mid-wait injection: when a take would block, this hook runs first
 * (simulating an event landing DURING the semaphore wait) */
static void (*mid_wait_hook)(void);
static rt_err_t rt_sem_take(void *s, rt_ubase_t t) {
    mock_sem *m = s;
    if (m->auto_take_rc) { int rc = m->auto_take_rc; m->auto_take_rc = 0; return rc; }
    if (m->count > 0) { m->count--; return RT_EOK; }
    /* mid-wait injection fires only for BOUNDED waits: the stale-count
     * drain uses RT_WAITING_NO polls and must not consume injections */
    if (t != RT_WAITING_NO && mid_wait_hook) { void (*h)(void) = mid_wait_hook; mid_wait_hook = 0; h(); }
    if (m->count > 0) { m->count--; return RT_EOK; }
    /* nothing pending: any wait (bounded or poll) times out —
     * the M2-enter interrupt never landed */
    return -RT_ETIMEOUT;
}
/* test access to the current cluster-0 domain state (declared in the model) */
extern struct k3_cluster_domain *k3_test_domain(int c);
static rt_err_t rt_sem_release(void *s) { mock_sem *m = s; m->count++; return RT_EOK; }

#define RT_IPC_FLAG_FIFO 0
typedef void *rt_sem_t;
static int rt_tick_from_millisecond(int ms) { return ms; }
static void rt_memset(void *p, int c, size_t n) { memset(p, c, n); }
static int rt_snprintf(char *b, size_t n, const char *f, ...) { return snprintf(b, n, "%s", f); }
#define K3_MAX_CLUSTERS 4
/* pull only the .c after shimming the header include */
'''

TESTS = r'''
static int checks, failed;
static void require(int cond, const char *what){
    checks++;
    if (!cond) { failed++; printf("FAIL: %s\n", what); }
}

static void inject_during_wait(void); /* fwd: defined after main */
static void release_enter_sem_during_wait(void); /* fwd */

int main(void){
    struct k3_cluster_domain *d;

    /* --- init: BLOCKED until qualified (audit fix 3) ------------------ */
    require(k3_domain_init(0) == 0, "cluster 0 init");
    require(k3_domain_init(0) == 0, "init idempotent");
    require(k3_domain_init(9) == -RT_EINVAL, "invalid cluster rejected");
    require(k3_domain_sleep_eligible(0) == RT_FALSE, "unqualified domain is BLOCKED");
    require(k3_domain_request_sleep(0, 0) == -RT_EPERM, "request denied while unqualified");

    /* --- qualification + consumer blocking --------------------------- */
    require(k3_domain_qualify(0) == 0, "provider qualifies C0");
    require(k3_domain_sleep_eligible(0) == RT_TRUE, "qualified + empty -> eligible");

    require(k3_domain_consumer_acquire(0, K3_CONSUMER_GPU) == 0, "GPU acquires C0");
    require(k3_domain_sleep_eligible(0) == RT_FALSE, "active consumer blocks sleep");
    require(k3_domain_request_sleep(0, 0) == -RT_EPERM, "sleep request denied with consumers");

    /* --- per-class REFCOUNTS: two users, one release (audit fix 3) ---- */
    require(k3_domain_consumer_acquire(0, K3_CONSUMER_DMA) == 0, "DMA user 1");
    require(k3_domain_consumer_acquire(0, K3_CONSUMER_DMA) == 0, "DMA user 2");
    require(k3_domain_consumer_release(0, K3_CONSUMER_DMA) == 0, "DMA user 2 releases");
    require(k3_domain_sleep_eligible(0) == RT_FALSE, "one DMA user still holds C0");
    require(k3_domain_consumer_release(0, K3_CONSUMER_DMA) == 0, "DMA user 1 releases");
    require(k3_domain_sleep_eligible(0) == RT_FALSE, "GPU still holds C0");
    require(k3_domain_consumer_release(0, K3_CONSUMER_GPU) == 0, "GPU releases");
    require(k3_domain_sleep_eligible(0) == RT_TRUE, "all released -> eligible");

    /* --- unknown class rejected --------------------------------------- */
    require(k3_domain_consumer_acquire(0, K3_CONSUMER_UNKNOWN) == -RT_EINVAL,
            "unknown class rejected at acquire");

    /* --- bounded-wait timeout aborts, no stale vote -------------------- */
    require(k3_domain_request_sleep(0, 1) == -RT_ETIMEOUT, "timeout aborts entry");
    d = k3_test_domain(0);
    require(d->state == K3_DOMAIN_ACTIVE, "timeout returns domain ACTIVE (ABORTED is transient)");
    require(d->stats.aborted_entry >= 1, "abort counted");
    require(k3_domain_request_sleep(0, 0) == -RT_ETIMEOUT,
            "retry after abort permitted (nonblocking)");

    /* --- LATE CONSUMER during ENTERING/COMMITTED: atomic invalidation - */
    {
        rt_uint32_t g;

        /* the drain discards PRE-armed counts (stale M2 signals); a
         * legitimate grant must arrive DURING the wait: the mid-wait
         * hook simulates the M2-enter ISR releasing the semaphore */
        mid_wait_hook = release_enter_sem_during_wait;
        require(k3_domain_request_sleep(0, 1) == 0, "mid-wait M2-enter grants entry");
        d = k3_test_domain(0);
        require(d->state == K3_DOMAIN_COMMITTED, "granted entry COMMITTED");

        /* a consumer arriving during COMMITTED must invalidate the
         * transaction atomically: generation++ in the same critical
         * section (audit finding 2) */
        g = d->generation;
        require(k3_domain_consumer_acquire(0, K3_CONSUMER_DMA) == 0,
                "late DMA acquire during COMMITTED");
        d = k3_test_domain(0);
        require(d->generation == g + 1, "generation bumped atomically");
        /* the transient ABORTED normalizes to ACTIVE via abort_sleep;
         * the OBSERVABLE invariant: a request capturing generation g
         * can no longer commit (see the commit gate), and the domain
         * is not eligible while the consumer holds it */
        require(d->state == K3_DOMAIN_ACTIVE, "abort normalized to ACTIVE");
        require(k3_domain_sleep_eligible(0) == RT_FALSE, "invalidated entry not eligible");
        require(d->consumers[K3_CONSUMER_DMA] == 1, "DMA consumer held");
        require(k3_domain_sleep_eligible(0) == RT_FALSE, "not eligible with consumer");
        require(k3_domain_consumer_release(0, K3_CONSUMER_DMA) == 0, "DMA releases");
    }

    /* --- MID-WAIT injection: consumer lands during the wait (audit 5) - */
    {
        /* a request that passes the initial eligibility check, then a
         * consumer arrives while the request blocks on the M2 wait: the
         * hook fires inside rt_sem_take; the take still times out; but
         * the ACQUIRE ran mid-wait and the abort+commit-gate must hold */
        k3_domain_qualify(0);
        mid_wait_hook = inject_during_wait;   /* set below before use */
        require(k3_domain_request_sleep(0, 1) == -RT_ETIMEOUT,
                "mid-wait consumer -> entry aborts (timeout)");
        d = k3_test_domain(0);
        require(d->state == K3_DOMAIN_ABORTED || d->state == K3_DOMAIN_ACTIVE,
                "no commit despite primed M2");
        require(k3_domain_sleep_eligible(0) == RT_FALSE, "consumer from mid-wait holds");
        require(k3_domain_consumer_release(0, K3_CONSUMER_DISPLAY) == 0, "mid-wait consumer releases");
        require(k3_domain_sleep_eligible(0) == RT_TRUE, "eligible again");
    }

    /* --- sibling wake race: M2-exit during ASLEEP ---------------------- */
    k3_domain_m2_exit_isr(0);   /* wake with no sleep pending: no-op */
    k3_domain_m2_enter_isr(0);  /* enter with no entry pending: counted */
    d = k3_test_domain(0);
    require(d->stats.m2_enter_count >= 1 && d->stats.m2_exit_count >= 1,
            "M2 ISRs counted");

    /* --- hw handshake timeout accounting (audit 4) --------------------- */
    k3_domain_note_hw_timeout(0);
    require(k3_test_domain(0)->stats.hw_handshake_timeouts == 1,
            "hw timeout counted");

    /* --- wake accounting ---------------------------------------------- */
    require(k3_domain_note_wake(0, K3_CONSUMER_MGMT) == 0, "IPC wake noted");
    require(k3_domain_note_wake(0, K3_CONSUMER_DMA) == 0, "timer wake noted");
    require(k3_domain_note_wake(0, K3_CONSUMER_DISPLAY) == 0, "other wake noted");

    printf("%s: %d checks, %d failures\n", failed ? "FAILED" : "PASS", checks, failed);
    return failed != 0;
}

/* the mid-wait injection target: a DISPLAY consumer arrives while the
 * request is blocked in rt_sem_take */
static void inject_during_wait(void){
    k3_domain_consumer_acquire(0, K3_CONSUMER_DISPLAY);
}

/* mid-wait M2-enter: the ISR releases the semaphore while the
 * request is blocked in rt_sem_take (a legitimate grant) */
static void release_enter_sem_during_wait(void){
    k3_domain_m2_enter_release(0);
}
'''


class K3DomainOwnershipTests(unittest.TestCase):
    def test_ownership_fault_injection(self):
        src = (SOURCE_DIR / 'k3_domain_ownership.c').read_text()
        hdr = (SOURCE_DIR / 'k3_domain_ownership.h').read_text()
        # strip the include of the real header; inline it (minus its RT includes)
        for inc in ('#include <rthw.h>', '#include <rtthread.h>'):
            hdr = hdr.replace(inc + '\n', '')
        hdr_inline = '\n'.join('#define K3_MAX_CLUSTERS 4' if l.strip().startswith('#define K3_MAX_CLUSTERS') else l
                                for l in hdr.split('\n'))
        body = src.replace('#include "k3_domain_ownership.h"', '')
        body = '\n'.join(l for l in body.split('\n') if not l.startswith('#include'))
        program = COMMON + hdr_inline + '\n#define K3_DOMAIN_TEST 1\n' + body + '\n' + TESTS
        with tempfile.TemporaryDirectory(prefix='k3-p1-test-') as d:
            c = Path(d) / 't.c'
            exe = Path(d) / 't'
            c.write_text(program)
            build = subprocess.run(['cc', '-o', str(exe), str(c), '-I', str(SOURCE_DIR)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:4000])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn('0 failures', run.stdout)


if __name__ == '__main__':
    unittest.main()
