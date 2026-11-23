# fwts broad-run triage — the 17 failures classified (2026-11-23)

## November 23 Pico run with EFI runtime tests

FWTS 26.09 ran through `/dev/efi_test` on kernel
`6.12.0-284.acpidebug.1.el10.riscv64`, boot ID
`c1f0ac46-50c1-4ec6-8ed7-5ecfbc1bfa88`. The board report is
`/var/tmp/fwts-pico.3la5cSZ6/results.log`, SHA-256
`e257a7d38a8bcf00a31fe8584360e0ee579b5ad12be61b8a3c804cd7798f7f40`.
It records 420 passes, 29 failures, 11 aborts, 6 warnings and 519 skips.
The earlier 17-failure assessment below describes a different run.

| Runtime finding | What the test and platform source establish |
|---|---|
| Six `SetVariable` failures | Ordinary private-GUID scratch-variable creation with NV, boot-service and runtime attributes fails. Several tests stop at this prerequisite. Five print `EFI_INVALID_PARAMETER`. Test 8 omits the status. The firmware reports 83,328 bytes free, enumerates 48 names and passes 1,024 storage queries. Authenticated creation also fails and leaves the dependent checks untested. |
| Two `GetNextHighMonotonicCount` failures | Both calls supply an output pointer. The EDK2 counter driver increments its cached high word, writes it through `EfiSetVariable` and returns the write status. UEFI reserves `EFI_INVALID_PARAMETER` here for a null output pointer. [UEFI runtime services](https://uefi.org/specs/UEFI/2.11/08_Services_Runtime_Services.html) |
| Two `SetTime` failures | Test 4 attempts a valid date. In test 5, rejecting 1899 passes, then restoring the original valid time returns `EFI_DEVICE_ERROR`. Pico selects `VirtualRealTimeClockLib`, which writes timezone, daylight and epoch variables. The runtime wrapper also updates cached settings before the writes succeed and maps failure of its final `TimeSettings` write to `EFI_DEVICE_ERROR`. |

### Scratch-variable persistence test on rhct13

Pico `HW4MPK3161280211` matched the live DSDT SHA-256
`915e8d9d86dbd9031b50c466b26f886dfdf3ccd5a94dc4ec08a470e8a9688367`.
The EDK2 FIT extracted from the archived post-flash NOR readback matched
`13024d1360c915fb73bce809de750dfee82f8b866eba116e73bd6771e1e3bda4`,
platform revision `8b17165463eff040bb8f486be0b08416daff9f2b`.
The kernel image SHA-256 was `64209503d9887590dacc0dc494b577d8f3943894c8c8f4710e96dec27dd1f0a6`
and initramfs SHA-256 was `d2faf7da73ea1849225b2dfe3e5b7c0781f0750aa2d5a08b3aa64da4300505eb`.

Both names used private GUID `9d3f3c17-3d26-4f0e-b69e-7bbf9ccf69db`,
attributes 7 (NV, BS, RT), and four data bytes. Linux results below are raw
EFI statuses returned through the original FWTS run's `efi_test.ko`.

| Operation | Observation |
|---|---|
| Linux create on the original FWTS boot | `GetVariable(K3AuditRuntime23)` returned `EFI_NOT_FOUND`. Creating it with `RT23` returned `EFI_INVALID_PARAMETER` (0x8000000000000002). Readback returned `EFI_NOT_FOUND` again. |
| EFI Shell create | `K3AuditPreboot23` was absent. Creation succeeded. `dmpstore` showed NV+RT+BS and `50 52 45 31` (`PRE1`). |
| Linux update on boot `48df606c-3ea9-4a0d-bb82-c262f81d61f8` | Linux read attributes 7 and `PRE1`. Writing `UP23` returned `EFI_INVALID_PARAMETER`. An immediate read still returned `PRE1`. |
| Persistence and cleanup | After reset, EFI Shell read `PRE1` from the same name. Deletion in EFI Shell succeeded and a second lookup found it absent. On restored RHEL boot `3ee4d787-a65a-4e32-99f4-350f35ff07ea`, efivarfs listed neither scratch name. SSH was up, root was `/dev/nvme0n1p2`, and `BootCurrent` was the original redhat entry 0007. |

The firmware callback assumes a near-identity runtime map. On both Linux
test boots, `/sys/kernel/debug/efi_page_tables` showed flash physical
`0xb8000000` mapped at virtual `0x20200000` for 13 MiB. The variable FV
starts 7 MiB into that aperture, at physical `0xb8700000` and virtual
`0x20900000`. In the locked SDK, `VariableClassAddressChangeEvent`
converts the NV variable base. The platform's `FvbGetPhysicalAddress`
returns its saved physical region base. In `UpdateVariableStore`, a
write in the mapped variable store therefore satisfies
`CurrWritePtr < LinearOffset`, which returns `EFI_INVALID_PARAMETER`
before `Fvb->Write`. The measured map and the source establish an address
mismatch. The test observed the external status, without an internal
firmware trace identifying the first returning instruction.

The fix needs consistent address units in the variable-to-FVB calculation
and valid runtime pointers for subsequent FVB, SPI NOR and controller calls.
Keep flash-relative offsets distinct from mapped MMIO addresses. Re-run this
create/update/read/reset/delete sequence under the observed nonidentity map,
then re-run the failing counter and time suites. The earlier handoff hang
remains a regression check. [FVB bisect](fvb-va-bisect-2026-11-22.md) · [Runtime test contract](audit-2026-11-20/uefi-runtime.md)

### Other findings

The other 19 failures break down as follows.

- Two PCI namespace reports identify segments 2 and 4 on this boot.
- Eight LPI reports share one FWTS range check. `0x11000000` is in the
  platform-specific retentive range. [SBI HSM suspend types](https://docs.riscv.org/reference/sbi/ext-hsm.html)
- Three SMBIOS findings depend on whether the board provides an IPMI v1.0
  host interface, a Redfish host interface or a TPM, respectively.
  [BRS-I SMBIOS requirements](https://docs.riscv.org/reference/brs/smbios.html)
- Three wakealarm failures occur when enabling alarm interrupts on
  `/dev/rtc0`. The kernel records three `rtc-efi` status-3 messages, and
  the selected virtual RTC library returns `EFI_UNSUPPORTED` for wakeup.
- Both RHCT failures identify extensions absent from the advertised string.
  Check the intended profile and silicon support before changing the table.
- The one `_STA` report comes from FWTS's mandatory SBBR-mode namespace
  check. The report identifies no particular AML device.

The 11 aborts cover seven CPU-frequency tests, three TPM event-log tests
and one ESRT test. Their hardware interfaces were unavailable to this run.

## Earlier v12-era run

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
