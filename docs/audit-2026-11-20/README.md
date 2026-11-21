# K3 independent ACPI/UEFI audit — 2026-11-20

> **Current-state amendment (9b95f32):** [Recovery amendment](RECOVERY-AMENDMENT.md) distinguishes reported v26 hardware recovery from pending P1 ESOS work. Current manifest validation fails and the repository suite has two errors; original PASS results below belong to d3daf37. ACPI/platform inputs are unchanged.

**Release decision: HOLD.** The available implementation does not support a defensible claim of complete DT equivalence, generic upstream Linux interoperability, or hardware-qualified ACPI/UEFI compliance. This review found reproducible AML defects, incomplete clock-consumer and resource-ownership contracts, reliance on local Linux changes, runtime-service defects/risks, and a split between maintained source and locked release inputs. No target hardware tests were executed by this audit. The subsequent team-reported v26 recovery is incorporated separately; it does not qualify the pending P1 series. Historical successful boots are useful evidence for their particular configurations, not release qualification of either audited source state.

This is an evidence-backed static audit and qualification package, **not a completed silicon compliance certification**. The inventories cover every node/property in the available flattened DT inputs, but many rows remain unresolved. The normative register is an applicability/closure register, not an exhaustive transcription of all specifications. Full historical bootloader modifications, exact target board revision, full deployed kernel source/configuration, immutable firmware image identity and installed tables remain unavailable or unattributed. Those limitations prevent completing the requested proof; they are explicit release blockers rather than silent exclusions.

## Original audited snapshot (retained)

| Evidence | Identity / meaning |
|---|---|
| Integration repository | Original `d3daf37`; amendment reviews `9b95f32`. See the amendment for current validation failure and separately reported v26 recovery. |
| Locked platforms | `8e686e13d9f76e9acc478fa03bf1ba74f06517a2` plus all twelve manifest patches, reconstructed under `/tmp/k3-independent-audit/platforms`. |
| Maintained platforms | User committed UFS during review. Final clean HEAD `a2a647a5173ee10f837b6e18eadf2b7313e14f15`, parent `a56c27ff` restores `_LPI`. Both DSDTs compiled and tested separately. |
| Export difference | Locked DSDT has 27 devices and no UFS/_LPI; maintained DSDT has 28 devices with UFS and `_LPI`. The commit is present; the integration manifest/export has not incorporated it. |
| EDK2 core | Neighbor vendored files; their Git lookup resolves to enclosing K3-Ubuntu-Images commit `0dbb43a7303de574dc3e98ddae7666b68cf664e0`, **not an EDK2 upstream revision**. Core revision unestablished and unpinned. |
| ESOS | Locked base `e0b8d955...` plus seven patches; ESOS-lite `1e166dbe...`. Clock review reconstructed touched files. Dirty v24 development is distinguished from locked inputs. |
| OpenSBI | Manifest `b4152e0761ac1986dfd313876eaff8d7f63cd703`, local-only repository URI. Existence of a patch outside that component's patch list does not mean it is applied. |
| OS DT baseline | Imported source-manifest kernel `6.12.0-264.rv.10.el10`; Pico and COM260 include hierarchy flattened, including disabled nodes. |
| Firmware-internal DT | K3Cpus.dtsi + K3.dtsi + MUSE-PicoPinctrl.dtsi and all three board wrappers flattened separately. These are not interchangeable with the OS DT. |
| Linux | Local carries describe kernel `6.12.0-284.el10`; complete running source/build identity unverified. Upstream comparison `20eef29b7c8465ac98d7dd6d6f2ac07a8d8056ca` is not substituted for it. |
| Hardware documents | Vendor docs-chip `4879ed5dfb5415212099dd898906cd893b3fa286`. Hardware assignment tables examined; board PCB revision and matching schematic/errata signoff unavailable. |
| Physical target/profile | MUSE/Pico is the implemented ACPI build. COM260 is a separate, unqualified board target. No declared ratified BRS-I release profile or required-device allowlist found. |

All path prefixes and line references in the subsystem reports identify the source snapshot, not an assertion that the current flash contains it. `evidence/source-identities.json` and hashes identify retained evidence. The DT source-manifest has provenance for its imported includes; it does not describe all subsequent U-Boot/SPL fixups. Obtain the original last-known-good flash/DTB and bootloader source/configuration to close that boundary.

## Deliverable map

| Requested artifact | Files |
|---|---|
| A assessment / J release gate | This report |
| B bidirectional migration | `devices.csv` (one row per DT node), `equivalence.csv` (every property plus reverse ACPI rows), all `*-inventory.json`, `maintained-acpi-inventory.json` |
| C normative compliance | `standards.md`, `standards.csv` |
| D dependencies | `clock-dependencies.csv`, `clocks.dot`, `dt-dependencies.csv`, `dt-dependencies.dot`, `clocks-drivers.md` |
| E interrupts/MSI/PCI | `interrupt-routes.csv`, `interrupts.dot`, `interrupts-pcie.md` |
| F hardware regression | `regression.csv`;56 procedures; auditor hardware tests unexecuted, v26 team reports linked separately; REG-29 offline AML subset executed |
| G defects / H proposed fixes | `findings.csv`, detailed subsystem reports, sequence below |
| I continuous validation | `VALIDATION.md`, executable Python checks, retained command logs and fixed-table rebuild recipe |
| UEFI boot/runtime | `uefi-runtime.md` |

CSV matching by base address is a **candidate**, never semantic equivalence: register size, bus address translation, interrupts, clocks and children can differ. Raw DT cells are preserved alongside resolved phandle edges. The graph's clock parent alternatives do not claim measured active mux selections. Unmapped disabled devices remain documented; disabled status is not approval to omit them from a future board profile. An absent `_STA` uses ACPI default presence; it does not mean firmware has probed the board.

## Findings that drive the decision

1. **The release inputs do not reproduce maintained functionality.** UFS and restored CPU idle are committed in maintained EDK2 but absent from the locked export. EDK2 core/toolchain/early firmware and full target Linux are not completely pinned. A local OpenSBI URI prevents independent retrieval. Fix this before correlating boot logs to source.
2. **PCI interoperability depends on custom handling.** The presented MCFG uses a DesignWare CFG-shift arrangement and local `k3_dw_ecam_ops` filtering. A direct-attached NVMe boot does not prove standard ECAM behavior through switches or all functions. INTx `_PRT` is absent. Other PCI controllers enabled by Pico DT are not functionally represented in this ACPI namespace. See PCI-01/02; required-device policy is unresolved.
3. **Clock enumeration is not resource migration.** GPIO asks for `core`/`bus`, Ethernet for `tx`, while the RPMI provider exports global aliases under different names. I2C bypasses CCF. Most devices inherit initialized firmware state. UFS tolerates provider failure without deferral, while reset and firmware clock operations share APMU registers without cross-processor serialization. The pinned export lacks the claimed per-clock policy; the library's early `ALREADY` return also precedes the attempted platform idempotency fix.
4. **AML has executable specification failures.** Both DSDTs compile without warnings, but `_SB._OSC` clears an unknown UUID's capability DWORD and omits the masked-capability status for a valid `0x180` request reduced to `0x80`. The offline regression reproduces both. ACPI 6.6 §6.2.12 specifies these return semantics. A four-byte malformed request also raises `AE_AML_BUFFER_LIMIT`; that is recorded as robustness behavior, not proof a valid caller violates the ABI. [Normative source](https://uefi.org/specs/ACPI/6.6/06_Device_Configuration.html#osc-operating-system-capabilities).
5. **Runtime flash needs correction and qualification.** QSPI runtime mapping failures are ignored; a VA-change callback attempts to convert an embedded scalar structure as a pointer. Actual faults have not been induced. No nonidentity virtual-map runtime write test closes the complete FVB/SPI/QSPI path. Time services use a virtual clock, not independently verified persistent physical RTC behavior.
6. **Functional DT coverage is incomplete.** Additional PCIe ports, USB3/other USB controllers, Type-C child, PMIC/regulators, PDMA, QSPI OS interface, native display and other enabled baseline resources lack equivalent functional bindings or documented firmware-held/exclusion contracts. These are unresolved migration requirements, not automatically required release features. Firmware display output is not proof of native display-driver migration.
7. **Interrupt metadata is substantially more credible than blanket claims suggest.** The final MADT has one IMSIC structure, eight RINTCs, one supervisor APLIC, correct source-range arithmetic and guest identity count63. The August fix changes guest identities511→63, not guest-index bits6. Existing documentation incorrectly derives GEILEN7 from63 identities; hardware documentation and runtime guest-file observations need reconciliation. No new vector-affinity, GPIO-cascade, interrupt-load or KVM test was run.

No new confirmed P0 hardware failure was demonstrated. That statement is not clearance of P0: runtime mapping/memory retention, reset/suspend sequencing and interrupt delivery remain untested at the required scope. Severity and confidence are separate in `findings.csv`; possible memory-safety effects are explicitly conditional rather than reported as observed corruption.

## Namespace, tables and ownership

ACPICA loads both namespaces. They have no AML OperationRegions, `_INI` methods or conditional `_STA` methods in the expanded active DSDT. Thus uninstalled OpRegion handlers are not an active-AML problem in these inputs; unused Power.asl/PCCT drafts are not silently counted as implemented. Processor identities0..7 match rebuilt MADT/RHCT/PPTT. Fixed-table structures/offsets pass sampled structural validation. This does not prove advertised ISA, cache organization, physical hart population, 24 MHz timebase or timer behavior. No SRAT/SLIT/RIMT appears in the active table INF; these are conditional features requiring hardware/profile applicability decisions, not universal required tables.

The active serial child is I2C2/EPR0 via I2cSerialBus; EC is under ESPI with GPIO interrupt resource, PWM under EC, and FAN refers to PWM. The EC window overlaps an ESPI parent window by design and requires subresource ownership analysis, not automatic rejection. Repeated PRP0001/UID0 identities were flagged for compatible/path review, not declared a confirmed collision. Phandle resolution in DT and ACPICA namespace loading do not establish Linux probe ordering, GPIO IRQ-domain behavior or supplier lifetime. See the carried driver review.

RSDP/XSDT/FADT DSDT pointers and checksums are installed/updated by core ACPI services. Build-time fixed tables deliberately contain placeholder checksum and pointer fields. They must not be reported as bad runtime checksums. Installed root pointers, allocation types, length bounds against physical mappings and post-ExitBootServices lifetime remain BLOCKED pending a target dump and EFI memory map. ACPI-only means no OS hardware-DT dependency; internal firmware DT use itself is not prohibited by this audit.

## Proposed implementation order

No implementation code was changed.

1. Freeze a board revision/profile/required-device contract; export maintained UFS/_LPI only with matching ESOS/OpenSBI/target-kernel qualifications. Lock EDK2 core, toolchain, early firmware, kernel/config/carries and full image hashes. Keep unsafe idle states gated until the complete suspend/timer/cache path passes.
2. Correct `_OSC` buffer validation/error semantics and RES0 ResourceConsumer marking; replace borrowed USB/DBI identities with supported, documented bindings. Run offline regressions before hardware deployment. Do not invent replacement HIDs.
3. Correct runtime pointer conversion and propagate runtime-MMIO registration errors. Test nonidentity mappings, persistent variables, reset and time semantics in an isolated harness, then hardware.
4. Define one owner for every clock/reset/power/register domain. Wire device-scoped clock acquisition with deferred probe and managed alias teardown. Serialize UFS/GMAC reset and clock updates across processors; a local alias-only patch cannot fix ownership. Verify rate-policy enforcement through the complete RPMI service path.
5. Resolve PCI topology: standard ECAM hardware configuration if possible; otherwise a reviewed, pinned upstreamable quirk with accurately bounded support. Establish INTx wiring or explicitly exclude affected endpoints. Validate all advertised buses/functions/windows and MSI/MSI-X independently of DMA.
6. Reconcile each unmapped DT node/property and each ACPI-only object against hardware and drivers. Preserve serial-bus hierarchy, supplies, PHY/pins and DMA dependencies; implement or explicitly exclude hardware in the release profile. Do not mass-add namespace placeholders.
7. Execute REG cases with identical attributable DT/ACPI builds. Capture installed tables, maps, registers, counters and I/O hashes. Run full cold/warm/idle/reset stress only after ownership is established; negative table/controller/power tests stay in isolated harnesses.

## Release gates

| Gate | Current decision |
|---|---|
| Zero unresolved P0 | **BLOCKED**: no fresh hardware memory/interrupt/suspend validation; no assertion of zero latent P0 |
| Zero P1 affecting required scope | **FAIL/BLOCKED**: confirmed interface/integration gaps; required scope not frozen |
| Required static interfaces pass | **FAIL**: `_OSC` regressions reproduced; full runtime installation unverified |
| All enabled required devices accounted | **BLOCKED**: complete input inventory exists, but many semantic dispositions unresolved |
| Clock/reset/power dependencies traced | **BLOCKED**: raw topology captured; active states/ownership/retention incomplete |
| Wired IRQ/MSI routes validated | **BLOCKED**: static shipped routes agree; hardware load/affinity/teardown absent |
| Children correctly enumerated | **BLOCKED**: carried implementation and historical logs only; missing children remain |
| ACPI-only target boot | **NOT TESTED in this audit**; historical evidence not bound to exact reviewed images |
| Required I/O/DMA regression | **NOT TESTED** |
| Deviations/test limitations documented | **PASS for this audit package**; product release waivers remain unapproved |

The recovered v26 composition is the reported working rollback baseline; P1 promotion requires the new clock-service and verified-source gates. The appropriate next milestone is closure of the source/ownership/interface findings and an attributable hardware qualification run. A clean compiler result and existing Linux login do not change this HOLD decision.
