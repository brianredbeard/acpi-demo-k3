#!/usr/bin/env python3
"""Host-side contract tests for the K3 ACPI ECAM driver (segments 2/4).

The C half compiles the *actual* map/init functions out of
patches/kernel/el10-284/ecam/pcie-k3-acpi-ecam.c (not a
hand-copied "shape-verbatim" twin) against EL10-shaped mocks:

  - pci_lock is held by the PCI core across map_bus + access, so
    there is no private sleeping lock in the driver;
  - the iATU target is bus<<24 | dev<<19 | fn<<16 (config-shift off);
  - CFG0/CFG1 are the EL10 0x04/0x05 types;
  - the CPU access uses cfg->win (VA), the iATU registers use
    cfg->res.start (PA);
  - dw_pcie_prog_outbound_atu checks index/num_ob_windows,
    region_align, region_limit and size;
  - the PHY AHB link-status register gates downstream access;
  - map_bus masks where to PCIE_ECAM_REG_MASK (12 bits).

The Python half guards the pieces a host rig cannot execute: active
patch/source equality, the MCFG quirk rows and OEM revision, the
DSDT segment/viewport declarations, and the build/linkage gate.
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECAM_SRC = ROOT / "patches/kernel/el10-284/ecam/pcie-k3-acpi-ecam.c"
ACTIVE_PATCH = ROOT / "patches/kernel/el10-284/k3-ecam-segs24.patch"
CONFIG = ROOT / "patches/kernel/el10-284/config-acpidebug"
FW = ROOT.parent / "edk2-platforms/Platform/Spacemit/K3"
FW_HEADER = FW / "Include/K3PlatformAcpi.h"
FW_MCFG = FW / "AcpiTables/Mcfg.aslc"
FW_DSDT = FW / "AcpiTables/Dsdt/Dsdt.asl"

EXTRACT = (
    "k3_ecam_link_up",
    "k3_ecam_own_map",
    "k3_ecam_child_map",
    "k3_ecam_map_bus",
    "k3_ecam_enable_msi",
    "k3_ecam_init",
    "k3_dw_seg0_map_bus",
)


def extract_function(source: str, name: str) -> str:
    """Return the complete C function definition for *name*."""
    match = re.search(
        r"^static\s+[^;{]*?\b" + re.escape(name) + r"\s*\(",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"function {name} not found")
    brace = source.index("{", match.end())
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def new_file_hunk(patch: str):
    """Return (declared_line_count, body) for the patch's new file hunk."""
    lines = patch.splitlines(keepends=True)
    start = next(
        i for i, line in enumerate(lines) if line.startswith("@@ -0,0 +1,")
    )
    end = next(
        i for i, line in enumerate(lines)
        if line.startswith("--- a/drivers/pci/controller/dwc/Makefile")
    )
    body = "".join(line[1:] for line in lines[start + 1:end] if line.startswith("+"))
    count = int(re.search(r"\+1,(\d+)", lines[start]).group(1))
    return count, body


COMMON = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stddef.h>

#define NULL ((void *)0)
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long resource_size_t;
typedef int gfp_t;
#define GFP_KERNEL 0
#define __iomem

#define BIT(n) (1UL << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define container_of(ptr, type, member) \
	((type *)((char *)(ptr) - offsetof(type, member)))
#define IS_ALIGNED(x, a) (((x) & ((__typeof__(x))(a) - 1)) == 0)

#define PCI_SLOT(devfn) (((devfn) >> 3) & 0x1f)
#define PCI_FUNC(devfn) ((devfn) & 0x07)

/* EL10/stock DW config-shift-disabled encoding. */
#define PCIE_ATU_BUS(x)  ((u32)(x) << 24)
#define PCIE_ATU_DEV(x)  ((u32)(x) << 19)
#define PCIE_ATU_FUNC(x) ((u32)(x) << 16)

#define PCIE_ATU_TYPE_CFG0 0x04
#define PCIE_ATU_TYPE_CFG1 0x05

#define PCIE_ECAM_BUS_SHIFT  20
#define PCIE_ECAM_DEVFN_SHIFT 12
#define PCIE_ECAM_BUS_MASK   0xff
#define PCIE_ECAM_DEVFN_MASK 0xff
#define PCIE_ECAM_REG_MASK   0xfff
#define PCIE_ECAM_OFFSET(bus, devfn, where) \
	(((u32)(bus) & PCIE_ECAM_BUS_MASK) << PCIE_ECAM_BUS_SHIFT | \
	 ((u32)(devfn) & PCIE_ECAM_DEVFN_MASK) << PCIE_ECAM_DEVFN_SHIFT | \
	 ((where) & PCIE_ECAM_REG_MASK))

#define SZ_4K  4096
#define SZ_16K 16384
#define SZ_64K 65536
#define SZ_4G  0x100000000ULL

#define EINVAL 22
#define ENOMEM 12
#define ETIMEDOUT 110
#define ENOSPC 28

#define IATU_UNROLL 1
#define dw_pcie_cap_set(pci, cap) ((pci)->caps |= BIT(cap))

struct resource {
	resource_size_t start, end;
};

static inline resource_size_t resource_size(const struct resource *res)
{
	return res->end - res->start + 1;
}

struct device {
	int dummy;
};

struct pci_bus {
	int number;
	struct pci_bus *parent;
	void *sysdata;
};

struct pci_config_window {
	struct device *parent;
	void *win;
	struct resource res;
	struct resource busr;
	void *priv;
	unsigned int bus_shift;
};

struct acpi_device {
	struct device dev;
	void *driver_data;
};

struct acpi_pci_root {
	u16 segment;
};

#define to_acpi_device(d) container_of(d, struct acpi_device, dev)

static struct acpi_pci_root *acpi_driver_data(struct acpi_device *adev)
{
	return (struct acpi_pci_root *)adev->driver_data;
}

struct dw_pcie {
	struct device *dev;
	void *dbi_base;
	void *atu_base;
	int num_ob_windows;
	u32 region_align;
	u64 region_limit;
	unsigned long caps;
	u32 version;
};

struct dw_pcie_ob_atu_cfg {
	int index;
	int type;
	u64 parent_bus_addr;
	u64 pci_addr;
	u64 size;
};

struct k3_ecam_seg {
	struct dw_pcie pci;
	void *dbi_base;
	void *cfg0_base;
	resource_size_t cfg0_phys;
	resource_size_t cfg0_size;
	void *atu_base;
	void *link_base;
};

static int pci_is_root_bus(struct pci_bus *bus)
{
	return bus->parent == NULL;
}

static void *mock_va(resource_size_t pa)
{
	return (void *)(uintptr_t)(0x100000000000UL + pa);
}

static u32 link2_status, link4_status;
static u32 link2_irq_en, link2_intr_en, link4_irq_en, link4_intr_en;
static u32 dbi2_coh3, dbi4_coh3;
static int ro_wr_en_count;
static u32 readl(const void *addr)
{
	if (addr == mock_va(0x82D00004UL))
		return link2_status;
	if (addr == mock_va(0x82B00004UL))
		return link4_status;
	if (addr == mock_va(0x808008E8UL))
		return dbi2_coh3;
	if (addr == mock_va(0x810008E8UL))
		return dbi4_coh3;
	exit(EXIT_FAILURE);
}

/* the MSI-enable path's register handlers (vars declared above readl) */
static void writel_relaxed(u32 v, void *addr)
{
	if (addr == mock_va(0x82D00000UL)) { link2_irq_en = v; return; }
	if (addr == mock_va(0x82D00014UL)) { link2_intr_en = v; return; }
	if (addr == mock_va(0x82B00000UL)) { link4_irq_en = v; return; }
	if (addr == mock_va(0x82B00014UL)) { link4_intr_en = v; return; }
	fprintf(stderr, "unexpected writel at %p\n", addr);
	exit(EXIT_FAILURE);
}
static void dw_pcie_dbi_ro_wr_en(struct dw_pcie *pci) { ro_wr_en_count++; (void)pci; }
static u32 readl_relaxed(const void *addr)
{
	if (addr == mock_va(0x82D00000UL)) return link2_irq_en;
	if (addr == mock_va(0x82B00000UL)) return link4_irq_en;
	return 0;
}
static void dw_pcie_dbi_ro_wr_dis(struct dw_pcie *pci) { (void)pci; }
#define GENMASK(h, l) (((1UL << ((h) - (l) + 1)) - 1) << (l))
static inline u32 u32_replace_bits(u32 reg, u32 val, u32 mask)
{
	u32 shift = __builtin_ctz(mask);
	return (reg & ~mask) | ((val << shift) & mask);
}
static void writel(u32 v, void *addr)
{
	if (addr == mock_va(0x808008E8UL)) { dbi2_coh3 = v; return; }
	if (addr == mock_va(0x810008E8UL)) { dbi4_coh3 = v; return; }
	fprintf(stderr, "unexpected writel at %p\n", addr);
	exit(EXIT_FAILURE);
}
/* (DBI COH3 reads go through the extended readl above) */
static int mock_version_calls;
static void dw_pcie_version_detect(struct dw_pcie *pci)
{
	(void)pci;
	mock_version_calls++;
}

static struct dw_pcie_ob_atu_cfg mock_last_atu;
static int mock_atu_calls;
static int mock_atu_ret;

static int dw_pcie_prog_outbound_atu(struct dw_pcie *pci,
				     const struct dw_pcie_ob_atu_cfg *atu)
{
	u64 limit_addr;

	if (mock_atu_ret)
		return mock_atu_ret;

	/* EL10 pcie-designware.c range/index checks. */
	if (atu->index >= pci->num_ob_windows)
		return -ENOSPC;

	limit_addr = atu->parent_bus_addr + atu->size - 1;
	if ((limit_addr & ~pci->region_limit) !=
	    (atu->parent_bus_addr & ~pci->region_limit) ||
	    !IS_ALIGNED(atu->parent_bus_addr, pci->region_align) ||
	    !IS_ALIGNED(atu->pci_addr, pci->region_align) ||
	    !atu->size)
		return -EINVAL;

	mock_last_atu = *atu;
	mock_atu_calls++;
	return 0;
}

#define MOCK_IOMAPS 8
struct mock_iomap {
	resource_size_t pa, size;
};
static struct mock_iomap mock_iomaps[MOCK_IOMAPS];
static int mock_iomap_count;
static int mock_iomap_fail_at = -1;

static void reset_iomaps(void)
{
	memset(mock_iomaps, 0, sizeof(mock_iomaps));
	mock_iomap_count = 0;
	mock_iomap_fail_at = -1;
}

static void *devm_ioremap(struct device *dev, resource_size_t pa,
			  resource_size_t size)
{
	int idx = mock_iomap_count++;

	(void)dev;
	if (idx < MOCK_IOMAPS) {
		mock_iomaps[idx].pa = pa;
		mock_iomaps[idx].size = size;
	}
	if (idx == mock_iomap_fail_at)
		return NULL;
	return mock_va(pa);
}

static void *devm_kzalloc(struct device *dev, size_t size, gfp_t flags)
{
	(void)dev;
	(void)flags;
	return calloc(1, size);
}

static void dev_info(struct device *dev, const char *fmt, ...)
{
	(void)dev;
	(void)fmt;
}

/* The generic ACPI ECAM map formula used by seg 0 (256 MiB, bus_shift 0). */
static void *pci_ecam_map_bus(struct pci_bus *bus, unsigned int devfn, int where)
{
	struct pci_config_window *cfg = bus->sysdata;

	return cfg->win + PCIE_ECAM_OFFSET(bus->number, devfn, where);
}
'''


TESTS = r'''
static struct k3_ecam_seg seg2, seg4;
static struct pci_config_window cfg2, cfg4;
static struct pci_bus root2, child2, grandchild2, root4, child4;
static struct device mock_dev;

#define VA2   ((void *)0x500000000000UL)
#define VA4   ((void *)0x600000000000UL)
#define DBI2  ((void *)0x700000000000UL)
#define DBI4  ((void *)0x710000000000UL)
#define LINK2 mock_va(0x82D00000UL)
#define LINK4 mock_va(0x82B00000UL)

static int checks, failed;

static void require(int cond, const char *what)
{
	checks++;
	if (!cond) {
		failed++;
		printf("FAIL: %s\n", what);
	}
}

static void reset_seg(struct k3_ecam_seg *seg, struct pci_config_window *cfg,
		      void *va, void *dbi, unsigned long phys, void *link)
{
	memset(seg, 0, sizeof(*seg));
	memset(cfg, 0, sizeof(*cfg));

	seg->dbi_base = dbi;
	seg->cfg0_base = va;
	seg->cfg0_phys = phys;
	seg->cfg0_size = 0x10000;
	seg->atu_base = (void *)0x730000000000UL;
	seg->link_base = link;
	seg->pci.dev = &mock_dev;
	seg->pci.dbi_base = dbi;
	seg->pci.atu_base = seg->atu_base;
	seg->pci.region_align = SZ_64K;
	seg->pci.region_limit = SZ_4G - 1;
	seg->pci.num_ob_windows = 1;
	seg->pci.caps = BIT(IATU_UNROLL);

	cfg->parent = &mock_dev;
	cfg->win = va;
	cfg->res.start = phys;
	cfg->res.end = phys + 0xffff;
	cfg->priv = seg;
	cfg->bus_shift = 8;
}

static void reset(void)
{
	memset(&mock_last_atu, 0, sizeof(mock_last_atu));
	mock_atu_calls = 0;
	mock_atu_ret = 0;
	link2_status = link4_status = BIT(1) | BIT(12);
	mock_version_calls = 0;
	reset_iomaps();

	reset_seg(&seg2, &cfg2, VA2, DBI2, 0x1200000000UL, LINK2);
	reset_seg(&seg4, &cfg4, VA4, DBI4, 0x12c0000000UL, LINK4);

	root2.number = 0;
	root2.parent = NULL;
	root2.sysdata = &cfg2;
	child2.number = 1;
	child2.parent = &root2;
	child2.sysdata = &cfg2;
	grandchild2.number = 2;
	grandchild2.parent = &child2;
	grandchild2.sysdata = &cfg2;

	root4.number = 0;
	root4.parent = NULL;
	root4.sysdata = &cfg4;
	child4.number = 1;
	child4.parent = &root4;
	child4.sysdata = &cfg4;
}

static struct acpi_device mock_adev;
static struct acpi_pci_root mock_root;
static struct pci_config_window icfg;

static void init_fixture(u16 segment, resource_size_t phys, void *win)
{
	memset(&mock_adev, 0, sizeof(mock_adev));
	memset(&mock_root, 0, sizeof(mock_root));
	memset(&icfg, 0, sizeof(icfg));

	mock_root.segment = segment;
	mock_adev.driver_data = &mock_root;
	icfg.parent = &mock_adev.dev;
	icfg.win = win;
	icfg.res.start = phys;
	icfg.res.end = phys + 0xffff;
	icfg.bus_shift = 8;

	reset_iomaps();
	mock_version_calls = 0;
	mock_atu_ret = 0;
	mock_atu_calls = 0;
	link2_status = link4_status = BIT(1) | BIT(12);
}

int main(void)
{
	void *r;
	struct k3_ecam_seg *seg;
	int ret, i;

	/* Root-bus DBI access and the device-slot ghost filter. */
	reset();
	for (unsigned int devfn = 0; devfn < 256; devfn++) {
		require(k3_ecam_map_bus(&root2, devfn, 0x40) ==
			(devfn == 0 ? DBI2 + 0x40 : NULL), "seg2 DBI devfn filter");
		require(k3_ecam_map_bus(&root4, devfn, 0x40) ==
			(devfn == 0 ? DBI4 + 0x40 : NULL), "seg4 DBI devfn filter");
	}
	require(k3_ecam_map_bus(&root2, 0, 0x1000) == DBI2,
		"root where masked to 12 bits");
	require(k3_ecam_map_bus(&root2, 0, 0x100000) == DBI2,
		"root where past 4K masked");
	require(mock_atu_calls == 0, "root access does not program iATU");

	reset();
	link2_status = link4_status = 0;
	require(k3_ecam_map_bus(&root2, 0, 0x40) == DBI2 + 0x40,
		"seg2 root DBI while both links are down");
	require(k3_ecam_map_bus(&root4, 0, 0x40) == DBI4 + 0x40,
		"seg4 root DBI while both links are down");

	/* Downstream: CPU VA, physical iATU base, 12-bit offset. */
	reset();
	r = k3_ecam_map_bus(&child2, 0, 0);
	require(r == VA2, "seg2 01:00.0 CPU access -> VA");
	require(mock_last_atu.pci_addr == 0x01000000u,
		"seg2 01:00.0 target = bus<<24");
	require(mock_last_atu.type == PCIE_ATU_TYPE_CFG0,
		"seg2 01:00.0 type CFG0 directly below root");
	require(mock_last_atu.parent_bus_addr == 0x1200000000UL,
		"seg2 iATU base = physical 0x1200000000");
	require(mock_last_atu.size == 0x10000, "seg2 window size 64 KiB");
	require(mock_last_atu.index == 0, "seg2 config window index 0");

	r = k3_ecam_map_bus(&child2, 0, 0x40);
	require(r == VA2 + 0x40, "child where 0x40 -> VA+0x40");
	require(k3_ecam_map_bus(&child2, 0, 0x1000) == VA2,
		"child where 0x1000 masked -> VA");
	require(k3_ecam_map_bus(&child2, 0, 0x100000) == VA2,
		"child where 0x100000 masked -> VA (not I/O aperture)");

	k3_ecam_map_bus(&child2, 0x13, 0);
	require(mock_last_atu.pci_addr == 0x01130000u,
		"01:02.3 target = dev<<19 | fn<<16");
	k3_ecam_map_bus(&grandchild2, 0x15, 0);
	require(mock_last_atu.pci_addr == 0x02150000u,
		"02:02.5 target = bus<<24 | dev<<19 | fn<<16");
	require(mock_last_atu.type == PCIE_ATU_TYPE_CFG1,
		"bus 2 past one bridge -> CFG1");
	{
		struct pci_bus ff = { 255, &child2, &cfg2 };

		k3_ecam_map_bus(&ff, 0xff, 0);
		require(mock_last_atu.pci_addr == 0xffff0000u,
			"ff:1f.7 target = full-range encoding");
	}

	r = k3_ecam_map_bus(&child4, 0, 0);
	require(r == VA4, "seg4 01:00.0 CPU access -> VA4");
	require(mock_last_atu.parent_bus_addr == 0x12c0000000UL,
		"seg4 iATU base = physical 0x12c0000000");

	/* PHY AHB link gate: both SMLH and RDLH, no iATU if down. */
	const u32 states[] = { 0, BIT(1), BIT(12), BIT(1) | BIT(12) };
	for (unsigned int port = 0; port < 2; port++) {
		for (unsigned int n = 0; n < ARRAY_SIZE(states); n++) {
			reset();
			link2_status = port == 0 ? states[n] : 0;
			link4_status = port == 1 ? states[n] : 0;
			bool up = states[n] == (BIT(1) | BIT(12));
			require(k3_ecam_map_bus(&child2, 0, 0) ==
				(port == 0 && up ? VA2 : NULL), "seg2 PHY link gate");
			require(k3_ecam_map_bus(&child4, 0, 0) ==
				(port == 1 && up ? VA4 : NULL), "seg4 PHY link gate");
			require(mock_atu_calls == (int)up, "only a live link programs iATU");
		}
	}
	reset();
	seg2.link_base = NULL;
	require(k3_ecam_map_bus(&child2, 0, 0) == NULL,
		"missing link block -> NULL");

	/* EL10 iATU failure paths. */
	reset();
	mock_atu_ret = -ETIMEDOUT;
	require(k3_ecam_map_bus(&child2, 0, 0) == NULL,
		"iATU failure -> NULL");
	reset();
	seg2.pci.region_align = 0;
	seg2.pci.region_limit = 0;
	require(k3_ecam_map_bus(&child2, 0, 0) == NULL,
		"zero region geometry -> NULL");
	reset();
	seg2.pci.num_ob_windows = 0;
	require(k3_ecam_map_bus(&child2, 0, 0) == NULL,
		"num_ob_windows 0 -> NULL");
	reset();
	cfg2.priv = NULL;
	require(k3_ecam_map_bus(&child2, 0, 0) == NULL,
		"missing segment state -> NULL");

	/* Segment 0: genuine 256 MiB ECAM with the same root-slot filter. */
	{
		static struct pci_config_window cfg0;
		static struct pci_bus root0, child0;
		void *win = (void *)0x800000000000UL;

		memset(&cfg0, 0, sizeof(cfg0));
		cfg0.win = win;
		cfg0.busr.start = 0;
		cfg0.bus_shift = 0;
		root0.number = 0;
		root0.parent = NULL;
		root0.sysdata = &cfg0;
		child0.number = 1;
		child0.parent = &root0;
		child0.sysdata = &cfg0;

		require(k3_dw_seg0_map_bus(&root0, 0, 0x40) == win + 0x40,
			"seg0 root devfn 0 -> ECAM+where");
		require(k3_dw_seg0_map_bus(&root0, 1, 0x40) ==
			win + 0x1000 + 0x40,
			"seg0 root function 1 allowed");
		require(k3_dw_seg0_map_bus(&root0, 7, 0x40) ==
			win + 0x7000 + 0x40,
			"seg0 root function 7 allowed");
		require(k3_dw_seg0_map_bus(&root0, 8, 0) == NULL,
			"seg0 root device 1 filtered");
		require(k3_dw_seg0_map_bus(&root0, 0, 0x1000) == win,
			"seg0 generic ECAM masks where");
		require(k3_dw_seg0_map_bus(&child0, 0, 0) ==
			win + 0x100000,
			"seg0 child bus 1 dev 0 -> ECAM bus offset");
		require(k3_dw_seg0_map_bus(&child0, 8, 0) ==
			win + 0x108000,
			"seg0 child bus 1 dev 1 allowed");
	}

	/* k3_ecam_init geometry, mapping sizes, and segment rejects. */
	init_fixture(2, 0x1200000000UL, VA2);
	ret = k3_ecam_init(&icfg);
	require(ret == 0, "seg2 init succeeds");
	seg = icfg.priv;
	require(seg != NULL, "seg2 init sets cfg->priv");
	if (seg) {
		require(seg->cfg0_base == VA2, "seg2 cfg0_base = cfg->win");
		require(seg->cfg0_phys == 0x1200000000UL,
			"seg2 cfg0_phys = cfg->res.start");
		require(seg->cfg0_size == 0x10000,
			"seg2 cfg0_size = 64 KiB");
		require(mock_iomap_count == 3,
			"seg2 maps DBI, ATU, and link");
		require(mock_iomaps[0].pa == 0x80800000UL &&
			mock_iomaps[0].size == SZ_4K,
			"seg2 DBI PA/size");
		require(mock_iomaps[1].pa == 0x80B00000UL &&
			mock_iomaps[1].size == SZ_16K,
			"seg2 ATU PA/size (full unrolled file)");
		require(mock_iomaps[2].pa == 0x82D00000UL &&
			mock_iomaps[2].size == SZ_4K,
			"seg2 PHY link PA/size");
		require(seg->dbi_base == mock_va(0x80800000UL),
			"seg2 DBI VA");
		require(seg->atu_base == mock_va(0x80B00000UL),
			"seg2 ATU VA");
		require(seg->link_base == mock_va(0x82D00000UL),
			"seg2 link VA");
		require(seg->pci.dev == &mock_adev.dev,
			"seg2 dw_pcie.dev");
		require(seg->pci.dbi_base == seg->dbi_base,
			"seg2 dw_pcie.dbi_base");
		require(seg->pci.atu_base == seg->atu_base,
			"seg2 dw_pcie.atu_base");
		require(seg->pci.region_align == SZ_64K,
			"seg2 region_align");
		require(seg->pci.region_limit == SZ_4G - 1,
			"seg2 region_limit");
		require(seg->pci.num_ob_windows == 1,
			"seg2 num_ob_windows");
		require((seg->pci.caps & BIT(IATU_UNROLL)) != 0,
			"seg2 IATU_UNROLL");
		require(mock_version_calls == 1,
			"seg2 dw_pcie_version_detect called once");

		root2.sysdata = &icfg;
		require(k3_ecam_map_bus(&root2, 0, 0x40) ==
			seg->dbi_base + 0x40,
			"inited seg2 root map uses DBI");
	}

	init_fixture(4, 0x12c0000000UL, VA4);
	ret = k3_ecam_init(&icfg);
	require(ret == 0, "seg4 init succeeds");
	seg = icfg.priv;
	require(seg != NULL, "seg4 init sets cfg->priv");
	if (seg) {
		require(mock_iomaps[0].pa == 0x81000000UL &&
			mock_iomaps[0].size == SZ_4K,
			"seg4 DBI PA/size");
		require(mock_iomaps[1].pa == 0x81300000UL &&
			mock_iomaps[1].size == SZ_16K,
			"seg4 ATU PA/size");
		require(mock_iomaps[2].pa == 0x82B00000UL &&
			mock_iomaps[2].size == SZ_4K,
			"seg4 PHY link PA/size");
		require(seg->cfg0_phys == 0x12c0000000UL,
			"seg4 cfg0_phys");
		require(seg->link_base == mock_va(0x82B00000UL),
			"seg4 link VA");
	}

	init_fixture(0, 0x1100000000UL, (void *)0x900000000000UL);
	ret = k3_ecam_init(&icfg);
	require(ret == -EINVAL, "seg0 rejected by seg2/4 init");
	require(mock_iomap_count == 0, "seg0 init maps nothing");

	init_fixture(3, 0x1300000000UL, (void *)0x910000000000UL);
	require(k3_ecam_init(&icfg) == -EINVAL,
		"unknown segment rejected");

	for (i = 0; i < 3; i++) {
		init_fixture(2, 0x1200000000UL, VA2);
		mock_iomap_fail_at = i;
		ret = k3_ecam_init(&icfg);
		require(ret == -ENOMEM, "ioremap failure returns -ENOMEM");
		require(mock_iomap_count == i + 1,
			"init stops at the failed mapping");
	}

	printf("%s: %d checks, %d failures\n",
	       failed ? "FAILED" : "PASS", checks, failed);
	return failed != 0;
}
'''


class K3EcamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ECAM_SRC.read_text()
        cls.patch = ACTIVE_PATCH.read_text()

    def test_map_bus_and_init_behavior(self):
        functions = "\n\n".join(
            extract_function(self.source, name) for name in EXTRACT
        )
        with tempfile.TemporaryDirectory(prefix="k3-ecam-test-") as d:
            c = Path(d) / "t.c"
            exe = Path(d) / "t"
            phy_defines = "\n".join(line for line in self.source.splitlines()
                                   if line.startswith("#define K3_ECAM_"))
            c.write_text(COMMON + "\n" + phy_defines + "\n" + functions + "\n" + TESTS)
            build = subprocess.run(
                ["cc", "-o", str(exe), str(c), "-Wall", "-Werror",
                 "-Wno-sign-compare"],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[:4000])
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("PASS:", run.stdout)
            match = re.search(r"PASS: (\d+) checks", run.stdout)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(int(match.group(1)), 60,
                                    "rig lost coverage")

    def test_source_contract(self):
        src = self.source
        self.assertIn("MODULE_LICENSE(\"GPL\")", src)
        self.assertNotIn("mutex", src)
        self.assertIn("pci_lock", src)
        code = "\n".join(
            line for line in src.splitlines()
            if not line.lstrip().startswith(("*", "/*"))
        )
        self.assertEqual(src.count("where & PCIE_ECAM_REG_MASK"), 2,
                         "own and child maps mask the register offset")
        self.assertIn("dw_pcie_version_detect(&seg->pci)", src)
        self.assertIn("SZ_16K", src)
        self.assertNotIn("0x3f20", src)
        self.assertEqual(src.count("num_ob_windows = 1"), 1)
        self.assertNotIn("num_ob_windows = 16", src)
        self.assertIn("devm_ioremap(", code)
        self.assertNotIn("devm_ioremap_resource(", code)
        self.assertNotIn("struct dw_pcie_rp", src)
        self.assertNotIn("seg->pp", src)
        self.assertIn("k3_ecam_link_up", src)
        self.assertIn("K3_ECAM_PHY_AHB_LINK_STS", src)
        self.assertIn("K3_ECAM_LINK_SMLH_UP", src)
        self.assertIn("K3_ECAM_LINK_RDLH_UP", src)
        self.assertIn("region_align = SZ_64K", src)
        self.assertIn("region_limit = SZ_4G - 1", src)
        self.assertIn("cfg0_base = cfg->win", src)
        self.assertIn("cfg0_phys = cfg->res.start", src)
        for base in ("0x80800000", "0x80B00000", "0x82D00000",
                     "0x81000000", "0x81300000", "0x82B00000"):
            self.assertIn(base, src, f"missing segment base {base}")

        seg0 = src.split("struct pci_ecam_ops k3_dw_seg0_ops", 1)[1]
        seg0 = seg0.split("};", 1)[0]
        self.assertIn(".map_bus\t= k3_dw_seg0_map_bus", seg0)
        self.assertIn("pci_generic_config_read", seg0)
        self.assertIn("pci_generic_config_write", seg0)
        self.assertNotIn(".init", seg0,
                         "seg0 must keep generic ECAM, no seg2/4 init")

        dw = src.split("struct pci_ecam_ops k3_dw_ecam_ops", 1)[1]
        dw = dw.split("};", 1)[0]
        self.assertIn(".init\t\t\t= k3_ecam_init", dw)
        self.assertIn(".bus_shift\t\t= 8", dw)
        self.assertIn("pci_generic_config_read", dw)
        self.assertIn("pci_generic_config_write", dw)

    def test_active_patch_matches_source(self):
        count, body = new_file_hunk(self.patch)
        self.assertEqual(body, self.source,
                         "active patch new-file hunk drifted from ecam source")
        self.assertEqual(count, len(self.source.splitlines()),
                         "active patch hunk header line count is stale")

    def test_rpm_spec_applies_ecam_patch(self):
        lines = CONFIG.with_name("kernel.spec").read_text().splitlines()
        self.assertEqual(lines.count(f"Patch900007: {ACTIVE_PATCH.name}"), 1)
        apply = f"ApplyPatch {ACTIVE_PATCH.name}"
        self.assertEqual(lines.count(apply), 1)
        self.assertLess(lines.index("ApplyPatch k3-gpio-acpi-v3.patch"), lines.index(apply))
        self.assertLess(lines.index(apply), lines.index('%{log_msg "End of patch applications"}'))

    def test_active_patch_linkage_rows(self):
        patch = self.patch
        self.assertIn(
            "obj-$(CONFIG_PCIE_SPACEMIT_K1) += pcie-k3-acpi-ecam.o", patch)
        self.assertIn("extern struct pci_ecam_ops k3_dw_ecam_ops;", patch)
        self.assertIn("extern struct pci_ecam_ops k3_dw_seg0_ops;", patch)
        self.assertIn("#ifdef CONFIG_PCIE_SPACEMIT_K1", patch)
        self.assertIn(
            '{ "SPMT  ", "K3      ", 1, 0, MCFG_BUS_ANY, &k3_dw_seg0_ops }',
            patch)
        self.assertIn(
            '{ "SPMT  ", "K3      ", 1, 2, MCFG_BUS_ANY, &k3_dw_ecam_ops,',
            patch)
        self.assertIn(
            '{ "SPMT  ", "K3      ", 1, 4, MCFG_BUS_ANY, &k3_dw_ecam_ops,',
            patch)
        self.assertIn("DEFINE_RES_MEM(0x1200000000UL, 0x10000)", patch)
        self.assertIn("DEFINE_RES_MEM(0x12c0000000UL, 0x10000)", patch)
        self.assertIn("#define MCFG_BUS_ANY\t\t\tMCFG_BUS_RANGE(0x0, 0xff)",
                      patch)

    def test_config_linkage_gate(self):
        cfg = CONFIG.read_text()
        self.assertIn("CONFIG_ACPI=y", cfg)
        self.assertIn("CONFIG_PCI=y", cfg)
        self.assertIn("CONFIG_PCIE_DW=y", cfg)
        self.assertIn("CONFIG_PCIE_DW_HOST=y", cfg)
        self.assertIn("CONFIG_PCIE_SPACEMIT_K1=y", cfg,
                      "K3 ECAM must be built-in: =m compiles out the "
                      "pci_mcfg rows and leaves unexported DW symbols "
                      "unresolved at modpost")
        self.assertNotIn("CONFIG_PCIE_SPACEMIT_K1=m", cfg)
        self.assertNotIn("CONFIG_PCI_LOCKLESS_CONFIG=y", cfg,
                         "map_bus relies on the core pci_lock")

    def test_ecam_geometry(self):
        cfgres = 0x10000
        bus_shift = 8
        self.assertEqual(cfgres >> bus_shift, 256,
                         "64 KiB / bus_shift 8 covers bus 0..255")
        self.assertEqual(0xff - 0x00 + 1, 256)
        self.assertIn(".bus_shift\t\t= 8", self.source)

    @unittest.skipUnless(FW_HEADER.is_file() and FW_MCFG.is_file(),
                         "firmware ACPI sources not present")
    def test_firmware_mcfg_binding(self):
        hdr = FW_HEADER.read_text()
        self.assertIn("'S','P','M','T',' ',' '", hdr)
        self.assertIn("SIGNATURE_64 ('K','3'", hdr)
        self.assertRegex(hdr, r"EFI_ACPI_OEM_REVISION\s+0x00000001")
        mcfg = FW_MCFG.read_text()
        self.assertIn("Structures[1]", mcfg)
        self.assertIn("0x1100000000", mcfg)
        self.assertNotIn("0x1200000000", mcfg,
                         "MCFG must not carry seg2; the kernel quirk "
                         "fabricates it")
        self.assertNotIn("0x12C0000000", mcfg,
                         "MCFG must not carry seg4; the kernel quirk "
                         "fabricates it")

    @unittest.skipUnless(FW_DSDT.is_file(), "firmware DSDT source not present")
    def test_firmware_dsdt_segments(self):
        dsdt = FW_DSDT.read_text()
        self.assertRegex(dsdt, r"Name \(_SEG, 2\)")
        self.assertRegex(dsdt, r"Name \(_SEG, 4\)")
        self.assertRegex(dsdt, r"Name \(_BBN, 0x00\)")
        self.assertIn("0x0000001200000000", dsdt)   # seg2 viewport
        self.assertIn("0x00000012C0000000", dsdt)   # seg4 viewport
        self.assertIn("0x000000120000FFFF", dsdt)   # seg2 RES2 64 KiB
        self.assertIn("0x00000012C000FFFF", dsdt)   # seg4 RES4 64 KiB
        self.assertIn("0x80800000", dsdt)           # DBI2
        self.assertIn("0x81000000", dsdt)           # DBI4
        self.assertIn("0x0000001200010000", dsdt)   # seg2 I/O CPU base
        self.assertIn("0x00000012C0010000", dsdt)   # seg4 I/O CPU base


if __name__ == "__main__":
    unittest.main()
