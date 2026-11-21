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
