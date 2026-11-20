# edk2-platforms ACPI patch series export

Export date: 2026-11-20 (revised). Source tree:
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
| 0001 | ACPI tables for Pico-ITX bring-up: DSDT v8 (COM0/IC00/ETH0/USB2/PCI0/RES0/DBI0 only), MADT (AIA topology: 8×RINTC, IMSIC, APLIC-MSI), K3AcpiTables.inf wiring |
| 0002 | ClockDxe: TSEN/ESPI clock entries; ConfigNum/row mismatch fixes (the address-0 write that reset the SoC); zero-address guards |
| 0003 | AcpiClockInitDxe: deterministic ReadyToBoot clock bring-up for firmware-unowned OS-driven blocks (TSEN, ESPI) |
| 0004 | MUSE-Pico DSC/FDF: AcpiClockInitDxe wiring, quiet-console status-code/DEBUG PCDs, ACPI SDT protocol install |
| 0005 | DwEqosDxe: leave EMAC clocks enabled at ExitBootServices (ACPI handoff) |
| 0006 | DesignWarePcieControllerLib: bus-0 2MB config window (pairs with the kernel MCFG quirk) |
| 0007 | ResetSystemLib: resets via the SBI srst extension instead of direct WDT MMIO |
| 0008 | SPCR re-add (v4, 16550-with-GAS, namespace `\_SB.COM0`) + COM0 `_DSD` XScale compatible; BaudRate 115200 and UART clock 14745600 fixes |

**Peripheral coverage of this series is exactly:** serial console (COM0),
GMAC ethernet, USB2/xHCI, PCIe root bridge + NVMe-by-MSI-X, thermal sensor
clocks, eSPI controller clocks, and the SPCR console contract. The DSDT in
0001 does **not** contain GPIO, I2C, eSPI-EC, PWM-fan or tsensor devices;
see "Historical evidence vs this series" below.

## Verification

- All eight patches apply cleanly in order to the pinned baseline
  (`git apply --check` + `git apply`, the exact mechanism `meta.py` uses),
  and reproduce the maintained tree's build inputs content-exactly. Three
  files (`K3AcpiTables.inf`, `ClockDxe.c`, `DwEqosSpacemit.c`) differ from
  the live tree only in line endings: the export restores the baseline CRLF
  convention so the diffs are content-only.
- 0008 was built and verified in isolation for this export: iasl-clean DSDT,
  full RELEASE firmware build (`ACPI_ENABLE=TRUE`), SPCR decoded from the
  built DXEFV (GAS mmio32 0xd4017000, GSI 42, baud 115200, UART clock
  14745600, namespace string `\_SB.COM0`). Its hardware boot validation is
  pending and is scheduled with the board owner.
- The live firmware bundle built from these inputs is
  `pico-acpi-v9e-20261119` (fedora-k3-firmware `bundles/pico-acpi-v9`,
  edk2 ITB sha256 `01a4194e6ff4fcea312da819b8903c67ee6756206f0fe7276cca98919bd103af`).

## Historical evidence vs this series

GPIO (gpiolib-acpi), I2C (i2c-k1 + at24 EEPROM), thermal telemetry
(k3_tsensor), eSPI/ChromeOS-EC/PWM-fan and the XScale serial quirk are all
**validated on hardware** — but through kernel-side experiment AML
(GRUB DSDT overrides v9/v10, `patches/acpi-kernel/experiments/`), not
through patch 0001's DSDT. Those devices are *not* in this series. They get
promoted into the firmware DSDT only as each experiment DSDT is qualified
and folded back; the eSPI/EC/fan set (DSDT v10) is the next promotion
candidate and lives in the maintained tree as uncommitted work until then.

## Deliberately NOT exported (present in the maintained tree)

- `Pcct.aslc`, `K3AcpiNvs.h`, `AcpiNvsDxe/`: the PCC power-model design;
  unwired draft (no DSC/FDF reference), gated on the ESOS PCC endpoint
  passing the acceptance requirements in
  `docs/k3-maintained-efi/acpi-platform-management-architecture.md`.
- `Dsdt/Uart.asl`, `Platform.asl`, `Soc.asl`, `Power.asl`, `*.noscope`:
  stale DSDT split experiments; `Dsdt.asl` is the single source of truth.
  (`Spcr.aslc` **is** exported and wired via patch 0008.)
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
