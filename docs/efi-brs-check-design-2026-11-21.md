# EFI BRS check application — design (from the fwts failure inventory)

## Purpose

A boot-time self-test that validates OUR firmware's BRS-I/SBBR
conformance before the OS boots — the checks fwts performs on
a running system, run at the source (EDK2 DXE driver at
ReadyToBoot). Catches regressions at flash time instead of
post-boot test time.

## The failure inventory it must encode (from rhct2 boot, fwts V26.09)

### SMBIOS class (all OURS — the vendor's SmbiosMiscDxe + PCDs)

CHECK: version >= 3.7.0 (BRS-I minimum; we emit 3.6.0 — need
  the SMBIOS 3.7 structures: Type 44/45 fields; the SmbiosDxe
  version PCD + structure definitions)
CHECK: required structures present:
  MANDATORY: Type 4 (Processor, per hart), 7 (Cache, mirror
  the PPTT topology: L1I/L1D per core + L2 per cluster), 16
  (Physical Memory Array), 17 (Memory Device), 19 (Array
  Mapped Address), 44 (Processor Additional Info), 32 (have),
  0/1/3 (have)
  CONDITIONAL (skip-with-note when hardware absent — matches
  the fwts advice strings): 38 IPMI, 42 Redfish, 43 TPM —
  fwts marks them mandatory and fails; OUR check must encode
  the honest rule (present -> must have structure; absent ->
  note, no fail) and the fwts delta gets filed upstream
CHECK: Type 3 Chassis Type byte in 0x01..0x24 (LIVE BUG: ships
  0x00 — PcdSmbiosClassisType .dec default 0, never set in our
  DSC; the data file's 0x11 intent is overridden. Fix: DSC
  sets 0x11)
CHECK: no "Not Specified"/"Unknown" strings in the fields
  fwts flags: Type 1 Version; Type 2 Serial/AssetTag/
  LocationInChassis; Type 3 Manufacturer/Version/Serial/
  AssetTag (LIVE: several empty; the TLV override path works —
  the chassis serial was TLV'd — but the PCD fallbacks must
  carry real values for TLV-less units)

### ACPI class (checked, waivered, or fixed already)

CHECK: RHCT ISA string canonical order (the zvksg/zvksh class
  of bug — algorithm portable from fwts_riscv_isa.c; catches
  any future extension addition that lands out of order)
CHECK: _LPI state packages: 10 elements, [0-5] integers,
  [6] entry-method GAS, [7][8] NULL-or-real GAS buffers, [9]
  name string (the rhct2 fix class)
CHECK: PRP0001 (HID,UID) uniqueness namespace-wide (the rhct2
  fix class)
NOTE (not failures — record-only): FACS absence under
  HW_REDUCED, XSDT-only RSDP, SPCR 0x10+GSIV — the things
  fwts gets WRONG on RISC-V; the EFI check logs them as
  expected-correct so a future fwts run can be diffed against
  the firmware's own ground truth

### Runtime class (kernel-side, out of EFI scope — documented
  for completeness)

LPISBITypeInvalid (fwts stale on RPMI idle encodings),
LPICpuidleNoLatency (sysfs attr name skew), WakeAlarm
(rtc-efi no alarm IRQ), RHCTProfileMissingExtensions (silicon
fact), MethodNotExist _STA (PCC power model deliberately
unwired).

## Shape

K3BrsCheckDxe (Silicon/Spacemit/K3/Drivers/): DXE_DRIVER,
  ReadyToBoot callback (gEfiEventReadyToBootGuid), reads the
  INSTALLED tables via the SMBIOS + ACPI SDT protocols (not
  the source data — the check runs against what actually
  shipped), emits DEBUG((DEBUG_ERROR, "K3BRSCHECK: ...")) for
  each failure + a one-line summary. Failures are LOUD but
  non-fatal (boot proceeds; the check is a gate for US, not
  the board).
  Host-testable: the check logic is pure functions over table
  buffers (the same shape as the fwts checks) with a unit
  harness in tests/ like the P1 ownership model.

## Sequencing

1. Fix the live SMBIOS bugs first (version 3.7, Type4/7/16/
   17/19/44 producers, chassis type PCD, string PCDs) —
   the check app validates the FIXED state
2. Then the check driver + host tests
3. Then one flash cycle: fix + check together (the check's
   first live run IS the qualification)

## SMBIOS fixes IMPLEMENTED (rhct3, inspect-gated)

edk2-platforms 294228c0: version 3.7.0 (PcdSmbiosVersion),
Type 4 per hart, Type 7 (PPTT cache topology: 8xL1I 8xL1D
64KB + 2xL2 4MB), Type 16/17/19 (16GB LPDDR, extended size
fields), Type 44 per Type4 with the RISC-V PSB + ISA string,
chassis type 0x11 (the .dec-default-0 bug), full string PCD
fallbacks. Built clean; markers verified in the FD.

Bundle /tmp/pico-acpi-rhct3: single variable (edk2 payload)
on rhct2-qualified base, inspect-gate PASSED.

Acceptance: fresh fwts dmicheck — BrsiSmbiosVersion,
SbbrSmbiosNoStruct (4/7/16/17/19), DMIValueOutOfRange,
DMISerialNumber all GONE; BrsiSmbiosNoStruct reduced to the
three absent-hardware items (IPMI/Redfish/TPM, waived).

## rhct3 hardware acceptance + rhct4 (Type17 corrections)

rhct3 verified live: SMBIOS 3.7.0, 8x Type4 + 18x Type7 +
Types 16/17/19 + 8x Type44, chassis 0x11, all identity
strings populated (TLV serial through Types 1/2/3; PCD
fallbacks elsewhere). Two data bugs caught by the acceptance:
MemoryType 0x1E (read LPDDR4; LPDDR5 = 0x23) and ExtendedSize
bit31 (read 16 TiB; clear = KB = 16 GiB) + speed 5500->6400
per the SoC datasheet. rhct4 staged with the corrections,
inspect-gated.

Identity-field policy: TLV EEPROM is the per-unit source
(serial# plumbed through all three types by
SmbiosTlvOverrideDxe); PCD fallbacks carry deterministic
build constants; arbitrary values only where no TLV source
exists — never for hardware-truth fields (type/size/speed),
which are corrected against the datasheet.

## rhct4 acceptance + rhct5 (units fix) + the fastboot tool

rhct4 verified live: LPDDR5 (0x23), 6400 MT/s, SMBIOS 3.7.0,
all structures, regression green (17 clocks, 3 LPI, UFS).
One residual: Size read 16 TiB — the ExtendedSize units are
FIXED MB per spec 3.2 (bit31 is reserved-0, not a unit
selector); my KB-unit assumption was wrong. Verified against
the dmidecode 3.6 reader source. rhct5 = 16384 MB, staged +
inspect-gated.

Also landed (dd5b8ff): k3-enter-fastboot — the vendor's
no-button path (ESOS sysreset LISTEN_ADDR 0xc087c000 /
FLAG_FASTBOOT 0x1 -> PMIC nonvolatile flag -> BootROM USB).
/dev/mem is STRICT_DEMEM-blocked, so the write goes through a
one-shot kernel module (k3fb.ko, built against dbg1, deployed
to /usr/local/lib on the board; wrapper at
/usr/local/bin/k3-enter-fastboot). Source packaged in
tools/k3-fastboot/.

## rhct5 acceptance -> rhct6 (the four findings + the Type44 lesson)

rhct5 verified: 16 GiB (MB-units fix) ✓. The fresh dmicheck
then exposed four real bugs — and one spec lesson:
- Type4 length 0x33 -> 0x32 (sizeof included 3.8 fields)
- Type16 MaximumCapacity 0xFFFFFFFF -> 0x80000000 (the
  required marker with extended capacity)
- Type17 MemoryTechnology 0 -> 0x03 DRAM
- Type44: my ISA-string PSB was an invented layout (and the
  263-char string overflowed the PSB length byte). The
  ratified riscv/riscv-smbios v0.10 PSB is a fixed 110-byte
  CSR body: mhartid/boot-hart/mvendorid(0x710)/marchid(X100)/
  mimpid/misa/privileges/delegations/XLENs. Rewritten with
  the live CSR values; the ISA string's home is the RHCT.

rhct6 staged, inspect-gated. The lesson recorded: when a
structure's layout isn't in the SMBIOS spec proper, find the
arch spec FIRST — the riscv-smbios repo was one search away
the whole time.

## rhct7 QUALIFIED: the SMBIOS/DMI class is CLOSED

Fresh dmicheck on rhct7: ZERO failures (the absent-hardware
IPMI/Redfish/TPM items appear only under the BRS-I flag set,
which this invocation does not force; under the user's full
suite they remain as the documented waiver). Type4 strings
render (CPU0/SpacemiT/X100); regression green (17 clocks,
UFS true sys1clk).

The SMBIOS arc rhct1->rhct7: 3.6/7-structures/chassis-0x00 ->
3.7.0 / Type 4x8 + 7x18 + 16/17/19 + 44x8 (ratified RISC-V
v0.10 PSB with live CSR values) / chassis 0x11 / TLV+PCD
identity / datasheet-true memory (LPDDR5 16GiB 6400) / all
lengths, markers, and string areas conformant. Seven cycles,
one variable each, every acceptance caught the next real bug.
