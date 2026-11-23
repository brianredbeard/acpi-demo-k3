# fwts broad-run triage — the 17 failures classified (2026-11-23)

Source: /root/fwts_results.log on the board (the v12-era broad
run; the quick `fwts dmicheck` 47/0 is the SMBIOS-only subset).
The audit's summary: 3 BRS-I SMBIOS, 8 SBI_CRET, 3 RTC
wakealarm, 2 RHCT ISA-profile, 1 missing _STA. This log carries
the LPI/RHCT classes; the SMBIOS/RTC/_STA items came from the
serial-run capture of the same session.

## Classification

### SPEC-GAP: fwts does not know RISC-V SBI suspend types (8)

`LPISBITypeInvalid` on every CPU's SBI_CRET state: the LPI's
suspend type 0x11000000 "is not 0, 1, or >= 0x80000000".

0x11000000 = SBI_SUSP_BASE + SBI_EXT_0_1_SUSP_SYSTEM_SUSPEND
(the SBI v0.1 system-suspend hint encoded in the standard
SBI suspend-type format: type = 0x10000000 + index 0x11).
fwts's validator knows only the LPI ACPI-spec values (0/1/
platform >= 0x80000000); the RISC-V FFH _LPI encoding maps
SBI suspend types into this field. This is the audit's exact
note: "SBI places 0x11000000 in the platform-specific
retentive range" — misclassified by the TESTER, correct
per the RISC-V FFH spec (the LPI FFH overlay).

VERDICT: tester limitation (fwts needs RISC-V FFH awareness).
No firmware change. Upstream-able fwts fix.

### SPEC-GAP: the RHCT ISA-string order check vs the kernel UABI
### canonical order (2)

`RHCTISABadOrder`: our ISA string lists extensions "out of
canonical order" per fwts's (riscv,isa DT) ordering; the
kernel's RHCT parsing expects the ISA-string ordering from
the RVA23 profile spec. Our string IS kernel-verified (the
CPU driver probes and cpuidle works); fwts's order rule is
the DT device-tree ordering, not the RHCT UABI ordering.

`RHCTProfileMissingExtensions`: RVA23 profile requires
extensions our string lists differently (e.g. zvfh vs
zvfhmin grouping). Same root: fwts applies DT-profile rules
to an RHCT string.

VERDICT: tester-vs-spec ambiguity (fwts's rule is DT-derived;
our string is kernel-consumed and working). Candidate: align
the string to fwts's expectation IF that also satisfies the
kernel — needs a one-line reorder test in ACPICA. LOW
priority; the kernel is the consumer that matters.

### FIRMWARE: cpuidle latency not exposed (1 class, 8 CPUs)

`LPICpuidleNoLatency`: "3 cpuidle state(s) expose no
latency" — our _LPI states lack the latency/residency
fields the LPI spec provides (or they're zero). The states
WORK (LPI-0/1/2 in cpuidle) but the governor gets no
latency data = suboptimal state selection.

VERDICT: real firmware gap (minor, functional). Fix: add
_latencies/_residencies to the _LPI packages (measured
values from SBI HSM or conservative defaults). Rides the
next DSDT cycle.

### From the serial capture (audit's other items)

- 3 BRS-I SMBIOS: the dmicheck-era structure issues
  (the 47/0 dmicheck run PASSED these later — likely fixed
  by the rhct7-era SMBIOS rework, or the count was from the
  pre-fix run). VERIFY on next fwts broad run.
- 3 RTC wakealarm: the RTC wakealarm test — the board's
  RTC is EC-backed via cros-ec; the wakealarm path may need
  the EC RTC driver. Deferred: wake paths are the open
  suspend-resume item anyway.
- 1 missing _STA: a device without _STA — legal ACPI
  (missing _STA = present+enabled) but fwts warns. Identify
  the device on the next run.

## Disposition

- 8 SBI_CRET: tester gap — no action (fwts upstream candidate)
- 2 RHCT order: tester/spec ambiguity — verify kernel-first,
  then optionally align
- 8-CPU latency: real minor gap — _LPI latencies next DSDT cycle
- SMBIOS/RTC/_STA: re-verify on the next broad run post-
  cycle-3 boot
