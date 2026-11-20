# edk2-platforms ACPI patch series export

Export date: 2026-11-20 (rev 3). Source tree:
`workdir/k3-maintained-efi/edk2-platforms` branch `k3-maintained-efi`
(tip `8071f600`), baseline commit
`8e686e13d9f76e9acc478fa03bf1ba74f06517a2`.

## Series (12 patches)

Applied in order by `meta.py prepare` with `git apply` (not `git am`; the
series carries CRLF context lines from vendor files that mbox parsing
mangles). Authorship: the ACPI integration work is user-authored (Brian
'redbeard' Harrington) derived from DT research and hardware testing; vendor
hardware definitions are not vendor-authored changes.

| Patch | Content |
| --- | --- |
| 0001 | ACPI tables for Pico-ITX bring-up: DSDT v8 core devices, MADT (AIA topology), tables INF |
| 0002 | ClockDxe: TSEN/ESPI clock entries; ConfigNum corruption fix (the address-0 write that reset the SoC); zero-address guards |
| 0003 | AcpiClockInitDxe: ReadyToBoot clock bring-up for the FIRMWARE-UNOWNED blocks only (TSEN, ESPI). GMAC/PCIe/USB are deliberately excluded — their UEFI drivers enable them during BDS connect |
| 0004 | MUSE-Pico DSC/FDF: ACPI build wiring, quiet-console PCDs, SDT protocol install (kept for tooling; K3AcpiNvsDxe is NOT in components) |
| 0005 | DwEqosDxe: leave EMAC clocks enabled at ExitBootServices |
| 0006 | DesignWarePcieControllerLib: bus-0 2MB config window |
| 0007 | ResetSystemLib: resets via SBI srst; terminal deadloop documented |
| 0008 | SPCR v4 re-add + COM0 XScale compatible; BaudRate/UART-clock fixes |
| 0009 | ACPI 6.6 conformance: processor objects (Cpu.asl), APLIC 512/HardwareId, MADT rev 7, ResourceConsumer, dead-file removal, count static asserts |
| 0010 | DSDT v12 promotion: full qualified peripheral set (GPIO/I2C/EEPROM/eSPI/EC/PWM/fan/tsensor) + MPXY (RSCV0005) + RCLK — the firmware DSDT is complete; the GRUB override is retired |
| 0011 | Audit fixes: RHCT ISA completion (HWCAP), PCI _OSC support/control bitfield separation (MSI vs PCIeCapability), hart contract, borrowed-ID docs, GMAC1/2 register retargeting, EnableClock failure semantics |
| 0012 | \_SB platform _OSC (PCLPI only, 2-DWORD contract, revision/UUID error paths); _LPI REMOVED pending the OpenSBI retentive fix (patches/opensbi/0001: type 0 as plain wfi; build-verified, hardware qualification pending) |

## Current artifact identity

- Firmware chain qualified through pico-acpi-v12 (edk2 9ef6a15f: 0010+0011;
  ESOS 37533b27: the clk framework rework). Live evidence: full RHCT HWCAP
  set, truthful _OSC masks, all RPMI clocks at real rates, all peripherals
  bound from the firmware DSDT with no GRUB override.
- _LPI cycle (0012) in bring-up: _OSC presence and buffer contract proven
  live; FFH encoding, state Flags, and index-0 structuring fixed in AML and
  verified by build decode. Next flash is the first with all gates correct.

## Verification

- All twelve patches apply cleanly in order to the pinned baseline, and
  reproduce the maintained tree content-exactly (CRLF-normalized for three
  vendor files).
- Full RELEASE firmware builds verified at each increment; tables decoded
  from the built FV (see per-patch ledger in patches/edk2-platforms/README.md
  for hardware-qualification status and evidence).

## Deliberately NOT in this series

- `AcpiNvsDxe`, `Pcct.aslc`, `K3AcpiNvs.h`, Power.asl: the PCC power model,
  unwired by design (no DSC/FDF component), gated on the ESOS PCC endpoint
  passing the acceptance requirements.
- CLUSTER_NR `_LPI` state: deferred until cluster wake-mechanism
  qualification.
- A6 (`RSCV0006` SYSMSI): firmware-side unvalidated-MSI-target hole.

## Outstanding dependency pins

- EDK2 core: vendored tree at `0dbb43a7…` — pin as an explicit component
  once the canonical reachable remote is confirmed.
- Compiler toolchain pin for release builds.
- OpenSBI: qualified binary, unpinned source.
