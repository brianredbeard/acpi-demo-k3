# Pico-ITX rhct12-wifi firmware and ACPI audit

**Decision.** Retain v12 as the known-good RHEL-on-NVMe baseline for this Pico and kernel. Open separate qualification items for Linux access to PCI2/PCI4, GPIO and radio binding, deep idle/resume, and runtime flash variables. The most urgent prospective regression is in ESOS patch 0011, which is absent from v12.

## What actually booted

| Boundary | Evidence and result |
|---|---|
| NOR → firmware | Transaction `pico-acpi-rhct12-wifi-001`, serial `HW4MPK3161280211`. Verified both full NOR digests, the manifest digest `10db6054fb5a765df55f2d60d18b372fc21db3db7b2061364e7225380bb4d3de`, an EDK2-only write at `0x210000` of `0x319000` bytes, and byte equality outside it. The readback slice, bundle FIT and isolated RELEASE FIT all hash to `6bbaf41176c87e887740b71cac61387365aca8e9a2f579f3d8534e82a3eac932`. |
| ESOS → OpenSBI | ESOS runs on the remote processor and provides RPMI services. OpenSBI on the application harts uses those services for HSM and reset and exposes SBI to the supervisor. These are cooperating runtimes. The ESOS and OpenSBI payloads match the earlier lpi2q bundle byte for byte. The v12 flash replaced EFI only. OpenSBI reported RPMI HSM, system reset and system suspend, SBI 2.0 and no CPPC backend. |
| EFI → GRUB → RHEL | The v11d debug trace shows the NVMe, RTL8127 and RTL8852BE IDs and the Red Hat shim device path on NVMe. The later v12 RELEASE boot reached RHEL 10.3 with `6.12.0-dbg1-dbg1`, a gpioy initramfs and `clk_ignore_unused`. XFS mounted UUID `3c7c2b87-67c7-478b-a1bf-3f9dd49803dc` on `nvme0n1p2`. The three NVMe block rows are a namespace and its two partitions. |
| EFI → ACPI → Linux | The packaged DSDT is 8,195 bytes, SHA-256 `63bc318d9118daeec4e5c22871c7635ce6d69de85766f685b34f61ada5094747`. The retained live command printed the matching first 16 hex digits. The serial capture shows a GRUB menu entry containing an override edited for this boot. Save a persistent no-override entry and the full live digest with future receipts. Linux lists FADT, MADT, MCFG, PPTT, RHCT, SPCR and DSDT, starts eight CPUs, initializes IMSIC/APLIC, binds the Chrome EC over eSPI, and sees all three PCI root devices. |
| ACPI → PCI endpoints | Linux negotiates PCIe capability control on all roots. It enumerates the NVMe on segment 0 and explicitly reports missing ECAM regions for 2 and 4. The v11d firmware scan and v12 Linux probe are different observations. End-to-end Ethernet, Wi-Fi and Bluetooth remain open. |

The underlying records are the [installer report](</home/bharring/k3-backups/pico-acpi-rhct12-wifi-001/report.json>), [actual isolated manifest](</home/bharring/bisect/out-v12r/manifest.json>) and the retained serial capture. Relevant serial lines are 40292/48114/56564 and 110445 for v11d, then 139257 onward for v12, including 139503–139529 for PCI, 139604 and 139623 for GPIO/EC, and 139857 for root mount. The raw console contains interactive credentials. Redact it before sharing or publishing excerpts and rotate the exposed credential.

## PCI configuration and resource ownership

**Keep the single-entry MCFG.** Segment 0 has a 256 MiB aperture at `0x1100000000`. A narrowly matched filter for absent root functions is a reasonable compatibility measure there. Preserve the working NVMe path and check root-port versus endpoint identity explicitly. The debug firmware sees the endpoint on bus 1, while dbg1 reports the NVMe at `0000:00:00.0`. Successful I/O proves the boot path, but does not establish that Linux reproduced the physical hierarchy.

**Segments 2 and 4 need a different configuration-access implementation.** Each has one 64 KiB viewport, at `0x1200000000` or `0x12c0000000`, with configuration-shift mode disabled. Root-port configuration comes from DBI. Firmware selects the destination bus/device/function in the DesignWare outbound address translation unit (iATU) for downstream accesses, uses CFG0 immediately below the root and CFG1 farther down, then accesses the register offset in the viewport. This applies after EFI hands control to Linux too. The tracked patch rejects nonzero devfn on the root bus, then calls generic `pci_ecam_map_bus()`. Its standard bus-1 offset is 1 MiB, already inside the translated PCI I/O aperture. A different shift alone cannot select a target. [Tracked quirk](../patches/kernel-rpm/series/el10-284/k3-ecam-mcfg-quirk.patch) · [Firmware access implementation](../../edk2-platforms/Silicon/Spacemit/Library/DesignWarePciSegmentLib/DesignWarePciSegmentLib.c) · [Linux PCI/ACPI contract](https://docs.kernel.org/PCI/acpi-info.html)

**Recommended implementation.** Keep the ACPI roots as the enumerators. Scope the Linux host-support path to the matching K3 layout and segments and reuse the existing DesignWare root/child configuration operations where practical. Supply verified DBI, iATU and viewport resources and ensure a config read/write and its target selection are serialized per controller. Check link state, preserve routing for I/O and memory transactions, and return device-absent for unreachable functions. Avoid a second host driver claiming or retraining the same controller. If hardware can instead supply genuine linear ECAM for the required buses, that is the more portable firmware design. It requires verified address space and hardware decoding before advertising MCFG or `_CBA` ranges.

There are three independent obstacles in the 284 RPM path. The tracked spec applies UFS and GPIO and omits the PCI patch. The proposed patch uses a Kconfig guard that does not match `PCIE_SPACEMIT_K1` and references accessors absent from this 284 tree. Even a compiled match supplies operations without a configuration resource. With no MCFG entry or `_CBA`, 284 returns `-ENXIO`. Giving generic ECAM a 64 KiB resource still cannot map a 1 MiB bus. Gate the actual SRPM on its digest, applied source, resolved config and linked implementation before another board trial. The archived SRPM is an older freeze under the same NVR. The exact remote retry input was unverified. [Spec](../patches/kernel-rpm/series/el10-284/kernel.spec) · [Expected payload](../patches/kernel-rpm/payload/k3-ecam-mcfg-quirk.txt)

**Fix the AML reservations alongside the kernel work.** I evaluated the released AML with ACPICA and decoded the root-bridge PCD records from the flashed FIT.

| Resource | Released AML | Firmware configuration or trace |
|---|---|---|
| PCI2/PCI4 configuration reservations | RES2 and RES4 each consume 16 MiB | Each viewport is 64 KiB. The reservations also cover the 1 MiB I/O aperture and the actual v11d MMIO allocations at `0x1200200000` and `0x12c0200000`. |
| PCI2 non-prefetchable PCI memory | `0x00110000..0x7fefffff`, length `0x7fdf0000` | PCD ends at `0x7fffffff`, length `0x7fef0000`. EFI could allocate from the final 1 MiB that Linux was never offered. |
| Bus and I/O producers | Both roots describe buses 0–255 and PCI I/O 0–0xfffff | Both agree with the PCD. Host bases are `0x1200010000` and `0x12c0010000`. v12 declares a 40-bit I/O space. v10d recorded both registrations failing with the 32-bit map. |

Reserve the actual controller register windows and compare every translated consumer and producer interval, including non-prefetchable and prefetchable memory, in the FIT check. Also check the compiled SEC I/O address width against the highest translated byte. The existing checker validates bus and I/O descriptors but drops the memory triples. The new GCD pre-registration loop also discards errors, and its independent necessity with a 40-bit map has not been demonstrated. [Released ASL](../../edk2-platforms/Platform/Spacemit/K3/AcpiTables/Dsdt/Dsdt.asl) · [Artifact verifier](../edk2_verify.py)

## GPIO and radio control

**Keep one GPIO provider for the controller and one Linux consumer for each independently controlled radio line.** The gpioy test kernel demonstrated that an early, flat 128-line provider can deliver EC events using pin 43. Preserve that ACPI numbering and the DT binding. Share register and bank operations in the SpacemiT driver, with small firmware-specific setup paths for enumeration, clock ownership and interrupt registration. Keep the provider available early for the built-in EC. Give the kernel, modules and initramfs an unambiguous common release identity. A previous gpioy boot failure mixed kernel and initramfs artifacts. [GPIO patch history](../patches/kernel-gpio/README.md) · [Initramfs incident](gpioy-poweroff-postmortem-2026-11-21.md)

* **Fix resource bounds first.** The evaluated GPIO `_CRS` declares `0xd4019000..0xd40190ff`. Bank 3 starts at offset `0x100`. The 284 adapter initializes all four banks and writes, for example, the fourth bank's mask at offset `0x134`. Page rounding can make that code appear to work. Verify the documented register block and reserve its full extent, validate the range in probe, and compare the vendor DT, which also declares 0x100 bytes. The two radio pins and EC pin are in the first two banks, so their tests cannot qualify bank 3. [GPIO AML](../../edk2-platforms/Platform/Spacemit/K3/AcpiTables/Dsdt/Dsdt.asl) · [284 adapter](../patches/kernel-rpm/series/el10-284/k3-gpio-acpi.patch)
* **Preserve GPIO error and IRQ semantics.** The adapter converts optional-clock errors, including a real `-EPROBE_DEFER`, to `-EINVAL`. A zero count of literal `-517` log messages can therefore miss dependency failures. Its IRQ type setter accepts level requests while only programming edge registers, the shared-parent handler claims even an empty interrupt, and bank-wide mask/edge updates are unlocked read-modify-writes. Return the original clock error, reject unsupported trigger types, protect per-bank updates and test shared IRQ teardown, simultaneous edges and suspend/wake. The existing passing EC probe is valuable regression coverage. [284 GPIO adapter](../patches/kernel-rpm/series/el10-284/k3-gpio-acpi.patch)
* **Fix the consumer probe independently.** AML supplies one named, active-high shutdown GPIO per device, WLAN 35 and Bluetooth 30. The 284 `rfkill-gpio` probe reads the properties and then, for every ACPI companion, requires a match in its legacy GPS ID table. `PRP0001` fails before it requests either line. Preserve the legacy GPS mappings and support property-described devices using their named GPIOs and radio type. Confirm the resolved built-in/module config and actual consumer binding. [284 driver](</tmp/k3srpm/linux-6.12.0-284.el10/net/rfkill/rfkill-gpio.c:125>) · [Linux GPIO property convention](https://docs.kernel.org/firmware-guide/acpi/gpio-properties.html)
* **Settle what each line controls electrically.** If it implements an independent radio block, rfkill is a good owner. If it removes power from an enumerated PCIe or USB function or a shared combo module, model device or shared power sequencing and coordinate it with the transport driver. Give each line one owner. First test the EC, then each radio independently, including block/unblock, reprobe and suspend/resume while the other radio is active. Verify the logical state, physical function and driver ownership. A Wi-Fi entry in NetworkManager is insufficient evidence for the power sequence.

## ESOS, OpenSBI and EFI patch integrity

1. **Hold ESOS 0011.** The released ESOS firmware matches the policy build through 0008. Its monitor requires all consumers to release before it will release its own AP hold. A host test with all cores stopped reproduced that circular condition. Applying staged 0011 permits the AP hold to release while DMA still holds the domain. The monitor immediately calls the commit function, which checks only the ACTIVE state. With the existing RT-Thread stubs and a simulated M2-enter interrupt, the staged path invoked M2 enable once and reached ASLEEP with one DMA reference outstanding. Recheck all holders atomically when committing. Test the composed monitor path with AP-only, AP+DMA, concurrent acquisition and timeout before promotion. Three ACPI idle-state names and lower measured power when offlining CPUs do not establish this path. [Shipped monitor and commit](../patches/esos/0007-k3-domain-ownership-p1.patch) · [Staged release predicate](../patches/esos/0011-ownership-sticky-block-and-provider-release.patch)
2. **Test RPMI at the message boundary.** In a host run of the matched librpmi clock handler, repeated enable and repeated disable returned wire status `-6` (`ALREADY`), without calling the K3 platform callback. That contradicts the stated idempotence policy even though callback-level tests pass. Also, staged CPPC 0010 passes a null fastchannel to a constructor that rejects it. Test group registration and a real request before exposing `_CPC`. CPU idle, CPPC and system wake have distinct acceptance criteria. The release boot reports no CPPC backend and records suspend denials. [Clock policy](per-clock-rate-policy-2026-11-20.md) · [CPPC patch](../patches/esos/0010-cppc-service-group.patch) · [Suspend and wake evidence](p2-scoping-2026-11-21.md)
3. **Make the release reproducible from a clean checkout.** The shipped ESOS and OpenSBI images match the qualified lower layers, but the development lock also includes ESOS 0009–0011. The OpenSBI lock points to local commit `51a9d0f9` while its note describes an older `fw_dynamic` hash. All 13 EDK2 patch hashes and their order verified. Applying them to `8e686e13` produced tree `fdc10dce4bf22c75d82b3f00e29db7b9fa80d015`, differing in 61 paths from the qualified `ff348957` tree `09caae1bcfe3ac6c3bdb31eff7053123594475e6`. The isolated build manifest identifies the correct tree. The sealed bundle carries an older source-head file, invalid build JSON with literal shell substitutions, and a qualification file describing three MCFG entries. Create a new release record referencing the immutable flashed digest. Require replayed tree equality, build epoch, every FIT subimage hash, schema-valid provenance and the installer receipt. Retain the OpenSBI object source in a portable repository or Git bundle. [Source lock](../sources.lock.json) · [Patch series](../patches/edk2-platforms/series) · [Bundle provenance](</home/bharring/bundles/pico-acpi-rhct12-wifi/provenance/edk2-build-manifest.json>)
4. **Constrain EFI fixes to their demonstrated scope.** The shared Port A logic selects x2 whenever A is on and B is off. Other SKU masks satisfy that condition, including FML13V05, whose DSC describes x4. Use board wiring or a per-SKU setting and test the other boards separately. The flash-variable virtual-address callback assumes an identity mapping. Reaching Linux exercises the transition but does not establish runtime variable write/read/delete persistence or nonidentity mappings. Keep an operator-controlled private-variable test separate from the boot test. [Port policy](../../edk2-platforms/Silicon/Spacemit/K3/Library/K3PcieHostBridgeLib/K3PcieHostBridgeLib.c) · [FVB bisect](fvb-va-bisect-2026-11-22.md)

## ACPI method results and qualification limits

ACPICA executed the extracted AML offline. For each of PCI0, PCI2 and PCI4, a PCI `_OSC` query requesting control `0xff` returned status `0x11` and control `0x10`. An unknown UUID on PCI2 returned status `0x04` and preserved the other DWORDs. Linux independently records the PCIe capability grant on all three roots. The platform-wide `\_SB._OSC` has a separate defect. Requesting support `0x180` returned `0x80` with status zero. It should report the cleared capability in status bit 4. A one-DWORD malformed buffer also raised `AE_AML_BUFFER_LIMIT`. Correct the valid-input status first and validate buffer lengths before creating fields. [ACPI 6.6, operating system capabilities](https://uefi.org/specs/ACPI/6.6/06_Device_Configuration.html#osc-operating-system-capabilities)

The retained quick-check command ran a single `fwts dmicheck` and read the last summary in an appendable results file. It reported 47 passes, zero failures and one skip. The subsequent broader v12 serial run lists **17 failed checks**: three BRS-I SMBIOS structures, eight per-hart SBI_CRET encodings, three RTC wakealarm checks, two RHCT ISA-profile checks and one missing `_STA` check. The same run reports eleven successful ACPI checksum checks and nine CPU hotplug round-trip passes. Classify each failure against the hardware, specification and tester version. In particular, SBI places `0x11000000` in the platform-specific retentive range. A type-range diagnostic and a real wake failure need different follow-ups. Record immutable per-boot results, test binary and version, skip reasons and any waiver. [Serial failure list](</tmp/k3-serial-full.log:140797>) · [SBI HSM suspend types](https://docs.riscv.org/reference/sbi/ext-hsm.html) · [Prior FWTS triage](fwts-findings-2026-11-21.md)

**Acceptance order.** First freeze the known-good boot receipt, inputs and qualified scope. Correct the ACPI resource bounds and test the GPIO provider with the known-good EC. Build a separately identifiable 284 kernel with verified PCI and rfkill source and effective config. On a subsequent controlled boot, verify each root and exactly one expected downstream device, the BARs against the corrected windows, the bound drivers and increasing MSI counters under traffic. The AML supplies no legacy INTx routing for these roots. Prove NIC traffic, Wi-Fi association and independent radio control before claiming those functions. Keep ESOS power changes on a separate flash cycle.

This was a read-only hardware audit using saved images and captures. Installer inspection, `python3 meta.py validate`, the final-FIT PCI profile with bus limit 255, and all 67 repository tests passed on the host with `K3_EDK2_TEST_FIT` pointing to the flashed bundle and `K3_ESOS_CACHE` pointing to the local clone. The audit added this report. No firmware, kernel package or board configuration was changed.

## Reproducibility closure (2026-11-23)

The rhct12-wifi provenance set is regenerated and installer-verified.

- **Tree identity.** `ff348957` carries tree `09caae1b`; the release lock
  (`edk2-build.lock.json`, platforms revision `ff348957`, zero patches)
  reproduces it by construction — the qualified tree is a git checkout.
- **Series drift, quantified.** Applying the 13-patch bring-up series
  (`sources.lock.json`) to `8e686e13` yields tree `fa9bb57b`, which differs
  from `09caae1b` in **63 paths** (26 docs, plus DSDT/AcpiTables, BrsCheckDxe,
  AcpiNvsDxe, SMBIOS type fixes, UiApp override, MUSE-Pico DSC) — the series
  serializes only the bring-up spine, not the 46-commit qualified range. The
  series must NOT be used to reproduce this release; the note is recorded in
  the bundle's `provenance/edk2-build-manifest.json`.
- **Provenance defects fixed.** `edk2-source-head.txt` `d313946d` →
  `ff348957`; `edk2-build-manifest.json` regenerated (the heredoc-unexpanded
  `$(stat…)`/`$(sha256sum…)`/rhct11 paths replaced with real payload hashes
  from the shipped `payloads/edk2.bin`, sha `6bbaf411…`); the qualification
  file's "MCFG Structures[3]" corrected to the single-entry table
  (segment 0, 256 MiB ECAM; segs 2/4 via the SPMT:K3 quirk ops).
- **Build epoch.** `manifest.json` now carries `build_epoch`
  `1795345608` (ff348957's commit time — the same source
  `build_edk2.py` derives `SOURCE_DATE_EPOCH` from).
- **Gates.** All payload hashes verified against disk; every provenance JSON
  parses; `k3-firmware inspect --bundle …` passes ("All payload lengths and
  SHA-256 hashes verified"); repository suite green with
  `K3_EDK2_TEST_FIT` pointed at the bundle.

Open follow-up (audit's portable-source ask): retain the OpenSBI object
source as a git bundle or portable repository; the current lock points at
local commit `51a9d0f9` with a stale `fw_dynamic` note.

## rhct13 candidate assembled (2026-11-23)

Built, verified, and packaged for inspection — NOT flash-qualified.

- **Content**: thermal-trips (`cdfda4a4`), `_OSC` status-bit + buffer-length
  fixes (`3b2ff7f0`), resource bounds (`d6d9a1a9`), the Port A SKU gate
  (`e0a11126` + token/INF fixes), and the GPIO `_CRS` extent 0x100→0x800.
- **Build**: isolated, lock-pinned at `96a276aa` (tree `f0ab6d8b`,
  epoch `1795401403`); PCIe profile check passed.
- **Verification**: full suite 67/67 with the candidate ITB as the FIT
  target — the extended memory-triple checker covers the RES2/RES4
  64 KiB viewports and the PCI2 non-prefetchable bounds.
- **Bundle (rev 2, `8b171654`)**: `~/bundles/pico-acpi-rhct13-candidate`
  (bundle sha `0e3bfbde…`). The first packaging (`24ca3e2d…`) carried a
  REAL defect caught on cross-check: the thermal-trips 75/95 hotspot pair
  sat at flat index 3 while the ACPI zone builder indexes pairs by RAW
  channel (`channel*2`) — ch3 received the hotspot thresholds and the
  actual ch4 hotspot read the default. Fixed (pair at index 4, ch3 at
  74/94 matching the driver's own defaults, ch1 slot documented as the
  unwired placeholder); the DSDT comment now states the raw-index
  contract. Lower layers byte-identical to the qualified baseline;
  installer inspection passes.
- **Status**: candidate. Flashing waits for the operator's call; the
  kernel-side thermal zone driver rides the cycle-3 RPMs.

## rhct13 flash qualification (2026-11-23, firmware cycle)

Operator-authorized flash of the rev2 candidate (`0e3bfbde…`, `8b171654`)
on serial HW4MPK3161280211; single EDK2 write (offset 0x210000, 3,248,128
bytes), readback verified; transaction archived at
`~/k3-backups/pico-acpi-rhct13-1`.

Boot on the **gpioy kernel** (the qualified recovery kernel, GRUB default —
one variable: firmware):

- RHEL 10.3 to graphical target; EC bind (`cros_ec_espi PRP0001:03`); UFS
  attached (host0, `/dev/sda`); NVMe `1dee:5216` on seg0 — the boot device.
- **GPIO `_CRS` extent live**: `/proc/iomem` shows `d4019000-d40197ff`
  (0x800) claimed by the PRP0001 GPIO device.
- **Corrected thermal-trips live**: the decoded DSDT carries
  (70/90)(72/92)(72/92)(74/94)(75/95)(72/92)(72/92)(72/92) — the ch4
  hotspot at raw index 4, exactly the `8b171654` fix.
- **`_OSC` clean**: platform-wide `_OSC` ran (control 0x80 preserved), no
  AML errors in the boot log.
- dmicheck: 47 pass / 0 fail / 1 skip.
- Segs 2/4: roots present in ACPI (domains 0002/0004); endpoints not
  probed — **matches the rhct12-qualified gpioy behavior** (the
  qualification receipt itself gates endpoint probing on the ECAM quirk +
  RFKILL_GPIO kernel, i.e. the cycle-3 acpidebug build).

The thermal zone CONSUMPTION verdict (staggered zones, RW sysfs trips)
rides the cycle-3 kernel against this now-qualified firmware.

## Cycle-3 boot (2026-11-23, 04:45): panic eliminated, hang remains

One-time GRUB entry (grub2-reboot; gpioy default untouched) into
6.12.0-284.acpidebug.1.el10 (cycle-3 RPMs, sleeper EXIT=0 at 04:03).

**Verdict: v2's parse gate WORKED — no espi panic.** The boot passed 2.9s
(the cycle-2 panic point) and reached 2.73s of kernel time with:
- `spacemit-k3-espi PRP0001:02: error -EINVAL: failed to populate child
  devices` — the probe failed GRACEFULLY (cycle-2: NULL-deref panic)
- `spacemit-gpio PRP0001:0a: ACPI gpiochip: 128 pins (4 banks x 32)` —
  the GPIO v3 provider probed clean

**But the box hard-hung at 2.737s**, the console line
"Serial: 8250/16550 driver, 4 ports, IRQ sharin" frozen mid-word; no
network, no further output; recovery via Kauf-plug power cycle to gpioy
(unclean shutdown left a FAT dirty flag on the ESP — fsck advisable).

Root cause (rig-diagnosed): the espi probe's `devm_of_platform_populate`
returns -EINVAL on the ACPI-synthesized of_node; the failure path runs
`err_assert_resets`, resetting the ESPI controller out from under the
EC child binding mid-probe. **v3 staged** (`82acc5c`): the populate
error only fails the probe for non-ACPI boots; DSDT-declared children
enumerate via the ACPI bus. Rig .o disassembly-verified; patch applies
clean to the independent pristine base.

Not yet exercised on this boot (rode past the hang point): EC event
delivery, UFS, tsensor zones, rfkill, segs 2/4 endpoints. The rpmi-hsm
suspend denials in the log are the known, documented boundary items.

## Cycle-3d boot forensics (2026-11-23, ongoing)

The 3d kernel (espi v3 + XScale quirk + ECAM) freezes at the 8250 banner
(2.70-2.72s) under EVERY hypothesis eliminator tried:
- espi probe in both states (failed -22 / succeeded via v3)
- cpuidle.off=1, idle=poll (idle entry ruled out)
- maxcpus=0 (SMP ruled out)
- no console= (banner completes; freeze follows the probe anyway)
- 3d/3e XScale quirk: the reconstruction omitted `UPF_FIXED_TYPE`. EL10-284 re-enables hardware type detection in this case. [Binary comparison and corrective experiment](8250-console-review-2026-11-23.md)
- 8250.nr_uarts=0: **the boot SURVIVES past the freeze** — kernel runs,
  initrd finds root (after fixing two initrd defects: dracut built on
  gpioy omitted the nvme/ufs modules; an --add-drivers run pulled in an
  iscsi root fatal). The COM0 probe is the killer, mechanism unknown.

Second-order findings (board side, 2026-11-23):
- The acpidebug initramfs generated at install time ran dracut while
  GPIOY was booted: hostonly omitted nvme/nvme_core/ufshcd modules.
  Regenerated with --add-drivers (nvme nvme_core ufshcd_core
  ufshcd-pltfrm ufs-spacemit gpio_spacemit_k1) -o iscsi -o nfs.
- The RPMI system-reset path (SBI SRST via the ESOS backend) WEDGES
  with controller magic=0 version=0 after the second poweroff cycle —
  hard power cycle required to recover. (Firmware-side issue, separate
  from the kernel work; the rpmi reset backend's controller state
  handling needs the same treatment as the clock idempotence item.)

Next: instrumented serial8250_probe_acpi (3e build) to name the exact
faulting call; the earlycon carries the trace past the 8250 init.

## Matched-boot protocol (operator-directed, 2026-11-23)

Control (test 1) — existing 3e with `console=ttyS0,115200n8` (explicit
baud; the earlier boots' bare `console=ttyS0` made the name-based 8250
setup default to 9600 and reprogram the divisor mid-registration):
**the wedge is unchanged** — `K3DBG: before register_8250_port` then
`printk: l` (frozen mid-word, one character further than the 9600 boot).
Baud reprogramming is excluded as the cause.

Binary evidence (operator): the archived gpioy image sets the
fixed-type bit on the XScale match; the packaged 3e binary omits it.
The 284 serial core honors the supplied type only under
UPF_FIXED_TYPE and otherwise reinstates UPF_BOOT_AUTOCONF — so 3d/3e
never actually disabled hardware type detection. The generic 16550A
path can clear IER bit 6 (the K3 UART's transmit enable) during that
window, and OpenSBI polls the same physical UART for TX-ready without
a timeout — losing both ttyS0 and SBI output with IRQ and MMIO
correct. The 3e trace (validation OK, irq=11 clk=14745600; freeze
inside the registration interval before the return marker) is
consistent.

Test 2 — 3f (the one-line `UPF_FIXED_TYPE` addition, IRQ 11 and all
other inputs unchanged) is built on the sleeper; boot verdict looks
for `is a XScale`, the registration-return marker, and SSH/journal
confirmation of an independently identified boot.

## 3f boot: FIRST acpidebug userspace boot (2026-11-23 13:32)

The UPF_FIXED_TYPE fix (f86c099) + the coherent initramfs (both dracut
exclusion configs retired; the 43- file had a misspelled directive —
`omit_dracut_modules` vs RHEL's `omit_dracutmodules` — silently keeping
the iscsi hook while 42- dropped its drivers; every kernel-install
regeneration reproduced the fatal) delivered the first 6.12.0-284
acpidebug boot to a working SERIAL LOGIN ("is a XScale", registration
returned, console enabled).

Remaining items surfaced by the boot (all concrete, none mysterious):
1. **tsensor probe -EINVAL**: three of_property_* reads remain in the
   base probe path (sensor_range, tsensor_map, temperature_offset —
   lines 25/36/236) that fail on the ACPI-synthesized node. The ACPI
   zone builder is present; the probe path needs the unified property
   layer.
2. **EC chain dead below espi**: the v3 probe succeeds but EC0/PWM0
   (DSDT-nested PRP0001) never become platform devices — no cros_ec,
   no PWM, pwm-fan deferred forever.
3. **ECAM quirk not engaging**: "0002/0004 ECAM region not found" —
   the SPMT:K3 quirk entries supply ops but the root bridges need an
   ECAM region (MCFG entry or quirk cfgres); segs 2/4 stay dark and
   wifi/10G endpoints invisible.
4. **dwmac -ENXIO "IRQ macirq not found"**: the GMAC's _CRS interrupt
   not resolving under this kernel's ACPI resource path (worked on
   gpioy).
5. **ECAM ghost multiplication**: 8 NVMe copies on bus 0 (the known
   seg-0 decode interplay; needs the ghost-filter quirk carried).

## Thermal patch v2 on-hardware session (2026-11-23 14:0x)

The full ACPI conversion applied to the rig tree (all four pieces):
1. Three probe-path property reads → device_property_* (sensor_range,
   tsensor_map, temperature_offset)
2. func/bus clocks optional under ACPI (gated on !has_acpi_companion —
   the firmware's AcpiClockInitDxe owns them; the earlier working
   driver's form)
3. init_sensors() return checked (goto err_clocks with clock cleanup)
4. Teardown: ACPI-registered zones unregistered via
   thermal_zone_device_unregister (the devm OF helper mismatches the
   manually registered zones); clock/reset cleanup NULL-guarded
Plus #include <linux/acpi.h>.

Rig build: CLEAN (k3_tsensor.ko, 25544 bytes, "init_sensors failed:
%d" verified in the binary). The RPM's old module was rmmod'd and the
new one insmod'd successfully on the 3f boot.

**The manual device rebind (echo PRP0001:0d > .../k3_thermal/bind)
HUNG the console** — the probe passes the property reads (no -EINVAL)
but wedges later (suspect: init_sensors' TSEN mmio or the zone
registration under the rebind path). The RPM build's original probe
failed -EINVAL at 19.6s BEFORE any mmio, so the mmio sequence is
unproven on this kernel. No network on this boot (the dwmac macirq
issue) limited remote diagnosis; power-cycled to gpioy.

Next: the thermal module needs breadcrumb instrumentation in
init_sensors (like the 8250 K3DBG round) OR a boot with working
network for remote debugging. The ECAM/dwmac fixes remain the other
open items from the 3f boot.

## Thermal zone trip mapping: correct by design (2026-11-23)

The "second trip reads 80-85k vs the DSDT's 90-95k hot" observation is
the builder's intended layout, not a defect: the ACPI zone builder
registers THREE trips per channel —
  trip 0: passive (fan), the DSDT passive value, 8C hysteresis
  trip 1: MIDDLE passive ((passive+hot)/2) — ch4: (75+95)/2 = 85C ✓
  trip 2: HOT, the DSDT hot value
The observed trip_point_1 values (80-85k) are exactly the mid-points;
trip_point_2 carries the true hot thresholds. The 3f hardware readings
match the code to the digit. No driver change needed.

(gpioy's zones — ch0-only 65/75/85 — are the OLD hardcoded driver;
not comparable.)

## EC enumeration root cause: the 284 config omits the Chrome EC stack (2026-11-23)

gpioy (the working reference): cros_ec_espi binds PRP0001:03 directly
(ACPI scan creates the platform device; "Chrome EC device registered"
at 1.978s) and the cros-ec core creates the .auto MFD children
(dev/chardev/debugfs/gpio). The DSDT-nested-children concern was wrong:
ACPI enumeration DOES create PRP0001:03's device.

The 3f/284 RPM config has SENSORS_CROS_EC=y and SENSORS_PWM_FAN=y
(the consumers) but NO CHROME_PLATFORMS/CROS_EC/CROS_EC_ESPI/
CROS_EC_DEV/PWM_CROS_EC (the transport + PWM provider) — every
cros_ec* symbol absent. The chain is config-gated off, not broken.

Staged for the next build (3h): the transport symbols appended to
kernel-riscv64-rhel.config. Sources verified present in the 284 tree.
This rides AFTER 3g (ECAM) per one-variable-per-boot discipline.

## 3j boot (2026-11-23 20:4x): ECAM segs 2/4 LIVE; EC probes with a protocol error

The bus_shift fix works: segments 2 and 4 enumerate through the full
PCI walk (downstream busn_res updates visible at 2.3s; lspci shows
the X100 root complexes on 0002:). Two bounded items remain:

1. **Seg 2/4 root-bus ghosts**: 64 root-port (201f:0002) aliases —
   k3_ecam_map_bus returns the DBI for EVERY root-bus devfn. The
   Nov 18 filter (devfn==0 only on the root bus) must apply to the
   seg-2/4 own_map path; the fake bridges' bus claims block the
   downstream scan from reaching the real RTL8127/RTL8852BE.

2. **EC transport up, protocol failing**: cros_ec_espi binds
   PRP0001:03, reaches registration, then "cros_ec_prepare_tx
   failed: -22" and "couldn't register ec_dev (-74)". prepare_tx
   -EINVAL = the outgoing message exceeds the declared shmem
   mapping — the EC's max_request/response sizes (ec->din/dout)
   need the _DSD or a sane default the K3 EC actually uses.

Seg 0 remains perfect (one NVMe, ghost filter holding). Console,
network, thermal zones, UFS all working on this boot.

## 3l boot (2026-11-24 05:3x): the full-stack boot

The ec_dev->dev fix (a4be038) delivered the acceptance sequence:

- Chrome EC device registered at 2.09s (the 3k panic site)
- RTL8127 10GbE at 0002:01:00.0, r8169 BOUND, enP2p1s0 UP
- RTL8852BE 802.11ax at 0004:01:00.0, wlP4p1s0 present (DOWN —
  association is the qualification step)
- GMAC up with the IP on this kernel
- Console (XScale), NVMe, UFS, thermal zones all working

Remaining: pwm-fan deferred (probe order — the PWM provider probed
before the EC registered; the rebind path), the radio link tests
(wifi association, 10G traffic), and the rhct14 variable-write
test on this kernel.

## Wi-Fi radio disable: silicon-level diagnosis (2026-11-24)

The RTL8852BE hard-block chain, measured at every layer:

**Layer 1 — the driver stack works.** rtw89_8852be binds at
0004:01:00.0, loads rtw89/rtw8852b_fw-2.bin, creates phyN. The
rfkill-gpio PRP0001:00/01 probes fail -EBUSY (audit finding 9,
the GPS fallback double-claim) but this does NOT gate the radio.

**Layer 2 — the rtw89 rfkill mechanism (driver source):**
`rtw89_core_rfkill_init()` programs the chip's GPIO9 pinmux +
input mode; `rtw89_core_rfkill_get()` reads
`R_AX_GPIO_EXT_CTRL` (0x0060) bit `B_AX_GPIO_IN_9` (BIT(1) of
the byte at 0x0062), INVERTED: register set = enabled, clear =
disabled. The driver polls this and reports the rfkill hard
state.

**Layer 3 — the silicon measurement.** Via PCI BAR2
(0x12c0200000, 1 MiB) register-space mmap: GPIO_EXT_CTRL
reads 0x00000008 — **GPIO9 input = LOW = radio disabled at the
chip pin.** This is the hard-block source; the WLEN GPIO is
not it (Layer 4).

**Layer 4 — the board wiring.** The DSDT WLEN device
(\_SB.WLEN, _UID 0x80) declares GpioIo flat pin 35, active-high
shutdown. Measured via gpiod: pin 35 = inactive (LOW = enable).
A 4-second WLEN high pulse (gpioset -p 4 35=1) does NOT change
the chip's GPIO9 reading — **the chip's GPIO9 is not directly
wired to the WLEN line**, or the enable state is latched
inside the chip/EC and requires a re-initialization sequence
(driver rebind also does not clear it).

**Layer 5 — the power topology.** The vendor DT
(k3-pico-itx.dts): pcie4_rc = 1 lane, combophy 5, vpcie3v3 =
reg_aux_vcc3v3 (always-on fixed regulator). No radio-specific
power gate in the DT. The remaining candidate controllers for
GPIO9's state: the Chrome EC's radio domain (the EC firmware
holds the WLAN_ENABLE output; /dev/cros_ec exists but no
gpio-query debugfs is available on this kernel build), or the
chip requires its WLAN_EN power-on pulse sequence (the
Realtek reference design pulses PD_N/ WLAN_EN at power-on).

**Open:** query the EC's radio/wlan GPIO via a cros-ec command
(the chardev exists; ectool is not packaged for EL10) or the
ESOS-side EC firmware source (the EC image's gpio config for
the WLAN_ENABLE output).

## Fan always-blowing + the durable fix (2026-11-24)

The pwm-fan probe deliberately sets MAX_PWM (safety default)
and registers its cooling device via the OF-only
devm_thermal_of_cooling_device_register(dev, dev->of_node, …)
— under ACPI the of_node is the synthesized stub, the
registration fails, and NO governor ever lowers the duty. The
fan blew at 100% from boot.

Immediate relief: `echo 77 > …/hwmon*/pwm1` (the 30% floor =
DSDT FAN0 cooling-levels state 0). Durable fix:
k3-pwmfan-acpi-cooling.patch (Patch900011, commit 6825961) —
the ACPI path registers thermal_cooling_device_register
directly. REMAINING: the zone binding — the 6.12 thermal core
binds cdevs via the GOVERNOR's should_bind callback (not
thermal_zone_params, which lacks that member in this kernel);
the tsensor zones need a governor or trip-level wiring to
modulate the fan from the 30% floor through 60/80/100%.

## The power-rail audit: the ACPI boot's biggest gap (2026-11-24)

The EC firmware (RPMI voltage service) declares 22+ rails. The
AP-side DT (the DT-mode truth) marks 16 always-on/boot-on
(buck1-6, aldo1/2/4, dldo1-7), three GPIO-gated (pwr_x100/
a100/ext, default off), and ONE unconfigured: **aldo3** (500mV-
3.4V range, no state, no consumer — the only rail a driver
would enable at probe).

The ACPI boot handles NONE of them: the DSDT declares zero
voltage consumers, no RPMI voltage driver loads, and the rails'
state at AP boot is whatever the EC's own init left. Everything
that works, works on always-on luck.

The WiFi chain closes here: the chip enumerates (slot power
present) but its GPIO9 enable input reads LOW at the silicon —
aldo3 (RPMI regulator-dynamic8) is the prime suspect for the
chip's enable/VDD rail.

**The fix: AcpiPowerInitDxe** — the power twin of the existing
AcpiClockInitDxe (the proven pattern). At ReadyToBoot, send the
RPMI voltage-enable for the boot-required rails the EC leaves
off (aldo3 at the DT's range; verify pwr_ext) through the ESOS
voltage service. The EC owns the rails; the firmware sequences
them before the OS, same as the clock handoff.

**The broader missing ACPI functionality** (the port map):
thermal fan-zone governor binding (6.12 should_bind), rfkill
-EBUSY (finding 9), suspend/resume (the ESOS M2/CPPC cycle +
_LPI latencies), USB power sequencing, display (DSI/backlight).

## Wi-Fi enable: the toggle attempts + the path forward (2026-11-24, cont.)

The live aldo3 toggle via RPMI: three approaches attempted.

1. **Raw SBI MPXY** (module 1): SET_SHMEM + GET_CHANNEL_IDS
   work, but "mpxy channels: 0" — the response parsing needs
   the per-CPU shmem model the kernel's own mpxy-mbox driver
   uses; the global-page approach is insufficient.

2. **Kernel RPMI mbox API** (modules 2/3): the correct API
   (rpmi_mbox_init_send_with_response + rpmi_mbox_send_message,
   the clk-rpmi pattern), but mbox_request_channel requires a
   consumer device with the DT/ACPI mboxes spec. The RQTS
   device (which declares exactly that) exists only in the repo
   DSDT — it "rides the next firmware cycle" and was never
   flashed. A first-iteration ERR_PTR bug panicked the kernel
   (recovered; fixed).

3. **Board GPIO tests**: neither pin 35 (the pico DT's WLEN)
   nor pin 73 (the com260's working wifi line, which reads
   ACTIVE-high on this board too) changes the chip's GPIO9.
   The P1 PMIC's I2C expander (ri2c2 slave 0x41, 6 pre-burned
   pins, pwren on 1/2/3) is the remaining wire-level candidate,
   but the AP's i2c8 driver fails under ACPI ("failed to
   enable func clock" — another clock/power ACPI gap, same
   family as the rail topology).

**The com260 comparison**: the com260's wifi WORKS (its DT:
pin 73, ACTIVE_LOW). Same chip, same package. The pico's GPIO9
reads LOW with both candidate pins in enable state — the pico's
GPIO9 wiring goes elsewhere (the PMIC expander's pre-burned
pins 0/4/5, or a rail).

**The path forward (the next firmware cycle)**:
- Add the RQTS voltage-consumer device to the DSDT (the mboxes
  spec — the kernel-side RPMI client then binds and the rail
  state is directly controllable)
- OR implement AcpiPowerInitDxe (the ReadyToBoot rail enable —
  the same RPMI voltage SET_CONFIG from the firmware side,
  no OS dependency)
- Both belong to the rhct14+ cycle with the ESOS power work.

Also found: the i2c-k1 ACPI probe fails on its func clock
(the i2c8/PMIC path is dead under ACPI for the same clock
family reason — the AcpiClockInitDxe table needs the i2c
rows added).

## The rhct15 firmware cycle: AcpiPowerInitDxe + RQTS (2026-11-24, evening)

**The RQTS channel bug (found live)**: the RQTS device shipped
with `mboxes = <MPXY 8 0>` — channel 8 is the CLOCK service group
(RCLK's own channel). The rpmi-volt platform driver bound
PRP0001:07 correctly but the channel request failed -EBUSY
(someone — clk-rpmi — already owns it). The FW DT
(k3_fw_dt.dtsi) maps the service groups: clock = channel 8,
voltage = channel 7. Fixed: RQTS now declares `<MPXY 7 0>`.

**The rpmi-volt client (v5, on the board)**: platform driver
binding k3,rpmi-qual-test; verifies the channel's servicegroup
via RPMI_MBOX_ATTR_SERVICEGROUP_ID (expects 0x0007), then
GET_NUM_DOMAINS / GET_ATTRIBUTES (the domain name proves the id
mapping) / GET_CONFIG / SET_CONFIG(enable) / optional SET_LEVEL
/ read-back. Domain 8 = aldo3 (regulator-dynamic8 in the pico
rcpu DT). Module params: domain_id, set_enable, set_level_uv.

**The TWSI8 clock gap (closed in the same driver)**: the OS
i2c-k1 driver's "failed to enable func clock" under ACPI pointed
at the TWSI8 block being unclocked. The register is
APBC+0x20 — WRITE-ONLY (reads return zero; the ccu-k1.c quirk
comment). AcpiPowerInitDxe blind-writes 0x3 (func+bus gates,
mux 0 = pll1_d78_31p5) before the PMIC I2C transfer, the same
combined-gate form the kernel's quirk workaround uses.

**The P1 register math**: ALDO3_VOLT_REG 0x62 = 0x7b (3.3V:
500mV at VSEL 0x0b + 112 x 25mV), ALDO3_CTRL_REG 0x61 bit0
enable. Read-modify-write, idempotent.

**The aldo3 test on the rhct15 boot** (one variable): read the
chip's GPIO9 (R_AX_GPIO_EXT_CTRL 0x60 bit1 via PCI BAR2
0x12c0200000 mmap) — if HIGH, rebind rtw89 and test
association; if still LOW, the rail is excluded and the search
moves to the PMIC expander's pre-burned pins 0/4/5.

## rhct15 booted: the aldo3 test result + the GPIO9 mechanism (2026-11-24, night)

**The rhct15 flash**: verified (readback bound, NOR edk2 region =
bundle hash). Boot regression-green: EC, UFS, NVMe, thermal,
console. RQTS enumerated (PRP0001:07) on the corrected channel 7.

**aldo3 EXCLUDED**: the RPMI voltage path works end-to-end
(channel 7 = servicegroup 7; 24 domains; SET_CONFIG(1) +
SET_LEVEL(3.3V) on domain 13 = aldo3 — the EC accepted both,
RPMI_SUCCESS). GPIO9 unchanged (still low). The rail is not
the wifi-enable line. Domain map correction: the RPMI server
numbers ALL domains (fixed 0-5 + dynamic 6-23); aldo3 =
domain 13, not 8.

**The GPIO9 mechanism DECODED (from the rtw89 driver source)**:
GPIO9 = the chip's HARDWARE RFKILL INPUT (rtw8852b.c
rfkill_get = {R_AX_GPIO_EXT_CTRL, B_AX_GPIO_IN_9}, INVERTED).
The pin is programmed as input (func sel 0xf, MOD/IO_SEL 0) by
the driver's rfkill_init — CORRECTLY, verified by register
read. The board's wifi-enable line into GPIO9 is simply LOW:
nothing drives it on the pico. Pins 35/73 both excluded,
aldo3 excluded → the line is either unwired (NC/pulldown on
the pico vs driven on the com260) or driven by the PMIC
expander's pre-burned pins 0/4/5.

**THE UNBLOCK PROVEN**: driving GPIO9 as output-high from the
chip side (R_AX_GPIO_EXT_CTRL+1 bit1 OUT, +2 MOD, +3 IO_SEL)
flips GPIO_IN_9 to 1 → "rfkill hardware state changed to
enable" → rfkill hard-block CLEARED. The chip scans (probe
requests flow) — the radio TRANSMITS.

**Remaining on wifi**: the scan's pkt-offload h2c fails
("Update probe request failed" — rtw89_hw_scan_update_probe_req
→ rtw89_append_probe_req_ie path) with empty scan results.
Distinct from the enable question; suspects: the chip
initted with the pin low then transitioned (a cold boot with
GPIO9 high from the start may fully init), or a seg-4 DMA
path issue. NEXT TEST: drive GPIO9 high BEFORE the rtw89
probe (early boot), then scan.

**The RPMI sysfs client (v6)**: /sys/devices/platform/PRP0001:07/
{domain,enable,level,query} — the runtime rail-control
interface, with a proper remove() (v5 leaked the channel —
the missing .remove kept the mbox bound; fixed).
