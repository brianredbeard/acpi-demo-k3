// SPDX-License-Identifier: GPL-2.0
/*
 * SpacemiT K3 ACPI PCI config access for DesignWare viewport segments.
 *
 * Segments 2 (10G NIC) and 4 (Wi-Fi) have 64 KiB config viewports
 * with config-shift mode disabled: generic ECAM computes a 1 MiB
 * offset for bus 1 and lands in the translated PCI I/O aperture.
 * Root-port config lives at each controller's DBI base; every
 * downstream access selects the target bus/dev/fn in the outbound
 * iATU (CFG0 directly below the root, CFG1 farther) and then
 * accesses the viewport at the register offset — the DT driver's
 * dw_pcie_other_conf_map_bus behavior, resused for ACPI.
 *
 * The firmware (rhct12+) trains the links, publishes the ACPI
 * root bridges (PCI2/PCI4 with _SEG 2/4) and the _CRS windows:
 *   seg 2: viewport 0x1200000000/64K, DBI 0x80800000, ATU 0x80B00000
 *   seg 4: viewport 0x12C0000000/64K, DBI 0x81000000, ATU 0x81300000
 * Segment 0 (NVMe) has genuine 256 MiB ECAM and is untouched.
 *
 * rhct12 audit: docs/wifi-pcie-acpi-2026-11-22.md, "Recommended
 * implementation" — K3-specific ops, DBI root access, serialized
 * iATU downstream selection, single-entry MCFG preserved.
 */

#include <linux/io.h>
#include <linux/mutex.h>
#include <linux/pci.h>
#include <linux/pci-acpi.h>
#include <linux/pci-ecam.h>
#include <linux/sizes.h>

#include "pcie-designware.h"

/*
 * Per-segment state. The firmware initialized the controllers;
 * we only need the register bases and a dw_pcie wrapper for the
 * DW core's iATU programming.
 */
struct k3_ecam_seg {
	struct dw_pcie	pci;
	struct dw_pcie_rp pp;
	void __iomem	*dbi_base;
	void __iomem	*cfg0_base;	/* 64 KiB config viewport */
	resource_size_t	cfg0_size;
	void __iomem	*atu_base;
};

static DEFINE_MUTEX(k3_ecam_atu_lock);

/*
 * Root-bus access: the root port's own config space at DBI.
 * (dw_pcie_own_conf_map_bus behavior.)
 */
static void __iomem *k3_ecam_own_map(struct k3_ecam_seg *seg, int where)
{
	return seg->dbi_base + where;
}

/*
 * Downstream access: serialize the iATU target selection (the
 * viewport is a single shared window), program the outbound ATU
 * for the target bus/dev/fn, then hand back viewport + where.
 */
static void __iomem *k3_ecam_child_map(struct k3_ecam_seg *seg,
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
	atu.parent_bus_addr = (u64)seg->cfg0_base;
	atu.pci_addr = busdev;
	atu.size = seg->cfg0_size;

	mutex_lock(&k3_ecam_atu_lock);
	ret = dw_pcie_prog_outbound_atu(pci, &atu);
	mutex_unlock(&k3_ecam_atu_lock);

	if (ret)
		return NULL;

	return seg->cfg0_base + where;
}

static void __iomem *k3_ecam_map_bus(struct pci_bus *bus,
				     unsigned int devfn, int where)
{
	struct pci_config_window *cfg = bus->sysdata;
	struct k3_ecam_seg *seg = cfg->priv;

	if (!seg)
		return NULL;

	if (pci_is_root_bus(bus)) {
		/*
		 * Root-bus ghost filter (the Nov 18 gpioy-qualified rule,
		 * seg-2/4 form): the DW controller answers every root-bus
		 * devfn with the root port's config (64 fake bridges seen
		 * on 3j, their bus claims blocking the downstream scan).
		 * Only devfn 0 is reachable on the root bus.
		 */
		if (devfn)
			return NULL;
		return k3_ecam_own_map(seg, where);
	}

	return k3_ecam_child_map(seg, bus, devfn, where);
}

/*
 * Per-bridge init: resolve the _CRS windows for this segment and
 * build the DW wrapper. The DSDT (rhct12+) publishes the viewport
 * as the bridge's first MEM window and the DBI/ATU as PNP0C02
 * reservations (DBIn/ATUn devices, _UID matching the segment).
 */
static int k3_ecam_init(struct pci_config_window *cfg)
{
	struct device *dev = cfg->parent;
	struct acpi_device *adev = to_acpi_device(dev);
	struct acpi_pci_root *root = acpi_driver_data(adev);
	struct k3_ecam_seg *seg;

	static const struct {
		u16 segment;
		resource_size_t dbi;
		resource_size_t atu;
	} k3_seg_bases[] = {
		{ .segment = 2, .dbi = 0x80800000, .atu = 0x80B00000 },
		{ .segment = 4, .dbi = 0x81000000, .atu = 0x81300000 },
	};
	int i;

	for (i = 0; i < ARRAY_SIZE(k3_seg_bases); i++)
		if (k3_seg_bases[i].segment == root->segment)
			break;
	if (i == ARRAY_SIZE(k3_seg_bases))
		return -EINVAL;		/* segment 0 keeps genuine ECAM */

	seg = devm_kzalloc(dev, sizeof(*seg), GFP_KERNEL);
	if (!seg)
		return -ENOMEM;

	/* The viewport: the config window's own mapping. */
	seg->cfg0_base = cfg->win;
	seg->cfg0_size = resource_size(&cfg->res);

	/* v1: silicon-fixed DBI/ATU (the DSDT reserves both; _CRS
	 * resolution is the refinement — same bases, less hardcode).
	 */
	seg->dbi_base = devm_ioremap(dev, k3_seg_bases[i].dbi, SZ_4K);
	if (!seg->dbi_base)
		return -ENOMEM;
	seg->atu_base = devm_ioremap(dev, k3_seg_bases[i].atu, SZ_64K);
	if (!seg->atu_base)
		return -ENOMEM;

	/*
	 * The DW wrapper: the minimum for prog_outbound_atu —
	 * dbi/atu bases, the viewport count, and the addressing
	 * the firmware configured (config-shift disabled).
	 */
	seg->pci.dev = dev;
	seg->pci.dbi_base = seg->dbi_base;
	seg->pci.atu_base = seg->atu_base;
	seg->pci.num_ob_windows = 1;	/* single shared viewport */
	seg->pp.va_cfg0_base = seg->cfg0_base;
	seg->pp.cfg0_size = seg->cfg0_size;

	cfg->priv = seg;

	dev_info(dev, "K3 ECAM seg %d: viewport %pR via iATU (DBI %pa)\n",
		 root->segment, &cfg->res, &k3_seg_bases[i].dbi);

	return 0;
}

/*
 * Segment 0 (genuine 256 MiB ECAM, NVMe root port): the DW controller
 * does not filter type-0 config TLPs for unused root-bus slots, so a
 * standard ECAM read of any non-root-port devfn on bus 0 returns the
 * downstream endpoint's ID (ghost multiplication — 32 slots reporting
 * 1dee:5216). Mirror the DT pci-host-generic pci_dw_valid_device()
 * filter (the Nov 18 gpioy-qualified fix): only devfn 0 on the root
 * bus is reachable; downstream buses enumerate normally.
 */
static void __iomem *k3_dw_seg0_map_bus(struct pci_bus *bus,
					 unsigned int devfn, int where)
{
	struct pci_config_window *cfg = bus->sysdata;

	if (bus->number == cfg->busr.start && devfn)
		return NULL;

	return pci_ecam_map_bus(bus, devfn, where);
}

struct pci_ecam_ops k3_dw_seg0_ops = {
	.pci_ops = {
		.map_bus	= k3_dw_seg0_map_bus,
		.read		= pci_generic_config_read,
		.write		= pci_generic_config_write,
	},
};

struct pci_ecam_ops k3_dw_ecam_ops = {
	.init			= k3_ecam_init,
	/*
	 * bus_shift 8: pci_ecam_create's size math needs the 64 KiB
	 * viewport to cover the declared [bus 00-ff] (65536 >> 8 = 256
	 * buses). The generic ECAM offset is never used — map_bus
	 * computes viewport + where via the iATU — so the shift only
	 * satisfies creation.
	 */
	.bus_shift		= 8,
	.pci_ops		= {
		.map_bus	= k3_ecam_map_bus,
		.read		= pci_generic_config_read,
		.write		= pci_generic_config_write,
	},
};
