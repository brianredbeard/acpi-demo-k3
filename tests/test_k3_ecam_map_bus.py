#!/usr/bin/env python3
"""Host-side unit tests for the K3 ECAM map_bus logic (segs 2/4 ops).

Extracts the map_bus core from the rig's pcie-k3-acpi-ecam.c and runs
it against mocked kernel primitives. This is the test the 3j boot
needed BEFORE burning a cycle: the root-bus ghost filter (the Nov 18
devfn rule) and the ATU translation parameters are pure logic,
testable without a kernel build.

Test classes:
  - root-bus ghost filter: only devfn 0 reaches the DBI; every other
    root-bus devfn returns NULL (the 64-fake-bridge regression)
  - own-map addressing: devfn 0 + where -> dbi_base + where
  - child-map ATU encoding: bus/dev/fn bits, CFG0 directly below the
    root, CFG1 farther, viewport handback
  - ATU serialization: concurrent maps cannot interleave the program
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECAM_SRC = ROOT / "patches/kernel-rpm/series/el10-284/ecam/pcie-k3-acpi-ecam.c"

# The kernel headers the driver includes, mocked for the host.
COMMON = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>
#include <pthread.h>

static pthread_mutex_t k3_ecam_atu_lock = PTHREAD_MUTEX_INITIALIZER;

#include <stdbool.h>
#define NULL ((void *)0)

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long resource_size_t;
#define __iomem

#define PCI_SLOT(devfn) (((devfn) >> 3) & 0x1f)
#define PCI_FUNC(devfn) ((devfn) & 0x07)

#define PCIE_ATU_BUS(x) ((u32)(x) << 20)
#define PCIE_ATU_DEV(x) ((u32)(x) << 15)
#define PCIE_ATU_FUNC(x) ((u32)(x) << 12)
#define PCIE_ATU_TYPE_CFG0 0x0a
#define PCIE_ATU_TYPE_CFG1 0x0b

#define SZ_4K 4096
#define SZ_64K 65536

/* --- mocked kernel types ------------------------------------------- */
struct pci_bus {
    int number;
    struct pci_bus *parent;
    void *sysdata;               /* struct pci_config_window * */
};

static int pci_is_root_bus(struct pci_bus *bus)
{
    /* a root bus has no parent OR a dummy-flagged one; for the tests
     * we mark roots by parent == NULL */
    return bus->parent == NULL;
}

struct pci_config_window {
    void *win;                   /* cfg0_base */
    resource_size_t res_start, res_end;
    void *priv;                  /* struct k3_ecam_seg * */
};

struct device { int dummy; };

struct dw_pcie {
    struct device *dev;
    void *dbi_base;
    void *atu_base;
    int num_ob_windows;
    unsigned int pp_ob_atu_idx_offset;
};

struct dw_pcie_rp { int dummy; };

struct dw_pcie_ob_atu_cfg {
    int index;
    int type;
    u64 parent_bus_addr;
    u64 pci_addr;
    u64 size;
};

/* --- the ATU mock: records the LAST programmed config + a call log -- */
static struct dw_pcie_ob_atu_cfg mock_last_atu;
static int mock_atu_calls;
static int mock_atu_ret;         /* injectable failure */

static int dw_pcie_prog_outbound_atu(struct dw_pcie *pci,
                                     struct dw_pcie_ob_atu_cfg *atu)
{
    (void)pci;
    if (mock_atu_ret)
        return mock_atu_ret;
    mock_last_atu = *atu;
    mock_atu_calls++;
    return 0;
}

/* mutex: use pthreads to exercise serialization semantics */

/* devm mocks: fixed arenas so ioremap "succeeds" */
/* the device/ACPI init path is not under test; stub the segment directly */
'''

TESTS = r'''
/* --- the extracted map_bus core (kept verbatim in shape) ---------- */
struct k3_ecam_seg {
    struct dw_pcie pci;
    struct dw_pcie_rp pp;
    void *dbi_base;
    void *cfg0_base;
    resource_size_t cfg0_size;
    void *atu_base;
};

static void *k3_ecam_own_map(struct k3_ecam_seg *seg, int where)
{
    return seg->dbi_base + where;
}

static void *k3_ecam_child_map(struct k3_ecam_seg *seg,
                               struct pci_bus *bus,
                               unsigned int devfn, int where)
{
    struct dw_pcie *pci = &seg->pci;
    struct dw_pcie_ob_atu_cfg atu = { 0 };
    u32 busdev;
    int type, ret;

    busdev = PCIE_ATU_BUS(bus->number) |
             PCIE_ATU_DEV(PCI_SLOT(devfn)) |
             PCIE_ATU_FUNC(PCI_FUNC(devfn));

    type = pci_is_root_bus(bus->parent) ?
        PCIE_ATU_TYPE_CFG0 : PCIE_ATU_TYPE_CFG1;

    atu.index = 0;
    atu.type = type;
    atu.parent_bus_addr = (u64)(uintptr_t)seg->cfg0_base;
    atu.pci_addr = busdev;
    atu.size = seg->cfg0_size;

    pthread_mutex_lock(&k3_ecam_atu_lock);
    ret = dw_pcie_prog_outbound_atu(pci, &atu);
    pthread_mutex_unlock(&k3_ecam_atu_lock);

    if (ret)
        return NULL;

    return seg->cfg0_base + where;
}

static void *k3_ecam_map_bus(struct pci_bus *bus,
                             unsigned int devfn, int where)
{
    struct pci_config_window *cfg = bus->sysdata;
    struct k3_ecam_seg *seg = cfg->priv;

    if (!seg)
        return NULL;

    if (pci_is_root_bus(bus)) {
        /*
         * Root-bus ghost filter (the Nov 18 gpioy-qualified rule,
         * seg-2/4 form): only devfn 0 is reachable on the root bus.
         */
        if (devfn)
            return NULL;
        return k3_ecam_own_map(seg, where);
    }

    return k3_ecam_child_map(seg, bus, devfn, where);
}

/* --- test fixtures -------------------------------------------------- */
static struct k3_ecam_seg seg;
static struct pci_config_window cfg;
static struct pci_bus root_bus;      /* parent == NULL: root */
static struct pci_bus child_bus;     /* parent == &root_bus: bus 1 */
static struct pci_bus grandchild;    /* parent == &child_bus: bus 2 */

static int checks, failed;
static void require(int cond, const char *what)
{
    checks++;
    if (!cond) { failed++; printf("FAIL: %s\n", what); }
}

static void reset(void)
{
    memset(&seg, 0, sizeof(seg));
    memset(&cfg, 0, sizeof(cfg));
    memset(&mock_last_atu, 0, sizeof(mock_last_atu));
    mock_atu_calls = 0;
    mock_atu_ret = 0;

    seg.dbi_base = (void *)0xD4000000;
    seg.cfg0_base = (void *)0x1200000000UL;
    seg.cfg0_size = 0x10000;
    seg.atu_base = (void *)0x80B00000;
    seg.pci.dbi_base = seg.dbi_base;
    seg.pci.atu_base = seg.atu_base;

    cfg.win = seg.cfg0_base;
    cfg.priv = &seg;

    root_bus.number = 0;
    root_bus.parent = NULL;
    root_bus.sysdata = &cfg;

    child_bus.number = 1;
    child_bus.parent = &root_bus;
    child_bus.sysdata = &cfg;

    grandchild.number = 2;
    grandchild.parent = &child_bus;
    grandchild.sysdata = &cfg;
}

int main(void)
{
    void *r;

    /* --- ROOT-BUS GHOST FILTER (the 3j regression) --------------- */
    reset();
    r = k3_ecam_map_bus(&root_bus, 0, 0);
    require(r == (void *)0xD4000000, "root bus devfn 0 maps to DBI");

    r = k3_ecam_map_bus(&root_bus, 1, 0);
    require(r == NULL, "root bus devfn 1 (dev0 fn1) filtered");
    r = k3_ecam_map_bus(&root_bus, 8, 0);
    require(r == NULL, "root bus devfn 8 (dev1 fn0) filtered");
    r = k3_ecam_map_bus(&root_bus, 0x18, 0);
    require(r == NULL, "root bus devfn 0x18 (dev3) filtered");
    r = k3_ecam_map_bus(&root_bus, 0xff, 0);
    require(r == NULL, "root bus devfn 0xff filtered");
    require(mock_atu_calls == 0, "no ATU programming for root-bus access");

    /* --- OWN-MAP ADDRESSING -------------------------------------- */
    reset();
    r = k3_ecam_map_bus(&root_bus, 0, 0x40);
    require(r == (void *)0xD4000040, "devfn 0 where 0x40 -> dbi+0x40");
    r = k3_ecam_map_bus(&root_bus, 0, 0xfff);
    require(r == (void *)0xD4000fff, "devfn 0 where 0xfff -> dbi+0xfff");

    /* --- NULL SEG GUARD ------------------------------------------ */
    reset();
    cfg.priv = NULL;
    r = k3_ecam_map_bus(&root_bus, 0, 0);
    require(r == NULL, "NULL seg returns NULL");

    /* --- CHILD-MAP ATU ENCODING ---------------------------------- */
    reset();
    r = k3_ecam_map_bus(&child_bus, 0, 0);
    require(r == (void *)0x1200000000UL, "child bus 1 devfn 0 returns viewport");
    require(mock_atu_calls == 1, "one ATU program per child access");
    require(mock_last_atu.type == PCIE_ATU_TYPE_CFG0,
            "bus 1 (directly below root) uses CFG0");
    require(mock_last_atu.pci_addr == PCIE_ATU_BUS(1),
            "bus 1 encodes bus number only for devfn 0");

    r = k3_ecam_map_bus(&child_bus, 0x10, 0);   /* dev 2 fn 0 */
    require(mock_last_atu.pci_addr == (PCIE_ATU_BUS(1) | PCIE_ATU_DEV(2)),
            "bus 1 dev 2 encodes bus|dev");

    r = k3_ecam_map_bus(&child_bus, 0x13, 0);   /* dev 2 fn 3 */
    require(mock_last_atu.pci_addr == (PCIE_ATU_BUS(1) | PCIE_ATU_DEV(2) | PCIE_ATU_FUNC(3)),
            "bus 1 dev 2 fn 3 encodes bus|dev|fn");

    /* --- GRANDCHILD: CFG1 ---------------------------------------- */
    reset();
    r = k3_ecam_map_bus(&grandchild, 0x15, 0);
    require(mock_last_atu.type == PCIE_ATU_TYPE_CFG1,
            "bus 2 (past one bridge) uses CFG1");
    require(mock_last_atu.pci_addr == (PCIE_ATU_BUS(2) | PCIE_ATU_DEV(2) | PCIE_ATU_FUNC(5)),
            "grandchild devfn 0x15 encodes bus 2|dev 2|fn 5");

    /* --- ATU PARAMETERS ------------------------------------------ */
    require(mock_last_atu.parent_bus_addr == 0x1200000000UL,
            "ATU parent addr = viewport base");
    require(mock_last_atu.size == 0x10000,
            "ATU size = viewport size (64 KiB)");
    require(mock_last_atu.index == 0, "ATU index 0 (single window)");

    /* --- WHERE OFFSET HANDLING ----------------------------------- */
    reset();
    r = k3_ecam_map_bus(&child_bus, 0, 0x3c);
    require(r == (void *)(0x1200000000UL + 0x3c),
            "child where 0x3c -> viewport+0x3c");

    /* --- ATU FAILURE PROPAGATION --------------------------------- */
    reset();
    mock_atu_ret = -1;
    r = k3_ecam_map_bus(&child_bus, 0, 0);
    require(r == NULL, "ATU program failure returns NULL");

    /* --- ATU SERIALIZATION (concurrent children) ----------------- */
    reset();
    {
        /* the mock records the LAST config; with the mutex held during
         * program, two threads cannot interleave. We verify the lock
         * is actually held across dw_pcie_prog_outbound_atu by
         * asserting from INSIDE the mock: */
        extern int in_atu_critical_section(void);
        require(in_atu_critical_section() == 0,
                "mutex not held outside the ATU call (sanity)");
    }

    printf("%s: %d checks, %d failures\n",
           failed ? "FAILED" : "PASS", checks, failed);
    return failed != 0;
}

/* the serialization probe: called by the ATU mock while the lock
 * is held; nonzero iff the mutex is currently locked by this thread */
static int mock_in_atu;
static int in_atu_critical_section(void)
{
    return mock_in_atu;
}
'''

# inject the probe into the ATU mock
COMMON_FINAL = COMMON.replace(
    """    mock_last_atu = *atu;
    mock_atu_calls++;
    return 0;""",
    """    mock_last_atu = *atu;
    mock_atu_calls++;
    mock_in_atu = 1;
    /* while we are inside the mock, the k3 lock must be held: try a
     * non-blocking acquire — it must FAIL (else the caller did not
     * hold the lock across the program call) */
    {
        int rc = pthread_mutex_trylock(&k3_ecam_atu_lock);
        if (rc == 0) {
            printf("FAIL: ATU mock ran WITHOUT the k3 lock held (unserialized program)\\n");
            pthread_mutex_unlock(&k3_ecam_atu_lock);
            mock_serialization_violation = 1;
        }
    }
    mock_in_atu = 0;
    return 0;"""
).replace(
    "static int mock_atu_ret;         /* injectable failure */",
    "static int mock_atu_ret;         /* injectable failure */\nstatic int mock_in_atu;\nstatic int mock_serialization_violation;"
)

# the lock must be declared before the mock uses it
COMMON_FINAL = COMMON_FINAL.replace(
    "/* mutex: use pthreads to exercise serialization semantics */\nstatic pthread_mutex_t k3_ecam_atu_lock = PTHREAD_MUTEX_INITIALIZER;",
    "/* mutex: use pthreads to exercise serialization semantics */\nstatic pthread_mutex_t k3_ecam_atu_lock = PTHREAD_MUTEX_INITIALIZER;\nstatic int mock_in_atu;\nstatic int mock_serialization_violation;"
)

# move the serialization probe functions out of TESTS (they live in the common)
TESTS_FINAL = TESTS.replace(
    """        extern int in_atu_critical_section(void);
        require(in_atu_critical_section() == 0,
                "mutex not held outside the ATU call (sanity)");""",
    """        require(mock_serialization_violation == 0,
                "ATU programming always under the k3 lock (serialized)");"""
).replace(
    """
/* the serialization probe: called by the ATU mock while the lock
 * is held; nonzero iff the mutex is currently locked by this thread */
static int mock_in_atu;
static int in_atu_critical_section(void)
{
    return mock_in_atu;
}
""", "")


class K3EcamMapBusTests(unittest.TestCase):
    def test_map_bus_rules(self):
        """Compile the extracted map_bus core + mocks; run the assertions."""
        with tempfile.TemporaryDirectory(prefix="k3-ecam-test-") as d:
            c = Path(d) / "t.c"
            exe = Path(d) / "t"
            c.write_text(COMMON_FINAL + TESTS_FINAL)
            build = subprocess.run(
                ["cc", "-o", str(exe), str(c), "-lpthread", "-Wall", "-Werror"],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:4000])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn("PASS:", run.stdout)

    def test_source_matches_rig(self):
        """The harness's extracted logic must match the rig's driver source.

        Guards against the harness drifting from the real driver: the
        root-bus filter comment and the devfn rule must appear verbatim
        in the rig's pcie-k3-acpi-ecam.c.
        """
        rig = ECAM_SRC.read_text() if ECAM_SRC.is_file() else None
        if rig is None:
            self.skipTest("rig driver source not archived in the repo")
        self.assertIn("if (devfn)\n\t\t\treturn NULL;", rig,
                      "the Nov 18 root-bus devfn filter must be in the driver")
        self.assertIn("bus_shift", rig,
                      "the bus_shift 8 creation fix must be in the driver")


if __name__ == "__main__":
    unittest.main()
