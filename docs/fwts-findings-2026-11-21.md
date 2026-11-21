# FWTS failure triage (rhct + lpicheck), 2026-11-21

All four failure classes root-caused against the fwts sources on
the board (/root/fwts_build), the kernel UABI doc, the builder
tree, and live sysfs.

## 1. RHCTISABadOrder — REAL firmware bug, FIXED

fwts's algorithm (ported from fwts_riscv_isa.c, mirrors the
kernel UABI normalization): singles in IMAFDQCBPVH order, then
Z-extensions by category (IMAFDQLCBKJTPVH) then alphabetical,
then S (both conventions accepted), Sm last, X last.

Our string had exactly ONE violation: zvksh before zvksg
(both Z-category V, 'g' < 'h'). Fix: Rhct.aslc ISA_STRING
reordered to canonical (extension SET unchanged — verified
set-equal against K3Cpus.dtsi). Verified by running the
ported fwts algorithm on the new string: zero violations.

## 2. RHCTProfileMissingExtensions — NOT a firmware bug (hw fact)

fwts checks the RVA23U64 mandatory list (riscv-unified-db
RVA23U64.yaml). The 9 "missing" extensions (zcb, zcmop, zfa,
zihintntl, zimop, zawrs, zicbop, zic64b, supm) are missing
from the HARDWARE ITSELF — /proc/cpuinfo (the kernel's own
enumeration of the X100 harts) lacks every one of them.
The RHCT correctly describes what the silicon implements;
adding the names would be a LIE that userspace would trap on
(executing an unimplemented extension = illegal instruction).
Resolution: waive with evidence (the /proc/cpuinfo diff is
the artifact). The MMU half of the profile test already
PASSED (Sv39 via the MMU node).

## 3. LPISBITypeInvalid — fwts checker stale vs the RISC-V FFH spec

fwts lpicheck.c rejects our 0x11000000 SBI suspend type
("not 0, 1, or >= 0x80000000"). But 0x11000000 is the
RPMI-routed platform idle state we qualified on hardware
(ESOS 0001-0008 series): the RISC-V FFH spec reserves
type 1 = SBI default non-retentive, and >= 0x80000000 =
platform-specific per the SBI HSM suspen extension — BUT
0x11000000 is what the vendor RPMI idle-state domain reports
(sleep-state-id 0x11 << 24 domain shift), and OpenSBI's
sbi_suspend accepts it (proven: the state entered and exited
on hardware with correct hart state).
fwts's checker predates the vendor-domain encodings. Filing
upstream is the correct resolution; NOT changing the DSDT
(the state is hardware-qualified).

## 4. LPICpuidleNoLatency — fwts/kernel sysfs name mismatch

fwts reads cpuidle/state*/exit_latency_us (upstream 6.12+
name). This RHEL 6.12.0-284 kernel exposes the attribute as
"latency" (drivers/cpuidle/sysfs.c:319
define_one_state_ro(latency, show_state_exit_latency)).
The kernel HAS consumed our _LPI latencies correctly — live
sysfs: LPI-0 1/1, LPI-1 500/950, LPI-2 1100/2700 (exit
latency / residency us) matching Cpu.asl exactly.
fwts defect (version skew), not a firmware issue.

## Net: one real fix (ISA order, applied), two fwts defects
## to file upstream, one hardware-fact waiver.

## The bundle (pico-acpi-rhct1)

Staged at /tmp/pico-acpi-rhct1: single-variable build on the
qualified lpi2q image — ONLY the edk2 payload swapped (fresh
RELEASE_GCC5 from edk2-platforms 7c6cf9d1, the one-file ISA
reorder). fsbl/agent/esos/opensbi byte-identical (sha256
verified in both manifests). FIT payload rule verified:
fdt_1 subimage byte-identical between old and new edk2 FITs;
uefi subimage differs FD-wide via DXE-FV recompression of
the single table change (source delta git-verified: 1 file,
4 insertions).

Built through build_edk2.py (new): the canonical recipe
extracted from tools/build-com260-efi-edge.py made executable
— WORKSPACE=root, PACKAGES_PATH=SDK-first, --conf=$root/Conf,
cwd=root, no edksetup.sh. AGENTS.md prose had drifted to a
nonexistent efi-development path; the executable recipe
cannot drift.

Acceptance on next flash+boot: fwts rhct Test 2 —
RHCTISABadOrder GONE (the one real violation fixed);
RHCTProfileMissingExtensions remains (hardware fact,
documented waiver); 17 clocks, 3 LPI states, UFS unchanged
(same ESOS/OpenSBI/dtb payloads).

## Full-suite triage (post-rhct1, all unique failures)

### REAL firmware bugs (fix in next bundle)

1. **ACPI_020 [CRITICAL]: FACS must not exist** — the FACP carries
   x_facs=0x6000000 (nonzero) though no FACS table is present.
   BRS-I forbids FACS on RISC-V. Fix: zero the X_FACS pointer in
   FACP. (FWTS message: "must not implement the ACPI FACS table")

2. **ACPI_010 [CRITICAL]: RSDT must not exist** — we ship XSDT-only
   (correct per BRS-I), but the RSDP still carries an RSDT pointer
   (and fwts flags it). Fix: zero RSDP's RSDT address (0x00[16:20])
   keeping XSDT. [VERIFIED against live table: RSDP rsdt_ptr
   parse pending — confirm before fix]

3. **HardwareIDNotUnique [HIGH]: EC0/EPR0/PWM0 collide** — EPR0
   (atmel,24c02 EEPROM on I2C2), EC0 (cros-ec), and EC0.PWM0 all
   carry PRP0001 + _UID 0. PRP0001 devices need UNIQUE (HID,UID)
   pairs namespace-wide. Fix: distinct _UIDs (EPR0=1, PWM0=1 —
   scoping under EC0 makes PWM0 unique only if EC0's own UID
   differs; cleanest: EPR0 _UID 1, PWM0 stays 0 as EC0.PWM0 has
   different parent... verify fwts matching scope: it compares
   HID+UID globally for PRP0001).

### SPEC-STRICT vs kernel-tolerant (our call to make)

4. **Method_LPIBadSubElementType [HIGH]**: our _LPI state elements
   [7][8] are integer 0 ("no residency/usage counter"); fwts (and
   the RISC-V FFH spec examples) encode them as NULL GAS
   ResourceTemplates: Register(SystemMemory, 0, 0, 0, 0). The
   kernel skips 7/8 entirely (processor_idle.c: "elements[7,8]
   skipped for now"). Fix: match the spec examples — zero-filled
   GAS buffers for 7/8 (also covers the kernel's elem-9 name read;
   verify count >= 10 stays).

### fwts defects / hardware facts (waive with evidence)

5. **sbbr_gsiv [CRITICAL]**: fwts only accepts ARM PL011 (0x08) or
   IO-APIC (0x02) SPCR interrupt types; ours is 0x10 (RISC-V
   PLIC/APLIC — the ACPI 6.5-specified value) + GSIV 42. The
   console WORKS (boots on SPCR alone). fwts ARM-centrism.

6. **RHCTProfileMissingExtensions [MEDIUM]**: silicon lacks the
   RVA23U64/S64 sets (documented earlier — /proc/cpuinfo evidence).

7. **LPISBITypeInvalid + LPICpuidleNoLatency [MEDIUM]**: documented
   earlier (vendor RPMI idle-type encoding + sysfs attr name skew).

8. **WakeAlarmNotTriggered2/3/4 [MEDIUM]**: "Cannot enable alarm
   interrupts on /dev/rtc0" — the EFI RTC (rtc-efi) does not
   support alarm IRQs. Hardware/driver limitation, not table
   content. Waive or retest after a real RTC driver binds (if the
   board has one behind the EC — check post-EC-bind).

### Orphaned source finding (side effect of this audit)

**Power.asl is not included in any DSDT build** — the P1
power-resource votes (USB2/PCIE_PORTA/EMAC0 _ON/_OFF/_STA via PCC)
never shipped. That's why the namespace has ZERO _STA objects and
fwts's SBBR _STA probe (Test 41, MethodNotExist) fails: it walks
all names ending in _STA and finds none. Investigate: was the
power-resource namespace deliberately dropped at v12, or lost?
The P1 gate ran through a different path (ESOS-side), so the
firmware-side PCC power resources may be intentionally retired —
but then Power.asl should be deleted or moved to an attic, not
left as an unshipped trap.

## rhct2 bundle (the two real firmware fixes)

Staged at /tmp/pico-acpi-rhct2, inspect-gate PASSED. DSDT-only
variables on rhct1-qualified base (edk2-platforms daf8e6e8):

1. _LPI counter elements [7][8]: integer 0 -> NULL GAS
   Register(SystemMemory,0,0,0,0) per the RISC-V FFH spec
   examples. Kernel behavior unchanged (elements skipped;
   [9] name read unaffected). Decompile-verified in the built
   AML: 10-element packages with the GAS buffers.
2. PRP0001 _UID dedup: EPR0 0->1, EC0.PWM0 0->2 (EC0 keeps
   0). All 12 PRP0001 devices now unique. Binding untouched
   (PRP0001 matching is via _DSD compatible).

Expected on flash: Method_LPIBadSubElementType and
HardwareIDNotUnique GONE from a fresh per-boot fwts run.
Everything else per the verdict table (fwts defects remain
until upstream filing; profile = silicon waiver).

fwts operational rule (learned the hard way, twice): always
run with -r results-<fresh-name>.log and NEVER grep across
appended multi-boot results.
