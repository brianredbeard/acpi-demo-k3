# Clock, reset, PHY, supply and Linux consumer audit — 2026-11-20

> **Current-state amendment (9b95f32):** [Recovery amendment](RECOVERY-AMENDMENT.md) distinguishes reported v26 hardware recovery from pending P1 ESOS work. Current manifest validation fails and the repository suite has two errors; original PASS results below belong to d3daf37. ACPI/platform inputs are unchanged.

This is a source audit, not a new hardware qualification. The pinned firmware publishes twelve physical RPMI clocks and one legacy stub. Publishing them does not wire them into the existing ACPI drivers. Most enabled ACPI peripherals still inherit firmware clock/reset/PHY state. The maintained firmware now includes UFS0, but the locked patch export still lacks it. This is an export lag, not missing maintained implementation.

## Source identity and scope

Evidence prefixes below identify actual files examined:

- `EDK:` is `/tmp/k3-independent-audit/platforms/`, reconstructed by the coordinating audit from `sources.lock.json` edk2-platforms revision `8e686e13d9f76e9acc478fa03bf1ba74f06517a2` plus all twelve listed patches. This is the canonical final firmware source for this report.
- `ESOS:` is `/tmp/k3-independent-audit/esos-clocks/`, reconstructed in this audit from `e0b8d955bdc84957da3b7bba8c89e35ee0d27c2b` using `git show` for every file touched by the seven locked ESOS patches, then applying those patches in order. All seven applications returned zero. It is a partial audit tree, not a build tree.
- `CARRY:` is `/home/bharring/Projects/K3-Ubuntu-Images/workdir/k3-maintained-efi/patches/acpi-kernel/`. These are actual local driver source copies, but are not a complete, pinned target kernel. Report conclusions about their code separately from claims about the running kernel.
- `DT:` is `/home/bharring/Projects/K3-Ubuntu-Images/workdir/efi-development/kernel-source/tree/arch/riscv/boot/dts/spacemit/`. This partial kernel tree contains DTS, headers, scripts, and licenses; no complete driver build tree was found there. Its board source identity must not be substituted for the later running kernel identity.
- `MASTER:` is `/home/bharring/Projects/linux/`, observed HEAD `20eef29b7c8465ac98d7dd6d6f2ac07a8d8056ca`. This is a comparison source, **not the RHEL 6.12 target**. In particular it does not contain `drivers/ufs/host/ufs-spacemit.c`.
- `DIRTY:` is `/home/bharring/Projects/K3-Ubuntu-Images/workdir/k3-maintained-efi/esos-reset-handoff/`, HEAD `e0b8d955bdc84957da3b7bba8c89e35ee0d27c2b` plus uncommitted changes. Its v24 policy is not in the pinned patch series. The adjacent maintained edk2-platforms tree was rechecked after the user committed UFS0: clean HEAD `a2a647a5173ee10f837b6e18eadf2b7313e14f15` (`a2a647a5`, UFS0) follows `a56c27ff` (restored LPI). `MAINT:` below means `/home/bharring/Projects/K3-Ubuntu-Images/workdir/k3-maintained-efi/edk2-platforms/` at that clean commit. The locked reconstruction still differs. ESOS DIRTY remains a distinct uncommitted tree.

`sources.lock.json` pins ESOS, ESOS-lite, edk2-platforms and a local OpenSBI snapshot; it does not pin a kernel component. `docs/kernel-master-audit-2026-11-19.md:4` describes a 6.12.0-284.el10 baseline with additional local patches. This report cannot prove exact target driver/config identity or module packaging from that description. No kernel build or live board access was performed.

## Inventory and interpretation

`clock-dependencies.csv` contains 404 records: all 178 `static SPACEMIT_CCU_*` declarations in the reconstructed ESOS CCU, the separate RPMI stub, all 50 named ClockDxe module entries, and all 175 raw clocks/resets/phys/power-domains/supply declarations in the three examined local K3/Pico/display DT files. The raw definitions and exact file/line are retained. A DT row's node column is the nearest lexical opening node, not a resolved full DT path; use the source line as authoritative. DT includes, overlays, and status inheritance are not flattened by this inventory.

`clocks.dot` includes all 178 CCU declaration nodes and 176 parent edges. Mux edges are **candidate parents**, not measured active parents. Reset pseudo-clocks and management-core clocks are intentionally retained. Blue nodes are published physical RPMI clocks. External roots appear as referenced nodes; their hardware rates are not independently measured here. ClockDxe module names are groups of register operations, not necessarily one physical clock, so they are kept separately in CSV rather than conflated with CCU names.

The inventory is exhaustive for these input declarations, not a claim to exhaust every K3 hardware clock. PLL3/4/5/7/8, display/DSI/eDP groups, QSPI, PCIe ports, other GMACs, and USB3 groups appear in ClockDxe but not the twelve-clock RPMI surface. Management-core UART/I2C/SPI/I2S/PWM/CAN/IRC/reset families in the CCU are internal, not exposed merely because they exist in its table. The larger Linux DT clock set is not a Linux ACPI clock provider.

## Published clock contract

ID/name evidence: `ESOS:bsp/spacemit/drivers/rpmi/k3/k3-rpmi-clk-ids.h:25` and its name array at line 50. Parent/register evidence: `ESOS:bsp/spacemit/drivers/clk/ccu-spacemit-k3.c:807-895` and corresponding header offsets at lines 77-84.

| ID | Clock | Declared parent(s) | Register and operation | Actual ACPI consumer conclusion |
|---|---|---|---|---|
| 0 | rproc_clk | None | Stub; reports enabled/500 MHz | Not a physical remote-processor clock |
| 1 | twsi0_clk | pll1_d78_31p5 / pll1_d48_51p2 / pll1_d40_61p44 | APBC + 0x2c, mux [6:4], gate bit 1 | I2C2 ACPI driver bypasses clocks; also this is TWSI0, not proof of I2C2 input |
| 2 | twsi0_bus_clk | apb_clk | APBC + 0x2c, bit 0 | Same consumer gap |
| 3 | gpio_clk | vctcxo_24 | APBC + 0x08, bit 1 | Driver asks `core`, not `gpio_clk` |
| 4 | gpio_bus_clk | apb_clk | APBC + 0x08, bit 0 | Driver asks `bus`, not `gpio_bus_clk` |
| 5 | sdh0_clk | pll1_d6_409p6 / pll1_d4_614p4 / pll2_d8 / pll2_d5 / dummy slots / pll1_dx | APMU + 0x054, divider [10:8], mux [7:5], gate bit 4 | No SDH ACPI node in pinned DSDT |
| 6 | sdh_axi_aclk | axi_clk | APMU + 0x054, bit 3 | No SDH ACPI node; shared SDH bus requires ownership beyond SDH0 |
| 7 | ufs_aclk | pll1_d5_491p52 / pll1_d6_409p6 / pll2_d6 / pll2_d5 | APMU + 0x268, divider [7:5], mux [4:2], gate bit 1 | Tracked kernel patch aliases `axi`; pinned DSDT lacks UFS0 |
| 8 | ufs_refclk | pll1_d64_38p4 / 2 | Fixed factor, nominal 19.2 MHz | Explicitly excluded by tracked UFS patch |
| 9 | emac0_bus_clk | axi_clk | APMU + 0x3e4, bit 0 | Carried ACPI setup does not wire it by this name |
| 10 | emac0_ref_clk | pll2_d120_25 | APMU + 0x3e4, bit 14 **active-low enable** | No demonstrated ACPI consumer lookup |
| 11 | emac0_rgmii_tx_clk | pll2_d24_125 | APMU + 0x3e4, bit 8 | Driver asks optional `tx`, not this name |
| 12 | usb2_bus_clk | axi_clk | APMU + 0x05c, bit 1 | Generic DWC3 uses other names; no alias in firmware description |

The APB mux candidates are 25.6/51.2/25.6/102.4 MHz (`ccu-spacemit-k3.c:808`). AXI chooses PLL1 /8 or /6 plus a divider (`:817`). Names encode nominal rates, not a measurement. `ufs_aclk` can select other parents/dividers; 491.52 MHz is historical qualified state, not an immutable consequence of its name.

## Findings

### CLK-01 — confirmed: provider enumeration is not consumer integration

`CARRY:experiments/rpmi-clocks/clk-rpmi-clkdev.c:479-500` registers parentless Linux clocks and global aliases with `con_id = RPMI name`, `dev_id = NULL`. It does not create device-specific `core`, `bus`, `tx`, `func`, `sclk`, or DWC3 aliases. The DSDT RCLK mailbox reference (`EDK:Platform/Spacemit/K3/AcpiTables/Dsdt/Dsdt.asl:503-528`) connects the provider to MPXY channel 8; it does not connect peripheral consumers to that provider.

GPIO's ACPI branch requests optional `core` and `bus` (`CARRY:experiments/task4-espi-ec/gpio-spacemit-k1-nested.c:596-611`). Ethernet requests optional `tx` (`CARRY:dwmac-spacemit-acpi.c:406`). Thermal requests optional `func`/`bus` (`CARRY:experiments/task4-espi-ec/k3_tsensor-policy.c:205-231`). I2C deliberately bypasses CCF and computes its divider from `spacemit,func-clock-rate` (`CARRY:experiments/task3-i2c/i2c-k1-acpi.c:861-885`). Thus successful probe or 13 debugfs clocks cannot establish Linux ownership, rate accuracy, or suspend/resume restoration for these blocks.

Consequence: firmware must continue to hold their clocks, resets, PHY configuration and supplies unless an explicit managed dependency is implemented and qualified. Add device-scoped mappings or named acquisition with deferred probe and lifetime management before treating a peripheral as RPMI-managed. Do not mechanically alias generic `bus` globally: unrelated controllers share that name.

### CLK-02 — confirmed: maintained UFS support has not reached the locked export; fallback remains unsafe to interpret as qualification

`EDK:.../Dsdt.asl:117-165` goes from ETH0 directly to USB2; there is no UFS0. `MAINT:Platform/Spacemit/K3/AcpiTables/Dsdt/Dsdt.asl:165-202` adds UFS0 in committed clean HEAD `a2a647a5`, including compatible `spacemit,k3-ufshc`, lanes-per-direction=2 and the APMU register property. This confirms maintained implementation; it does not update the locked twelve-patch export. Both views are intentionally distinguished.

`patches/kernel/0001-ufs-spacemit-ACPI-platform-data-path.patch:45-53` only adds `axi -> ufs_aclk`, intentionally omitting `ufs_refclk`. At lines 76-87, **any** failed lookup is logged then ignored; there is no deferred-probe return. At lines 91-96 the alias is global. Probe ordering can therefore leave the device on the documented 409.6 MHz fallback even if the provider appears later; the source comment identifies real qualified rate as 491.52 MHz. The patch's "20% off" wording is relative to the lower baseline; 409.6 is 16.67% below 491.52. Successful UFS I/O alone does not validate timing clock ownership.

The alias has no matching unregister path in this patch. The per-entry `devm_kstrdup` result is also not checked before adding the entry (lines 103-107). Those are secondary lifetime/allocation concerns; they are not reported as observed crashes.

### CLK-03 — confirmed: reset and clock register ownership overlaps without a cross-agent transaction

The UFS patch maps an absolute APMU register and updates reset bit 0 through Linux regmap (`patches/kernel/...:130-148`). ESOS gate/mux/divider updates operate on the same APMU + 0x268 register (`ESOS:.../ccu-spacemit-k3.c:876-880`). Firmware ClockDxe's UFS group also controls bits 0/1 (`EDK:Silicon/Spacemit/K3/Drivers/ClockDxe/ClockDxe.c:118-121`). Linux regmap locking and ESOS local clock locking do not, by themselves, serialize read-modify-write between processors. Concurrent operations could lose a bit update; actual collision is **unverified**. This is presently latent for the pinned DSDT, which lacks UFS, and relevant to the maintained UFS configuration.

Ethernet similarly exposes raw APMU control/delay addresses (`EDK:.../Dsdt.asl:151-152`; `CARRY:dwmac-spacemit-acpi.c:286`), while ESOS exports EMAC0 gates from the same control register. A single documented owner or serialized management command is needed before runtime gating/rate changes are declared safe.

### CLK-04 — confirmed: pinned firmware lacks per-clock rate policy; uncommitted policy is not evidence of completion

`ESOS:.../k3-os0_clk.c:281-296` limits match mode and requires a local set-rate operation, but contains no explicit per-clock allowlist or shared-consumer qualification. Its own comment calls this capability, with policy left for later. Gate-only clocks are protected from rate propagation; that is narrower than permission for every mutable mux/divider. RPMI metadata advertises one discrete boot rate, which limits ordinary consumers but is not ownership arbitration.

`DIRTY:bsp/spacemit/drivers/rpmi/k3/k3-os0_clk.c:78` adds an allowlist (all real consumers locked), while lines 246-266 compare parent **index 0**, not the active mux parent, and only published siblings. This is a bounded approximation; it cannot establish ownership of every enabled child in the full hardware clock tree. No unsafe rate change is demonstrated here. The current all-locked consumer policy reduces exposure, but the shared-parent guard needs correction before enabling mutable consumers. The same dirty file contains diagnostic SRAM writes at lines 220-221. None of these changes is included by the locked seven-patch reconstruction.

### CLK-05 — confirmed source mismatch: v24 platform idempotency cannot bypass the library's early rejection

`DIRTY:components/librpmi/lib/rpmi_service_group_clock.c:252-254` returns `RPMI_ERR_ALREADY` for a cached enabled clock **before** calling platform `set_state` at lines 257-258. This file has no working-tree changes in the inspected repository. The dirty v24 platform callback's enabled-state success shortcut (`DIRTY:.../k3-os0_clk.c:286-295`) is downstream of that rejection. Symmetric disabled-state rejection exists at library lines 210-212.

Therefore `docs/per-clock-rate-policy-2026-11-20.md`'s claim that service-layer idempotency is fixed is not established by the actual code inspected. Qualification must issue repeated SET_CONFIG through the real RPMI entry point and inspect response, not call the platform callback directly or just inspect its disassembly. This is a source-confirmed control-flow limitation; a new on-board failure was not induced.

### CLK-06 — probable lifetime defect in carried clkdev provider

`CARRY:experiments/rpmi-clocks/clk-rpmi-clkdev.c:486` registers clock hardware with devres, but line 500 uses unmanaged `clk_hw_register_clkdev`. No `clkdev_drop` or alias cleanup is present. Enumeration can fail on a later clock (`:601-605`) and unwind managed clock storage while earlier aliases remain. A successful probe followed by unbind has the same potential. `MASTER:drivers/clk/clkdev.c:392-418` supplies a managed alternative. Confirm against the exact target tree and fault-inject later-clock failure before declaring a demonstrated dangling lookup. Do not infer a failure merely from `devm_of_clk_add_hw_provider` under ACPI: the inspected master returns success for NULL OF node (`MASTER:drivers/clk/clk.c:5156-5157`).

## Per-peripheral ownership and missing dependencies

| Peripheral | Pinned ACPI and driver path | Clock/reset/PHY/supply owner and gap |
|---|---|---|
| UART COM0 | RSCV0003, 14.7456 MHz property (`EDK:.../Dsdt.asl:83-112`) | Firmware fixed-rate assumption; no RPMI UART or reset mapping. XScale carry is needed for the described UART mode. Frequency property is not a power dependency. |
| GPIO | PRP0001 K3 GPIO (`:329-349`), carried nested ACPI IRQ implementation | Firmware pre-enabled APBC clock/reset; optional clock names do not match provider. Wake/event operation cannot be certified by enumeration. |
| I2C2 + EEPROM | PRP0001 K1 I2C and I2cSerialBus child (`:353-393`), input-rate property 31.5 MHz | Firmware clock/pins; driver programs SCL divider and controller soft reset. Optional reset acquisition at carried driver line 917 does not furnish an ACPI reset provider. RPMI TWSI0 is not automatic I2C2 wiring. |
| TSEN | PRP0001 K3 tsensor (`:531`), sensor mapping/range properties | ReadyToBoot enables TSEN APBC gates and releases reset; driver tolerates absent clocks/resets. No TSEN RPMI ID. `EDK:.../AcpiClockInitDxe/K3AcpiClockInitDxe.c:68,130`; ClockDxe table lines 61-65. |
| ESPI / EC / PWM / FAN | DSDT ESPI + EC + PWM and fan reference (`:401-493`) | ReadyToBoot sets ESPI SCLK/MCLK and active-low reset bits; no ESPI RPMI ID. Driver bulk clocks can be empty and sclk/reset optional (`CARRY:experiments/task4-espi-ec/spacemit-k3-espi-acpi.c:709-738`). Internal controller and in-band resets remain Linux actions (`:637-638`). EC PWM/fan power is mediated through EC, not a SoC PWM RPMI clock. |
| Ethernet0 | DSDT raw APMU fields and PHY mode; carried ACPI platform setup | UEFI initializes bus/TX/PHY; ExitBootServices patch keeps clocks. PHY discovered by legacy MDIO scan (`CARRY:dwmac-spacemit-acpi.c:226-235`), not a declared PHY power/reset dependency. `EDK:.../DwEqosDxe/DwEqosSpacemit.c:848,917`; all SKU and error paths still matter. |
| USB2 | Borrowed Intel 808622B7 (`EDK:.../Dsdt.asl:165-203`), generic DWC3 | Firmware initializes PHY/gates/resets, OS inherits high-speed host configuration and no PHY or clock resources. Firmware `UsbHcdInitDxe/UsbHcd.c:637` enables clock/reset. Master DWC3 asks optional bus_early/bus_clk/ref/ref_clk/suspend/suspend_clk/utmi/pipe (`MASTER:drivers/usb/dwc3/core.c:2069-2119`) and optional reset (`:2326`); these are comparison names, not verified 6.12 implementation. |
| PCI0 | Generic PCI host namespace and ECAM; one published host | Firmware link/PHY/reset/clock and supply setup. `EDK:Silicon/Spacemit/K3/Library/K3PcieHostBridgeLib/K3PcieHostBridgeLib.c:678` enables module. No PCIe RPMI clocks or ACPI rail/PHY dependency in pinned DSDT. Runtime port power management needs explicit ownership. |
| UFS | Absent pinned; present maintained committed DSDT | Requires locked-export update, target driver integration, clock ordering/alias fixes and reset ownership qualification. |
| SDH0/1/2, other GMACs, USB3, extra PCIe, QSPI, display/audio/media | No matching published functional nodes in this DSDT | ClockDxe table and DT declarations do not enable these under ACPI. Twelve RPMI clocks do not cover their clock/reset/PHY/supply graph. Some firmware-only display/framebuffer operation may persist, which is not a native display-driver binding. |

The locked DSDT contains no `_PR0`, `_PR3`, or inclusion of `Power.asl`. The neighboring `Power.asl` describes a draft PCC power resource mechanism, but its existence does not make it live. Treat peripheral power resources as unimplemented in this namespace; CPU idle/domain work is a separate contract.

The Pico DT explicitly declares always-on AUX 3.3 V and 5 V rails (`DT:k3-pico-itx.dts:37-50`), PMIC inputs/regulators (`:150-245`), QSPI supply (`:326`), PCIe supplies and combo-PHY lanes (`:368-395`), USB hub supply (`:417`), and USB PHY/role dependencies (`:421-483`). These have no equivalent rail/controller namespace in the pinned DSDT. Firmware-held supply state may be sufficient for boot, but actual voltage, wake retention and suspend/resume behavior remain unverified. The ledger preserves these missing dependencies rather than assuming a clock alone is enough.

## Historical results and required qualification (updated by recovery amendment)

`docs/rpmi-clock-qualification-2026-11-20.md` reports 13 enumerated clocks and hardware readback for an earlier qualified configuration. `docs/per-clock-rate-policy-2026-11-20.md:5-16` explicitly says v21f-v23 used an under-patched tree and UFS successes tolerated fallback. Its hardware-results section remains a placeholder. These are historical statements, not live evidence from this audit, and cannot certify the pinned build or dirty v24 policy.

Useful next checks, with source fixes prepared separately: pin the exact target SRPM/config/carry hashes; verify actual platform driver bindings and clkdev lookups, not only clock enumeration; test provider delayed/failed probe and removal; exercise repeated RPMI enable/disable through librpmi; read gate/mux/divider registers before and after each consumer operation; validate reset transitions with clocks held; then test cold boot, warm reset and suspend/resume under concurrent I/O. Any runtime clock/reset test should first establish a single owner and avoid disabling storage/network clocks used by the test itself. No such hardware mutations were performed here.

## Driver-source traceability

These source copies were inspected directly; a SHA-256 identifies the exact local copy. They do not establish that the target boot used that copy. Generic platform-driver names below are candidate binding paths where exact target source was unavailable.

| ACPI device | Actual inspected driver/source | Inspection limit |
|---|---|---|
| COM0 | CARRY:experiments/kernel-cleanup/8250_platform-xscale-quirk.c | Platform UART carry exists; exact linked target binary unverified |
| ETH0 | CARRY:dwmac-spacemit-acpi.c | ACPI setup, optional tx, raw APMU, legacy MDIO inspected |
| USB2 | MASTER:drivers/usb/dwc3/core.c | Actual master driver only; 6.12 source unverified |
| PCI0 | Generic ACPI PCI/ECAM path; firmware K3PcieHostBridgeLib inspected | Exact target pci_mcfg quirk implementation not certified in this subaudit |
| GPIO | CARRY:experiments/task4-espi-ec/gpio-spacemit-k1-nested.c | Actual ACPI GPIO source and optional clocks inspected |
| I2C2 | CARRY:experiments/task3-i2c/i2c-k1-acpi.c | Actual ACPI divider/reset path inspected |
| EPR0 | at24 through PRP0001 atmel,24c02 | Parent/serial-bus description inspected; target at24 source not pinned |
| ESPI | CARRY:experiments/task4-espi-ec/spacemit-k3-espi-acpi.c | Actual optional clock/reset and controller reset paths inspected |
| EC0 | CARRY:experiments/task4-espi-ec/cros_ec_espi-acpi.c | Source file present; full EC protocol review outside this clock audit |
| PWM0 | CARRY:experiments/task4-espi-ec/pwm-cros-ec-acpi.c | Source file present; EC-mediated PWM, not SoC clock provider |
| FAN0 | pwm-fan using DSDT pwms reference | Generic target implementation not pinned |
| MPXY | SBI MPXY mailbox via RSCV0005 and firmware transport | Exact target mailbox source not recovered here |
| RCLK | CARRY:experiments/rpmi-clocks/clk-rpmi-clkdev.c | Actual enumeration/alias/failure/lifetime code inspected |
| TSEN | CARRY:experiments/task4-espi-ec/k3_tsensor-policy.c | Actual optional clocks/reset and ACPI policy branch inspected |
| UFS0 (maintained) | patches/kernel/0001-ufs-spacemit-ACPI-platform-data-path.patch | Actual added code inspected; complete target base driver not recovered |
| CPU / IC00 / PCI RES0 / DBI0 | Processor/interrupt-controller/reservation/host namespace | Not additional peripheral clocks; namespace does not imply a clock consumer |

| Local CARRY source | SHA-256 |
|---|---|
| dwmac-spacemit-acpi.c | `16b4bc10a6e5eca56da564b9e1c703f20108876f6210e2cb95b8cd55c8516f26` |
| experiments/rpmi-clocks/clk-rpmi-clkdev.c | `acc3a19af8403ae9fcfcf27d43ba44c5d8346785a0b1e9f1803f2e988b4d98ba` |
| experiments/task3-i2c/i2c-k1-acpi.c | `1fb33c0a57f9e8741c91c727abca63c614fedef605143cf149e9b66c20d7e2ec` |
| experiments/task4-espi-ec/gpio-spacemit-k1-nested.c | `85904499ecfb6e5f4ff39650df573f89838b77fd498e1ac9d6d30934a7c21bf6` |
| experiments/task4-espi-ec/k3_tsensor-policy.c | `3edb28c4648b1e6d1e861def27d95979d06a0bfa0594fa4f00468aa522b30ba6` |
| experiments/task4-espi-ec/spacemit-k3-espi-acpi.c | `d2c71d3e4f70e875a2cf543d146f05159620a088af9a8dfc8d98690e06e26b19` |
| experiments/task4-espi-ec/cros_ec_espi-acpi.c | `de49103f967944af538e6f3e06e832cd8c4ed6cfbab915541a584fa6cf9fd1ad` |
| experiments/task4-espi-ec/pwm-cros-ec-acpi.c | `dde37542e592a0ba1766092b7255ee0a076098683fecec8cf5cd97b0e168dac5` |
| experiments/kernel-cleanup/8250_platform-xscale-quirk.c | `fe44a51adf45fc6cdafbfdced7920155c491bd989fd1ba973a1487defbc72c02` |

Validation: CSV parses as 404 rows; all 178 CCU declaration names are unique; RPMI IDs 0–12 occur exactly once. DOT was generated from the same parent list; Graphviz is not installed, so renderer validation was not performed. `git diff --check` passed for tracked differences; these new audit files were separately parsed/read. No hardware writes or implementation edits occurred.

## Severity, remediation and discriminating tests

Severity is conditional on activating the relevant runtime path, not a claim of an observed crash.

| Finding | Severity / confidence | Concrete remediation | Discriminating validation |
|---|---|---|---|
| CLK-01 | High for runtime PM; confirmed source gap | Device-scoped consumer mappings; explicit deferral; retain firmware hold until each consumer is migrated | Trace each driver's clk_get and enable count; delayed provider probe; suspend/resume with register readback |
| CLK-02 | High reproducibility/timing; confirmed export lag and tolerant failure | Export maintained UFS0 commit; pin target kernel; defer on unavailable mandatory clock; scope alias to UFS device and manage lifetime | Compare rebuilt AML namespace to maintained source; force provider-before/after-UFS probe and require identical measured timing input |
| CLK-03 | High if concurrent writes; ownership overlap confirmed, collision unverified | Move shared APMU reset and clock operations behind one serialized service or establish enforceable cross-agent ownership | Instrument simultaneous reset/gate updates and assert unaffected bits survive; perform only on isolated non-boot test device |
| CLK-04 | Medium while advertised fixed-rate; confirmed missing pinned policy | Export reviewed policy; use active parents and all consumers before allowing mutations; qualify every allowed rate | Reject disallowed SET_RATE at protocol boundary; vary selected mux parent and enabled sibling, checking no register changes on rejection |
| CLK-05 | High functional blocker for inherited enabled clocks; confirmed source control flow | Define protocol idempotency consistently in library/controller path, not only callback; retire UFS exception only after qualification | Real RPMI enable-enabled and disable-disabled twice; assert expected success and stable gates, plus disabled-to-enabled transition |
| CLK-06 | Medium on failed probe/unbind; probable lifetime bug | Managed clkdev aliases or explicit cleanup paired with every registration | Inject enumeration failure after first alias, retry probe, unbind/rebind; no stale lookup, duplicate alias or invalid hw pointer |

## Matching and OF-specific API checks

PRP0001 matching an OF table is supported by Linux ACPI core, but it does not supply an `of_node`. Master evidence is `MASTER:drivers/acpi/bus.c:886-911,1020`. Matching is necessary, not proof that probe survives its DT assumptions. Exact target kernel verification remains outstanding.

| Node | Match evidence in inspected source | Probe portability evidence / limit |
|---|---|---|
| COM0 | CARRY:experiments/kernel-cleanup/8250_platform-xscale-quirk.c:289 RSCV0003; :301 ACPI table | :150 uses device_property_match_string for intel,xscale-uart quirk |
| ETH0 | CARRY:dwmac-spacemit-acpi.c:487 spacemit,k3-dwmac; :498 OF table | :180 separate ACPI setup; :193 device_get_phy_mode; :286 raw APMU path replaces OF syscon lookup |
| USB2 | MASTER:drivers/usb/dwc3/core.c:2911-2914 808622B7 | Generic optional resource path; borrowed Intel HID is a compatibility risk, not evidence of a K3-specific PHY driver |
| GPIO | CARRY:experiments/task4-espi-ec/gpio-spacemit-k1-nested.c:676 spacemit,k3-gpio | :570 device_get_match_data; :613 separate ACPI chip; OF bank path remains separate |
| I2C2 | CARRY:experiments/task3-i2c/i2c-k1-acpi.c:966 spacemit,k1-i2c | :837 device_property clock-frequency; :861 ACPI-specific input-rate/divider path |
| TSEN | CARRY:experiments/task4-espi-ec/k3_tsensor-policy.c:350 spacemit,k3-tsensor | :25/:36 device_property arrays, :192 temperature offset; optional ACPI clocks |
| ESPI | CARRY:experiments/task4-espi-ec/spacemit-k3-espi-acpi.c:800 spacemit,k3-espi | :517-556 device_property configuration; clocks/reset optional |
| EC0 | CARRY:experiments/task4-espi-ec/cros_ec_espi-acpi.c:830 google,cros-ec-espi | Table match exists; full transport probe and interrupt behavior not established by this clock review |
| PWM0 | CARRY:experiments/task4-espi-ec/pwm-cros-ec-acpi.c:274 google,cros-ec-pwm | :285 uses of_match_ptr; target CONFIG_OF and exact module build must preserve table for PRP0001 matching |
| RCLK | CARRY:experiments/rpmi-clocks/clk-rpmi-clkdev.c:618 riscv,rpmi-clock | :547 mbox_request_channel; :610 devm_of_clk_add_hw_provider is not the consumer lookup mechanism; actual lookup uses clkdev aliases |
| UFS0 maintained | MAINT DSDT :198 spacemit,k3-ufshc | Tracked kernel patch :35-38 identifies OF clock parsing limitation, :166/:209 branch on missing of_node; full target base match table unverified |
| EPR0 / FAN0 / MPXY / PCI0 / IC00 / CPUs | Namespace matches expected at24 / pwm-fan / SBI-MPXY / generic PCI / interrupt / processor paths | No exact target driver source and config recovered here; no unsupported claim that generic upstream is sufficient |

Do not describe these carried drivers as unmodified upstream support. The UFS driver was absent from the inspected master file path; actual carried ACPI adaptations and target packaging are required. Other master driver presence alone does not certify the matching target modules.

## Regeneration

Retained generator: `clock_inventory.py` beside this report. It requires Python 3 and explicit source roots; it performs no firmware/kernel writes. Run from any directory with:

```sh
python3 docs/audit-2026-11-20/clock_inventory.py \
  --esos /tmp/k3-independent-audit/esos-clocks \
  --edk /tmp/k3-independent-audit/platforms \
  --dt /home/bharring/Projects/K3-Ubuntu-Images/workdir/efi-development/kernel-source/tree/arch/riscv/boot/dts/spacemit
```

Use `--out` for an alternative output directory. ESOS and EDK roots must be reconstructed at the identities above; this script does not fetch/apply patches. The macro parser handles this audited source syntax, not arbitrary C preprocessing. It inventories candidate parents and raw DT declarations, not active gates or flattened status. For resolved DT relationships and effective board-node coverage, use the coordinating audit's `dt-dependencies.csv` (flattened Pico/COM graph); the raw clock ledger intentionally retains source definitions and their line numbers.

The latest committed post-mortem supersedes the initial missing-patches/hand-build causal explanation: it reports clock-service failure since v20 and recovery with v12 ESOS. Thus neither UFS throughput nor a denied suspend licenses a clock-service PASS. The original thirteen-ID source graph is retained; the recovered seventeen-entry runtime clock tree needs names/IDs and consumer evidence before reconciliation. CLK-01 through CLK-06 remain source/interface findings, not assertions that the recovered board currently fails. See CLK-07 and REL-03/04 in the amendment.
