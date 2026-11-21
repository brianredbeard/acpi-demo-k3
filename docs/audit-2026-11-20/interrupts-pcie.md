# Independent interrupt and PCIe audit — 2026-11-20

Scope: static reconstructed shipping sources, DT, Linux consumers, manufacturer documentation, and already-recorded boot evidence. No hardware writes or new boot tests were performed. Severity denotes potential effect; confidence denotes evidential certainty, not hardware qualification.

## Source identities and notation

`P/` means `/tmp/k3-independent-audit/platforms`, reconstructed from edk2-platforms baseline `8e686e13d9f76e9acc478fa03bf1ba74f06517a2` plus this repository's ordered twelve patches. `A/` means `P/Platform/Spacemit/K3/AcpiTables`; `D/` means `P/Platform/Spacemit/K3/DeviceTree`; `L/` means `/home/bharring/Projects/linux`, HEAD `20eef29b7c8465ac98d7dd6d6f2ac07a8d8056ca`; `H/` means `/home/bharring/Projects/spacemit-docs-chip`, HEAD `4879ed5dfb5415212099dd898906cd893b3fa286`, origin https://github.com/spacemit-com/docs-chip. Linux is a comparison consumer, not proven source of the running kernel. The adjacent maintained edk2-platforms was initially inspected at `a56c27ff2200bf7251405e57585461b4712f81b2` with a dirty DSDT including UFS. The user subsequently committed it as `a2a647a5`; it is a separate maintained state, not the integration repository’s twelve-patch reconstruction. Maintained DSDT UFS0 adds IRQ135 at line193; all following PCI source references in this report remain relative to the reconstructed integration state.

`D/Os/source-manifest.json:2` identifies imported DT as kernel-6.12.0-264.rv.10.el10, source RPM SHA256 `471d1cb4acdc3b13d208e6a06bd99a47258d989d0991b250e5bd857eddcf6bf2`. Recorded kernel284 boot evidence cannot establish binary equivalence to that import or to this final patch stack. Independent canonical-source fixed-table builds and comparisons were subsequently completed; see the verification section below. No running-firmware table extraction was performed.

## Reconstructed topology and consistency

| Item | Final ACPI | Comparator / conclusion |
|---|---|---|
| RINTC | 8 enabled harts, IDs and UIDs 0..7; ExtIntcId 0 | `A/Madt.aslc:39-101`; matches OS DT CPU interrupt parents 0..7 at `D/Os/Sources/arch/riscv/boot/dts/spacemit/k3.dtsi:1726-1729` |
| IMSIC MMIO | hart h: `0xe0400000 + h*0x40000`, size `0x40000` each | Combined `0xe0400000..0xe05fffff`, matches OS DT's 2 MiB range at line1722; 4 KiB pages and 6 guest-index bits imply 256 KiB hart stride |
| IMSIC identities | supervisor511, guest63 | `A/Madt.aslc:107-108`; OS DT1733-1734 agrees; zero identity is reserved |
| IMSIC address encoding | guest bits6, hart bits4, group bits0, group shift24 | `A/Madt.aslc:109-112`; OS DT1731-1732 agrees. Hart bits4 reserve address capacity for16 harts; they do not require exposing16 CPUs. Group shift24 is inert with zero group bits |
| APLIC | ID0, hardware ID SPMT0001, zero IDCs,512 sources, GSI base0, `0xe0804000/0x4000` | `A/Madt.aslc:116-125`; `A/Dsdt/Dsdt.asl:68-80` IC00 has RSCV0002, UID0, _GSB0, same range. OS DT1737-1743 agrees. Hardware manual `07_interrupts.md:15` specifies MSI-only output |
| Wired interrupt arithmetic | GSI = source ID because GSI base0 | Linux `drivers/irqchip/irq-riscv-aplic-main.c:237-246` subtracts GSI base; no +1 adjustment is appropriate for these nonzero source IDs |

The six shipped DSDT wired routes agree with the manufacturer assignment table: UART42, GMAC131, USB105, GPIO58, I2C2=38, TSEN61. All use level/active-high; GPIO is shared and the others exclusive. See `interrupt-routes.csv`. UFS135 is present in maintained HEAD `a2a647a5`, DT and experimental logs, but absent from reconstructed shipping DSDT: this is integration export lag, not a maintained-source omission. EC uses a GPIO interrupt resource/cascade rather than a direct APLIC Interrupt descriptor; actual polling/IRQ behavior must be checked in the carried driver. The firmware DT machine APLIC delegates sources1..512 (`D/K3.dtsi:124` uses `riscv,delegate`, while imported OS DT1784 uses `riscv,delegation`); only supervisor APLIC belongs in this OS MADT. Successful existing APLIC interrupts support actual delegation on that boot, not proof of every firmware-DT parser accepting both names.

## Mandatory August 2026 IMSIC correction

Verified from the actual upstream commit in local Linux git and independently downloaded official GitHub patch: [69f95409f0053f787ad60175944080621a8b7d95](https://github.com/torvalds/linux/commit/69f95409f0053f787ad60175944080621a8b7d95), authored 2026-08-17. Its sole DT change is `riscv,num-guest-ids` **511 → 63**; `guest-index-bits` remains **6**. It cites X100 VS-mode identity capacity64 including reserved identity0. This is not a correction of the guest-file address stride, nor a change from63 guest files to7. [Original submission](https://patch.msgid.link/20260817033038.2286436-1-guoren@kernel.org).

There are three distinct quantities:

1. Guest identities/file:63 usable nonzero interrupt identities, read by Linux IMSIC and used by KVM for maximum guest interrupt IDs (`L/drivers/irqchip/irq-riscv-imsic-state.c:643-648`, `L/arch/riscv/kvm/aia.c:729-732`).
2. Guest-index address bits:6, reserving64 4 KiB pages/hart including supervisor page. This yields63 address slots, not a promise all slots are implemented (`irq-riscv-imsic-state.c:890-937`).
3. Actual usable guest external interrupt lines/files: KVM probes HGEIE and clamps by mapped guest-file capacity (`L/arch/riscv/kvm/aia.c:613-625`). Existing log `docs/v15-phaseA-console-log.txt:121` reports7. It is independent of the63 identity count.

**INT-01 — Medium, high confidence, stale firmware DT.** `D/K3.dtsi:177-178` still advertises511 guest identities, while final MADT and imported OS DT correctly advertise63. Firmware-DT comments at182-188 correctly distinguish reserved63 slots from7 implemented X100 VS files. Correct the stale identity count when that DT is qualified; determine its actual consumers before claiming a shipping ACPI failure. Final MADT requires no change for the upstream fix.

**INT-02 — Low, high confidence, incorrect prior audit inference.** `docs/kernel-master-audit-2026-11-19.md:17` says “63 guest IDs ⇒ GEILEN 7”. That implication is false; revise the evidence statement to distinguish the independent quantities above. The final values themselves are correct.

**INT-03 — Evidence gap, high confidence in disagreement.** Manufacturer `H/en/key_stone/k3/k3_docs/k3_usermanual/08_cpu.md:23` says X100 GEILEN8; current firmware DT comments and observed KVM line count say7. The same manual's A100 section65 claims7 VS files despite firmware DT188 claiming none for A100. These are documentation inconsistencies, not grounds to change X100 MADT addressing or expose additional CPUs. Obtain a vendor erratum and per-hart HGEIE implementation evidence if precise GEILEN terminology is required. The August patch does not resolve this discrepancy.

## PCI ECAM, routing and MSI

Final `A/Mcfg.aslc:35-44` declares segment0, buses00..ff, base `0x1100000000`; thus ECAM spans256 MiB through `0x110fffffff`. DSDT PCI0 segment/base bus and bus window match (`A/Dsdt/Dsdt.asl:207-246`); reservation RES0 spans exactly that range. Nonprefetchable PCI `0x10000000..0x7fffffff` translates by `0x1100000000` to CPU `0x1110000000..0x117fffffff`, adjacent to but not overlapping ECAM. Prefetchable `0x1800000000..0x18ffffffff` is identity mapped. All agree with `P/Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc:464-486`.

Imported DT PCI0 config resource is only64 KiB and its 32-bit memory window starts earlier (`D/Os/Sources/arch/riscv/boot/dts/spacemit/k3.dtsi:474-490`). This is an intentional difference between a DT DesignWare driver that programs configuration transactions and the ACPI path relying on firmware-prepared CFG-shift windows; blindly copying DT windows into MCFG would be incorrect.

Firmware `P/Silicon/Spacemit/Library/DesignWarePcieControllerLib/DesignWarePcieControllerLib.c:1318-1345` maps bus0 and bus1 with a2 MiB CFG0 outbound window, and buses2..255 with CFG1. Existing boot `docs/v15-phaseA-console-log.txt:50,57` reports `k3_dw_ecam_ops` and an NVMe endpoint at00:00.0, not a conventional root-port header. This is evidence of an intentionally unusual enumeration path.

**PCI-01 — High portability limitation, high confidence.** This MCFG is not independently demonstrated usable with generic ECAM operations. Firmware extends CFG0 into bus0; local boot depends on `k3_dw_ecam_ops` ghost filtering. No matching quirk exists in inspected upstream `L/drivers/acpi/pci_mcfg.c`, and the kernel quirk is not in this repo's kernel patch set. MCFG alone cannot describe that filtering. Require an independently identified kernel284 source/patch and test root-bus function filtering, bus1 aliases, bridge/switch enumeration and extended configuration before claiming generic ACPI PCI compatibility. Existing direct-attached NVMe success is narrower evidence.

**PCI-02 — Medium limitation, high confidence.** PCI0 has no `_PRT` or interrupt link devices (`A/Dsdt/Dsdt.asl:207-326`). Live logs342-349 and358-359 explicitly report no GSI for PCI INT A; NVMe nevertheless creates queues at365. MSI-capable devices can work; an INTx-only endpoint or MSI-allocation fallback lacks a described route. `_OSC` granting PCIe capability does not supply INTx routing. Determine whether board policy intentionally excludes INTx or qualify actual pin-to-APLIC wiring and add routing.

**PCI-03 — Medium, high confidence.** ECAM reservation RES0 is PNP0C02 but its QWordMemory has `ResourceProducer` (`A/Dsdt/Dsdt.asl:283-294`). It describes consumed ECAM register space, not an allocation window produced for children; change to ResourceConsumer in a separately qualified correction. The root bridge's real bus/BAR windows should remain producers.

**PCI-04 — Medium portability risk, high confidence.** DBI0 claims borrowed AMZN0001 (`A/Dsdt/Dsdt.asl:300-322`) plus PNP0C02 CID. The source itself acknowledges it identifies Amazon Annapurna Labs DBI. This can attract unrelated platform behavior on other kernels. A reservation-only proper ID or documented SpacemiT binding requires qualification; successful current boot does not legitimize the borrowed HID.

MSI is coherent at the description level: OS DT487 points PCI to supervisor IMSIC; ACPI MADT establishes the same global MSI controller. Linux IMSIC platform code supports PCI MSI and MSI-X (`L/drivers/irqchip/irq-riscv-imsic-platform.c:278-304`) and composes target addresses from the per-CPU supervisor file. PCI MSI bypasses the APLIC; wired UART/USB/etc traverse it. The final table's 512 wired sources do not imply512 simultaneously allocated IMSIC vectors on every hart. IMSIC identity allocation and CPU affinity are separate runtime decisions.

`PCI0._CCA=0` (`A/Dsdt/Dsdt.asl:214`) agrees with firmware's NonCoherentDmaLib selection (`MUSE-Pico.dsc:85`) and DT's lack of `dma-coherent` on PCI0. This is a consistency check, not a cache-coherency hardware proof. MSI writes target interrupt MMIO and should not be treated as coherent RAM DMA; declaring noncoherent DMA does not disable MSI. Recorded NVMe queues and filesystem mounts support an operational MSI/DMA path on that particular boot, but do not prove all MSI destinations, affinity migration, guest assignment, inbound address reachability or cache-maintenance correctness. No endpoint MSI/MSI-X register dump, interrupt-count affinity sweep, current iATU register snapshot, or identity-bound running kernel source was available in this sub-audit.

## Required follow-up evidence

Before widening qualification: identify and export the exact running kernel quirk; retain decoded MADT/MCFG/DSDT from the same boot; compare their hashes with reconstructed artifacts; capture per-CPU interrupt counts and endpoint MSI/MSI-X capabilities; test affinity changes and suspend/resume without losing APLIC/IMSIC state; obtain vendor clarification of GEILEN wording. Do not use existing unrelated suspend findings as proof of interrupt-controller retention. These are proposed tests, not actions performed here.

## Independent fixed-table compilation and binary verification

All six fixed tables were rebuilt successfully from `P/` into `/tmp/k3-independent-audit/fixed-tables` using the existing module GNUmakefile’s RISC-V GCC/linker/GenFw commands, redirecting output and canonical platform include/source paths. Existing EDK2 headers and generated AutoGen.h were reused; this is not an independent whole-firmware build or regeneration of PCDs. First attempt lacked WORKSPACE and failed to find Base.h; supplying WORKSPACE and EDK_TOOLS_PATH resolved it. The final build returned0. Build log, preprocessed sources and decoded data remain in that temporary directory.

| Table | Header length | Revision | SHA256 of header-length table bytes | Existing Build table bytes identical |
|---|---:|---:|---|---|
| Madt | 384 | 7 | `5c3a323429e497f77be1d0e7177a1c527366d6bc3c8eeee8226c88370db9161e` | Yes |
| Mcfg | 60 | 1 | `c17d5d71f96cb981edc1692254c818f266ead1af211ee92f422e44691ea678e5` | Yes |
| Rhct | 538 | 1 | `2e396901bb79c6d4356b45908ee03279464474f86d39cf0e5c6c37bed0cc6071` | Yes |
| Pptt | 832 | 3 | `3c627b36e084a14e0ebda9163b07f7e902bd2b8751e802a1db74fd8975dffebf` | Yes |
| Fadt | 276 | 6 | `8aaa93259c411c4170773c0f7dc11ea43c8fb00d2179480924f31653efec7e90` | Yes |
| Spcr | 98 | 4 | `3677a2589a95091218eb1043bc219ed43391b5d8523018c86cab7078144629e9` | Yes |

The full .acpi files include linker tail data/padding and differ; only header-length table payloads were compared. All checksum bytes are zero in these pre-install artifacts; firmware installation must compute checksums. This is not evidence of invalid runtime checksums.

Decoded MADT contains exactly eight type24/length36 RINTCs, one type25/length16 IMSIC and one type26/length36 APLIC; values match the topology above. RHCT has11 nodes (ISA, CMO, MMU, eight hart-info), each hart-info length24 with processor UID0..7 and three node offsets. PPTT has one package, two clusters and four leaf processors per cluster with UIDs0..7; all node traversal lengths terminate at header length832. Thus MADT/RHCT/PPTT CPU identity counts agree for X100. This does not qualify the ISA string or cache topology against silicon.

Captured binaries, exact executed commands (`build.log`), rewritten Makefile and workstation-specific `rebuild.sh` are retained in `evidence/fixed-tables/`. `python3 docs/audit-2026-11-20/fixed_tables.py` passes; it validates lengths, topology values, RHCT/PPTT references and sampled reserved fields, and rejects three mutated MADT cases (zero length, oversized length, wrong supervisor ID count). It explicitly does not validate post-install checksums.
