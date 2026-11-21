# Executed validation and continuous qualification

All commands below run from the integration repository root. Hardware procedures are in `regression.csv`; none were executed in this audit. Tools operate on copied tables or reconstructed source, not live controller registers.

## Executed host results

| Command / check | Actual result | Evidence / limit |
|---|---|---|
| `python3 meta.py validate` | PASS | `evidence/manifest-validation.log`; local hashes only, not completeness of release inputs |
| `python3 -m unittest discover -s tests` | PASS, 17 tests | `evidence/repository-tests.log`; orchestration/service host tests, not board qualification |
| `reproduce.py` with existing local platforms Git objects | PASS | Pinned baseline plus all12 patches applies. Independent fresh reconstruction compared by DTB/AML bytes; `evidence/reproduction-test.log` and `reproduction-commands.json` |
| `cpp` + `dtc` on five DT inputs | PASS with warnings retained | Two OS board DTs and three internal firmware DTs; source warnings in logs, not waived correctness |
| `iasl -tc` on both expanded DSDTs | PASS: zero errors/warnings | Locked4229-byte AML; maintained5223-byte AML. `evidence/iasl*.log`. Include expansion sets OEM revision1 and default CPPC disabled; no other build variant qualified |
| `acpiexec` `_OSC` supported capability | PASS in both snapshots | `aml-results.json`; valid two-DWORD buffer, support0x80 |
| `acpiexec` unknown UUID | FAIL in both | Capability DWORD zeroed; expected preservation |
| `acpiexec` capability masking | FAIL in both | Valid support0x180 becomes0x80 without status0x10 |
| `acpiexec` malformed four-byte buffer | NOT APPLICABLE to valid ABI; robustness observation | Raises AE_AML_BUFFER_LIMIT; `*osc-short.log` |
| `audit_static.py` | Extraction completed; semantic checks BLOCKED | 1418 nodes across5 DTs, every raw property preserved,27 reverse locked ACPI devices. Address equality candidates, not migration PASS |
| `dependencies.py` | Extraction completed |1098 known phandle/interrupt edges across5 inputs, no unresolved provider handles in supported property kinds. Does not prove provider implementation or physical wiring |
| `fixed_tables.py` | PASS for implemented structural assertions |6 rebuilt table payloads; RINTC/IMSIC/APLIC/MCFG and selected RHCT/PPTT checks; three malformed MADT mutations rejected |
| Audit-tool unit tests | PASS,7 tests | Malformed checksum/truncated table/zero-length MADT rejection; resource nesting and DT retention; `evidence/audit-tests.log` |
| Clock generator | PASS for deterministic extraction |404 rows; all13 RPMI IDs;178 declared CCU nodes. Candidate parents, not live mux selections |
| Runtime/hardware | NOT TESTED / BLOCKED | No new boot, register readback, IRQ injection, power transition, EFI call, DMA test or guest test |

`acpiexec` can exit zero even when method evaluation fails. `aml_tests.py` checks returned buffer content and deliberately exits1 for the two regression cases. ACPICA reports four outstanding cache allocations at process teardown in these runs; no attribution to platform firmware is made. An initial manually escaped namespace invocation failed AE_NOT_FOUND; the corrected invocation and automated tests are the result used here. Raw initial log is retained. Early extractor bugs were corrected before final outputs, with unit tests for physical base/size and parent-child ownership; do not use intermediate terminal output as final findings.

Fixed-table `.acpi` files include linker padding beyond Header.Length. Checksums are zero-initialized before AcpiTableDxe installs the tables. `fixed_tables.py` checks pre-install structures, **not runtime checksums**. No installed RSDP/XSDT or memory map was supplied. FADT/SPCR header validation is narrower than a full field-by-field validator; ISA/cache capabilities and physical addresses remain hardware claims.

## Reproduce

```sh
python3 meta.py validate
python3 -m unittest discover -s tests
python3 docs/audit-2026-11-20/reproduce.py \
  --platform-repo ../edk2-platforms \
  --scratch /tmp/k3-audit-new-reconstruction
python3 docs/audit-2026-11-20/audit_static.py
python3 docs/audit-2026-11-20/dependencies.py
python3 -m unittest discover -s docs/audit-2026-11-20 -p 'test_*.py'
python3 docs/audit-2026-11-20/fixed_tables.py
python3 docs/audit-2026-11-20/aml_tests.py
```

The last command is **expected to fail until the reported AML defects are fixed**. Preserve that signal. `reproduce.py` refuses an existing scratch directory. It uses only local Git objects, verifies every patch SHA256 and never changes the supplied checkout. Maintained evidence follows the supplied checkout, so first verify its HEAD matches the report. `reproduction-commands.json` records preprocessing warnings and patch commands. The saved current manifest and source identity must travel with output; a changed manifest creates a new audit baseline.

The six fixed tables can be rebuilt with `evidence/fixed-tables/rebuild.sh`. This recipe intentionally documents its workstation paths and generated AutoGen.h dependency. It is **not a clean-machine firmware build**. Existing core headers/generated PCD values are borrowed, while platform C files come from the reconstructed source. Freeze those inputs before promoting it to release CI. The `.acpi` files retained here are evidence snapshots, not updated firmware to flash.

`clock_inventory.py --help` documents reconstruction/carry/DT paths. This is a declaration extractor, not a hardware-model solver. The full flattened dependency graphs additionally preserve board-effective status and provider IDs.

## CI adoption

Use two separate jobs:

1. **Source contract job:** verify manifest completeness and hash all inputs; reconstruct sources in a clean container; compile DT and every supported ACPI variant; run the table and AML regressions; publish machine-readable reports even on failure. Require table UID/hart/reference consistency and block new unresolved resources. Add reviewed exceptions for intentional parent/child windows; never suppress all overlaps. Run with ordinary Python (the current fixed-table checker uses assertions; `python -O` disables them).
2. **Hardware qualification job:** run on an identified board/firmware/kernel combination with recovery, serialize access, and collect `regression.csv` evidence. Only this job may issue a hardware PASS. Keep destructive negatives in emulation or a dedicated controlled bench. Fail closed when required measurements or devices are absent.

Do not add a CI badge that simply validates these historical blobs. CI must regenerate tables from the changed sources. Replace machine-local OpenSBI/core/compiler dependencies with accessible pinned inputs, and pin the exact target Linux carry set. A matching hash proves identity, not correctness.

Current automated detection coverage:

| Requested check | Implemented coverage / remaining work |
|---|---|
| MMIO conflicts | Expanded DSDT QWordMemory range/length/overlap checks; DT reg preserved. PCI translation, arbitrary AML dynamic resources and all RAM reservations need full interval model |
| DT/ACPI mismatches | Exhaustive raw property ledger and base-address candidates in both directions; manual semantics retained as unresolved |
| Unresolved namespace references | ACPICA load/evaluation; static extractor does not implement general AML graph analysis |
| Missing/duplicate identities | HID/UID duplicates flagged for review; PRP0001 compatible/path semantics require manual disposition |
| GSI/source ranges | Shipped direct GSI values1..512 and MADT contract; cascades/INTx/MSI runtime not inferred |
| IMSIC configuration | Exact rebuilt topology/count assertions and negative MADT mutations; silicon identity/file capacity requires target probe |
| Clock gaps | Complete supported phandle relations plus declared CCU and peripheral-owner analysis; consumer lookup gaps manually confirmed |
| Reset/regulator/power gaps | Preserved raw properties and resolved dependency edges; dynamic state/ownership not measurable offline |
| Parent/child inconsistency | Full DT paths, ASL nested paths and exclusion of child resources from parent's own records; actual Linux enumeration requires target source/runtime |

## Target evidence collection

After allocating the board qualification window, collect (not executed here):

```sh
uname -a
cat /proc/cmdline
cat /proc/interrupts
cat /proc/iomem
lspci -nnvv
lsusb -t
dmesg
acpidump -b
```

Capture output paths, timestamps, exit codes and kernel/firmware identities. These commands alone do not exercise the test suite. Debugfs interfaces depend on kernel configuration; absence must be logged, not interpreted as a passed test. Do not run `devmem`, modify IRQ/power registers or alter installed tables on the working system. EFI variable/time tests can write storage even when the apparent call is a time read; follow the test-specific disposable GUID/environment prerequisites.
