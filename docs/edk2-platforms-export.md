# edk2-platforms ACPI patch series export

Export date: 2026-11-20. Source tree:
`workdir/k3-maintained-efi/edk2-platforms` (maintained tree, baseline commit
`8e686e13d9f76e9acc478fa03bf1ba74f06517a2`, "Platform/Spacemit/K3: reject
incomplete RAM fixups and conflicting description modes").

## Series

Applied in order by `meta.py prepare` with `git apply` (not `git am`; the
series carries CRLF context lines from vendor files that mbox parsing
mangles). Authorship: the ACPI integration work is user-authored (Brian
'redbeard' Harrington) derived from DT research and hardware testing; vendor
hardware definitions are not vendor-authored changes.

| Patch | Content |
| --- | --- |
| 0001 | ACPI tables for Pico-ITX bring-up: DSDT (COM0/IC00/ETH0/USB2/PCI0/GPIO/I2C2+EEPROM/TSEN/ESPI+EC+PWM+fan), MADT (AIA topology), tables INF |
| 0002 | ClockDxe: TSEN/ESPI clock entries; ConfigNum/row mismatch fixes (the address-0 write that reset the SoC); zero-address guards |
| 0003 | AcpiClockInitDxe: deterministic ReadyToBoot clock bring-up for firmware-unowned OS-driven blocks (TSEN, ESPI) |
| 0004 | MUSE-Pico DSC/FDF: AcpiClockInitDxe wiring, quiet-console status-code/DEBUG PCDs, ACPI SDT protocol install |
| 0005 | DwEqosDxe: leave EMAC clocks enabled at ExitBootServices (ACPI handoff) |
| 0006 | DesignWarePcieControllerLib: bus-0 2MB config window (pairs with the kernel MCFG quirk) |
| 0007 | ResetSystemLib: resets via the SBI srst extension instead of direct WDT MMIO |

## Verification

- All seven patches apply cleanly in order to the pinned baseline
  (`git apply --check` + `git apply`, the exact mechanism `meta.py` uses).
- The resulting tree reproduces the live maintained tree's build inputs
  content-exactly. Three files (`K3AcpiTables.inf`, `ClockDxe.c`,
  `DwEqosSpacemit.c`) differ from the live tree only in line endings: the
  export restores the baseline CRLF convention so the diffs are
  content-only (local edits had LF-converted them wholesale).
- The live firmware bundle built from these inputs is
  `pico-acpi-v9e-20261119` (fedora-k3-firmware `bundles/pico-acpi-v9`,
  edk2 ITB sha256 `01a4194e6ff4fcea312da819b8903c67ee6756206f0fe7276cca98919bd103af`).

## Deliberately NOT exported (present in the maintained tree)

- `Spcr.aslc`, `Pcct.aslc`, `K3AcpiNvs.h`, `AcpiNvsDxe/`: experimental and
  not wired into `K3AcpiTables.inf`/the platform DSC; the shipping firmware
  builds without them (live tables: APIC/DSDT/FACP/MCFG/PPTT/RHCT).
- `Dsdt/Uart.asl`, `Platform.asl`, `Soc.asl`, `Power.asl`, `*.noscope`:
  stale DSDT split experiments; `Dsdt.asl` is the single source of truth.
- `Silicon/Spacemit/K3/K3.dec` PCC feature PCD: consumed only by the
  unwired AcpiNvsDxe experiment.
- `docs/k3-maintained-efi/`: maintained-tree documentation, not a build
  input (kept in the maintained repository).

## Outstanding dependency pins (next increment)

- EDK2 core / vendor SDK: the build consumes the vendored edk2 tree at
  `K3-Ubuntu-Images` commit `0dbb43a7303de574dc3e98ddae7666b68cf664e0`
  (provides edk2 core, BaseTools, and the SPL/boot-chain files used by the
  FIT packaging). Pin it as an explicit component once the canonical
  reachable remote for that revision is confirmed.
- Compiler: `riscv64-linux-gnu-gcc` (GCC 16.2.1 Red Hat Cross) — needs an
  explicit toolchain pin per the README toolchain policy.
