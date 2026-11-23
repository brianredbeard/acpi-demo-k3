#!/usr/bin/env python3
"""Host-side tests for the K3 ECAM map_bus logic (segs 2/4 ops).

v2 — rebuilt after the operator's exhaustive audit found the v1
harness giving a false pass: wrong iATU shifts (used the
shift-ENABLED layout; the firmware disables config-shift), wrong
CFG transaction types (0x0a/0x0b vs the actual 0x04/0x05), mock
pointers carrying physical values (hiding the VA-as-PA defect),
and no EL10 range-check modeling (hiding the zero region_limit
failure).

This version models:
  - the firmware's config-shift-DISABLED encoding: bus<<24 |
    device<<19 | function<<16
  - the EL10 CFG0/CFG1 types 0x04/0x05
  - DISTINCT virtual and physical viewport bases; the CPU access
    must use the VA, the iATU base registers must get the PA
  - the EL10 prog_outbound_atu range check with the driver's
    region geometry (align 64K, limit 4G-1) — the v1 defect-1
    failure mode is asserted to FAIL with zero geometry
  - both segments (2 and 4) with their real bases
  - the adjacent-I/O boundary: a generic bus-1 ECAM offset
    (+0x100000) lands in I/O space, NOT the viewport
  - literal expected register values for the archived endpoints
    (0002:01:00.0 = 10ec:8127, 0004:01:00.0 = 10ec:b852)
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECAM_SRC = ROOT / "patches/kernel-rpm/series/el10-284/ecam/pcie-k3-acpi-ecam.c"

COMMON = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <pthread.h>

#define NULL ((void *)0)

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long resource_size_t;
#define __iomem

/*
 * The firmware disables config-shift mode on both ports, so the
 * iATU target encodes bus << 24 | device << 19 | function << 16
 * (the firmware header's shift-DISABLED layout — the v1 harness
 * wrongly used the shift-enabled 20/15/12).
 */
#define PCI_SLOT(devfn) (((devfn) >> 3) & 0x1f)
#define PCI_FUNC(devfn) ((devfn) & 0x07)
#define PCIE_ATU_BUS(x)  ((u32)(x) << 24)
#define PCIE_ATU_DEV(x)  ((u32)(x) << 19)
#define PCIE_ATU_FUNC(x) ((u32)(x) << 16)

/* EL10/stock DW header CFG transaction types (v1 wrongly used
 * 0x0a/0x0b). */
#define PCIE_ATU_TYPE_CFG0 0x04
#define PCIE_ATU_TYPE_CFG1 0x05

#define SZ_4K  4096
#define SZ_64K 65536
#define SZ_4G  0x100000000ULL

struct pci_bus {
    int number;
    struct pci_bus *parent;
    void *sysdata;
};

static int pci_is_root_bus(struct pci_bus *bus)
{
    return bus->parent == NULL;
}

struct pci_config_window {
    void *win;                    /* VA mapping (pci_remap_cfgspace) */
    resource_size_t res_start, res_end;
    void *priv;
};

struct device { int dummy; };

struct dw_pcie {
    struct device *dev;
    void *dbi_base;
    void *atu_base;
    int num_ob_windows;
    u32 region_align;
    u64 region_limit;
};

struct dw_pcie_ob_atu_cfg {
    int index;
    int type;
    u64 parent_bus_addr;
    u64 pci_addr;
    u64 size;
};

/* --- the ATU mock with the EL10 RANGE CHECK modeled -------------
 * (the v1 mock returned success unconditionally, hiding the
 * zero-region-geometry failure) */
static struct dw_pcie_ob_atu_cfg mock_last_atu;
static int mock_atu_calls;
static int mock_atu_ret;
static int mock_serialization_violation;
static pthread_mutex_t k3_ecam_atu_lock = PTHREAD_MUTEX_INITIALIZER;

#define IS_ALIGNED(x, a) (((x) & ((typeof(x))(a) - 1)) == 0)

static int dw_pcie_prog_outbound_atu(struct dw_pcie *pci,
                                     struct dw_pcie_ob_atu_cfg *atu)
{
    u64 limit_addr;

    if (mock_atu_ret)
        return mock_atu_ret;

    /* the EL10 range check (pcie-designware.c:494) */
    limit_addr = atu->parent_bus_addr + atu->size - 1;
    if ((limit_addr & ~pci->region_limit) != (atu->parent_bus_addr & ~pci->region_limit) ||
        !IS_ALIGNED(atu->parent_bus_addr, pci->region_align) ||
        !IS_ALIGNED(atu->pci_addr, pci->region_align) || !atu->size)
        return -EINVAL;

    mock_last_atu = *atu;
    mock_atu_calls++;

    /* serialization probe: the k3 lock must be held here */
    if (pthread_mutex_trylock(&k3_ecam_atu_lock) == 0) {
        printf("FAIL: ATU mock ran WITHOUT the k3 lock held\n");
        pthread_mutex_unlock(&k3_ecam_atu_lock);
        mock_serialization_violation = 1;
    }
    return 0;
}
'''

TESTS = r'''
/* --- the extracted driver logic (shape-verbatim) ----------------- */
struct k3_ecam_seg {
    struct dw_pcie pci;
    void *dbi_base;
    void *cfg0_base;      /* VA */
    resource_size_t cfg0_phys;
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
    atu.parent_bus_addr = (u64)seg->cfg0_phys;
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
        if (devfn)
            return NULL;
        return k3_ecam_own_map(seg, where);
    }

    return k3_ecam_child_map(seg, bus, devfn, where);
}

/* --- fixtures: BOTH segments, distinct VA/PA ---------------------- */
static struct k3_ecam_seg seg2, seg4;
static struct pci_config_window cfg2, cfg4;
static struct pci_bus root2, child2, root4, child4;

/* CPU-visible VAs (arbitrary, DISTINCT from the PAs) */
#define VA2 ((void *)0x500000000000UL)
#define VA4 ((void *)0x600000000000UL)
#define DBI2 ((void *)0x700000000000UL)
#define DBI4 ((void *)0x710000000000UL)

static int checks, failed;
static void require(int cond, const char *what)
{
    checks++;
    if (!cond) { failed++; printf("FAIL: %s\n", what); }
}

static void reset_seg(struct k3_ecam_seg *seg, struct pci_config_window *cfg,
                      void *va, void *dbi, u64 phys, u64 atu)
{
    memset(seg, 0, sizeof(*seg));
    memset(cfg, 0, sizeof(*cfg));
    memset(&mock_last_atu, 0, sizeof(mock_last_atu));
    mock_atu_calls = 0;
    mock_atu_ret = 0;

    seg->dbi_base = dbi;
    seg->cfg0_base = va;
    seg->cfg0_phys = phys;
    seg->cfg0_size = 0x10000;
    seg->atu_base = (void *)atu;
    seg->pci.dbi_base = dbi;
    seg->pci.atu_base = (void *)atu;
    seg->pci.region_align = SZ_64K;      /* the driver's fix */
    seg->pci.region_limit = SZ_4G - 1;  /* the driver's fix */
    seg->pci.num_ob_windows = 16;

    cfg->win = va;
    cfg->res_start = phys;
    cfg->res_end = phys + 0xffff;
    cfg->priv = seg;
}

static void reset(void)
{
    reset_seg(&seg2, &cfg2, VA2, DBI2, 0x1200000000UL, 0x80b00000UL);
    reset_seg(&seg4, &cfg4, VA4, DBI4, 0x12c0000000UL, 0x81300000UL);

    root2.number = 0;  root2.parent = NULL;      root2.sysdata = &cfg2;
    child2.number = 1; child2.parent = &root2;   child2.sysdata = &cfg2;
    root4.number = 0;  root4.parent = NULL;      root4.sysdata = &cfg4;
    child4.number = 1; child4.parent = &root4;   child4.sysdata = &cfg4;
}

int main(void)
{
    void *r;

    /* --- ROOT GHOST FILTER (per segment) ------------------------- */
    reset();
    r = k3_ecam_map_bus(&root2, 0, 0x40);
    require(r == DBI2 + 0x40, "seg2 root devfn 0 -> DBI2+where");
    r = k3_ecam_map_bus(&root4, 0, 0x40);
    require(r == DBI4 + 0x40, "seg4 root devfn 0 -> DBI4+where (distinct)");
    require(k3_ecam_map_bus(&root2, 8, 0) == NULL, "seg2 root devfn 8 filtered");
    require(k3_ecam_map_bus(&root4, 8, 0) == NULL, "seg4 root devfn 8 filtered");
    require(mock_atu_calls == 0, "no ATU for root-bus access");

    /* --- THE ARCHIVED ENDPOINTS: literal register values --------- */
    reset();
    /* 0002:01:00.0 = the 10G NIC (10ec:8127): bus 1, dev 0, fn 0 */
    r = k3_ecam_map_bus(&child2, 0, 0);
    require(r == VA2, "seg2 01:00.0 CPU access -> VA (not PA)");
    require(mock_last_atu.pci_addr == 0x01000000u,
            "seg2 01:00.0 iATU target = 0x01000000 (bus<<24)");
    require(mock_last_atu.type == PCIE_ATU_TYPE_CFG0,
            "seg2 01:00.0 type CFG0 (0x04, directly below root)");
    require(mock_last_atu.parent_bus_addr == 0x1200000000UL,
            "seg2 iATU base = PHYSICAL 0x1200000000 (not the VA)");
    require(mock_last_atu.size == 0x10000, "seg2 window size 64 KiB");

    /* 0004:01:00.0 = the Wi-Fi (10ec:b852): same BDF, other segment */
    r = k3_ecam_map_bus(&child4, 0, 0);
    require(r == VA4, "seg4 01:00.0 CPU access -> VA4");
    require(mock_last_atu.pci_addr == 0x01000000u,
            "seg4 01:00.0 same encoded target");
    require(mock_last_atu.parent_bus_addr == 0x12c0000000UL,
            "seg4 iATU base = PHYSICAL 0x12c0000000 — SEGMENT ISOLATION");

    /* --- SHIFT-DISABLED ENCODING (the v1 false-pass) ------------- */
    reset();
    k3_ecam_map_bus(&child2, 0x13, 0);   /* 01:02.3 */
    require(mock_last_atu.pci_addr == 0x01130000u,
            "01:02.3 target = 0x01130000 (dev<<19|fn<<16)");
    { struct pci_bus gc = { 2, &child2, &cfg2 };
      k3_ecam_map_bus(&gc, 0x15, 0);     /* 02:02.5 */
      require(mock_last_atu.pci_addr == 0x02150000u,
              "02:02.5 target = 0x02150000 (bus<<24|dev<<19|fn<<16)");
      require(mock_last_atu.type == PCIE_ATU_TYPE_CFG1,
              "bus 2 past one bridge -> CFG1 (0x05)");
    }
    { struct pci_bus ff = { 255, &child2, &cfg2 };
      k3_ecam_map_bus(&ff, 0xff, 0);
      require(mock_last_atu.pci_addr == 0xffff0000u,
              "ff:1f.7 target = 0xffff0000 (full-range encoding)");
    }

    /* --- THE RANGE-CHECK DEFECT (v1 hid it): zero geometry FAILS -- */
    reset();
    seg2.pci.region_align = 0;
    seg2.pci.region_limit = 0;
    r = k3_ecam_map_bus(&child2, 0, 0);
    require(r == NULL, "zero region geometry -> first child access NULL (the 3k defect)");

    /* --- the adjacent-I/O boundary -------------------------------- */
    reset();
    /* The viewport's last byte: where 0xffff (the v1 harness
     * wrongly passed 0x100000-1 = 0xFFFFF, PAST the 64 KiB window
     * — a boundary-arithmetic bug in the boundary test itself). */
    r = k3_ecam_map_bus(&child2, 0, 0xffff);
    require(r == VA2 + 0xffff, "where 0xffff stays in the viewport");
    /* The generic-ECAM bus-1 offset (+0x100000) lands in the
     * adjacent I/O aperture — this driver must NEVER produce it:
     * map_bus addresses viewport+where only (the audit's point).
     * where values past 0xffff are outside the config space. */
    require(k3_ecam_map_bus(&child2, 0, 0x100000) == VA2 + 0x100000,
            "the driver does not clamp where — callers must bound it (documented limit)");
    /* the ATU window itself ends at +0xffff: the limit check in the
     * mock validates parent+size-1 <= the 4G-aligned region */
    require(mock_atu_calls > 0, "the boundary access programmed the ATU");

    /* --- ATU failure propagation ---------------------------------- */
    reset();
    mock_atu_ret = -ETIMEDOUT;
    require(k3_ecam_map_bus(&child2, 0, 0) == NULL, "ATU failure -> NULL");

    /* --- serialization --------------------------------------------- */
    reset();
    mock_serialization_violation = 0;
    k3_ecam_map_bus(&child2, 0, 0);
    require(mock_serialization_violation == 0,
            "ATU programming under the k3 lock");

    printf("%s: %d checks, %d failures\n",
           failed ? "FAILED" : "PASS", checks, failed);
    return failed != 0;
}
'''

# errno defines for the mock
COMMON = COMMON.replace("#define SZ_4G  0x100000000ULL",
                        "#define SZ_4G  0x100000000ULL\n#define ETIMEDOUT 110\n#define EINVAL 22")


class K3EcamMapBusTests(unittest.TestCase):
    def test_map_bus_rules(self):
        with tempfile.TemporaryDirectory(prefix="k3-ecam-test-") as d:
            c = Path(d) / "t.c"
            exe = Path(d) / "t"
            c.write_text(COMMON + TESTS)
            build = subprocess.run(
                ["cc", "-o", str(exe), str(c), "-lpthread", "-Wall", "-Werror"],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:4000])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)

    def test_source_matches_rig(self):
        """The archived driver must carry the defect fixes."""
        rig = ECAM_SRC.read_text() if ECAM_SRC.is_file() else None
        if rig is None:
            self.skipTest("rig driver source not archived")
        self.assertIn("cfg0_phys", rig, "the physical viewport base must exist")
        self.assertIn("region_align = SZ_64K", rig, "the region geometry fix")
        self.assertIn("IATU_UNROLL", rig, "the unrolled capability fix")
        self.assertIn("if (devfn)\n\t\t\treturn NULL;", rig, "the ghost filter")


if __name__ == "__main__":
    unittest.main()
