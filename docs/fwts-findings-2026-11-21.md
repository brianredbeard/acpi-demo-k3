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
