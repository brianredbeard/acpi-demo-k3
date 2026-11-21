# Pushing back upstream: fwts defects vs our firmware

Audience: fwts maintainers (github.com/fwts/fwts, issues +
pull requests). Verified against upstream master (cloned this
session) — the RSDP/FACS/SPCR defects are in master; the
lpicheck is not upstream (board-local, from the RV BRS test
suite lineage — track separately).

Filing order = severity x breadth of harm. All four carry
repro evidence from a real RISC-V platform (this K3).

## 1. ACPI_010: rsdt_address rewritten for every non-ARM64 arch
   (unpassable RSDP check on RISC-V)

File: src/lib/src/fwts_acpi_tables.c:1187-1205 (master).

The re-host fixup does:

    if (fw->target_arch == FWTS_ARCH_ARM64) {
            xsdt_address = xsdt_fake_addr;          /* only XSDT */
    } else {
            rsdt_address = rsdt_fake_addr;          /* ALWAYS */
            xsdt_address = xsdt_fake_addr;
    }

For ARM64 the real rsdt_address is preserved, so
rsdp_brsi_test1 ("implemented XSDT, but not RSDT" — requires
rsdt_address == 0) can pass. For every other arch — including
RISCV64 — the loader stamps its own nonzero fake RSDT address
into the re-hosted RSDP first, then the BRS-I check reads that
same field and fails. Observed: "RSDP RSDT is 3220184867"
(0xBFF01F23 = fwts's internal allocation) against firmware
whose real RSDP has rsdt_address = 0 (verified: our DSC sets
PcdAcpiExposedTableVersions=0x20 — no 1.0B — and
AcpiTableProtocol.c skips the RSDT stamping on that path; the
kernel's dmesg shows XSDT-only).

The fix: extend the ARM64-style branch to RISCV64 (or gate on
"revision >= 2 && xsdt in use" rather than arch). One-line
semantic change; the check then reads what firmware actually
published.

## 2. ACPI_020: loader synthesizes a FACS, then BRS-I fails it

File: src/lib/src/fwts_acpi_tables.c:1038-1061 (master).

When no FACS exists (hardware-reduced ACPI — required on
RISC-V per BRS-I), the loader fabricates one with
hardware_signature 0xf000a200, ADDs it to the table set, and
back-fills fadt->x_firmware_ctrl with the fake address (lines
1052-1057). fadt_brsi_reduced_hw then finds facs != NULL and
fails "must not implement the ACPI FACS table."

Self-inflicted by construction: reduced-hardware systems
CANNOT pass. Fix options (either is fine):
  a) skip FACS synthesis when HW_REDUCED is set in the FADT
     flags, or
  b) in fadt_brsi_reduced_hw, ignore FACS entries whose
     provenance is FWTS_ACPI_TABLE_FROM_FIXUP.

Evidence: our live FADT (verified from sysfs) has
x_firmware_ctrl = 0 and HW_REDUCED set; fwts's own dump then
shows a FACS at its internal 0xBFF01ED3.

## 3. sbbr_gsiv: SPCR check has no RISC-V PLIC/APLIC case

File: src/acpi/spcr/spcr.c:69-80 (master).

The GSIV validation accepts only interrupt_type 0x08 (ARM
PL011) or 0x02 (IO-APIC) with gsi != 0. ACPI 6.5 defines
bit[4] (0x10) = RISC-V PLIC/APLIC for SPCR; a RISC-V
reduced-hardware platform using the specified encoding +
GSIV is failed as CRITICAL. Fix: accept 0x10 alongside
0x08/0x02. Evidence: our SPCR (0x10, GSIV 42) boots a working
console on SPCR alone (kernel log: "ACPI: SPCR: console:
uart,mmio32,0xd4017000,115200").

## 4. LPICpuidleNoLatency: reads exit_latency_us, kernel
   exposes "latency" (RHEL 6.12 name skew)

File: board-local lpicheck.c:459-483 (NOT in upstream master
— file under the RV BRS test-suite lineage; coordinate with
that project).

The check reads
/sys/devices/system/cpu/cpu*/cpuidle/state*/exit_latency_us;
this kernel (RHEL 6.12.0-284) names the attribute "latency"
(drivers/cpuidle/sysfs.c:319,
define_one_state_ro(latency, show_state_exit_latency)). The
values are present and correct (1/500/1100 us, matching _LPI).
Fix: try exit_latency_us, fall back to latency.

## Filing mechanics

- One issue per defect, upstream first (1-3); attach the
  minimal repro: table hexdump (sysfs files) + the failure
  line + the source line numbers.
- Offer the patches: 1-3 are each <10 lines and mechanical;
  a PR with all three after the issues are acknowledged is
  the fastest path (fwts historically takes drive-by fixes
  well when the repro is this clean).
- Our interest: these four account for 5 of the 12 unique
  failures on a conformant system; clearing them makes fwts
  output on RISC-V actually usable as a gate, which is the
  point of running it.

## What we are NOT filing

- RHCTProfileMissingExtensions: our silicon genuinely lacks
  the RVA23U64 extensions; correct failure.
- Method_LPIBadSubElementType / HardwareIDNotUnique: OUR
  bugs, fixed in rhct2 (staged).
- MethodNotExist (_STA): policy choice (PCC power model
  deliberately unwired), documented.
