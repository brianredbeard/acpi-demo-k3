# edk2-platforms K3 ACPI patch series

Hardware-validated ACPI bring-up series for the Spacemit K3 MUSE-Pico (12
patches). Qualified on flash through `pico-acpi-v12-20261120` (firmware DSDT
complete, GRUB override retired); the `_LPI` cycle (0012) is in bring-up with
its gate ledger in docs/v13-boot-checklist.md.

## Source identity

- edk2-platforms at `8e686e13d9f76e9acc478fa03bf1ba74f06517a2` (branch
  `k3-maintained-efi`, the 6-patch DT-handoff series tip, upstream of the
  spacemit `k3-release-opensource` merge).
- `sources.lock.json` records the ordered patch hashes; `meta.py validate`
  verifies them; `meta.py prepare` applies them to the pinned revision.
- `series` is the authoritative order. Apply with `git apply --check` then
  `git apply`, in order, to a clean checkout of the pinned revision.

## Patch ledger

| Patch | Purpose | Validation |
|---|---|---|
| `0001` ACPI tables for Pico-ITX bring-up | Monolithic DSDT v8 (IC00/COM0/ETH0/USB2/PCI0/RES0/DBI0), MADT/RHCT (8×RINTC, IMSIC, APLIC-MSI), K3AcpiTables.inf wiring | Live boot: full RHEL via ACPI enumeration |
| `0002` ClockDxe TSEN/ESPI entries | TSEN (APBC+0x6C) and ESPI gate+reset rows in the EDK2 clock driver | v9c/v9e on flash: thermal channels read, ESPI clock handoff |
| `0003` AcpiClockInitDxe | Deterministic OS-visible device-block clock state at ReadyToBoot (TSEN+ESPI rows only; GMAC/PCIe/USB deliberately excluded — their UEFI drivers already enable them during BDS connect; the v9b reset loop was the ClockDxe ConfigNum corruption fixed in 0002) | v9c on flash: no reset loop, TSEN up, no GMAC/NVMe regression; v9e: ESPI handoff |
| `0004` MUSE-Pico ACPI build config | DSC/FDF/Spacemit.dsc.inc wiring: ACPI table set, AcpiClockInitDxe, PcdInstallAcpiSdtProtocol, status-code mask 0x02, DEBUG-print level | Builds RELEASE; quiet console verified on flash |
| `0005` DwEqosDxe EMAC clocks | Stop gating EMAC bus clock at ExitBootServices (APMU EMAC0 CLK_RES_CTRL) | Live: GMAC MMIO does not wedge kernel; full DHCP/SSH |
| `0006` PCIe bus-0 config window | 2 MB DW iATU OB window for bus 0 at 0x11_00000000 | Live: ATU OB0 dump base 0x11:00000000; removes kernel ECAM hack |
| `0007` ResetSystemLib resets | Reset path hardening (see patch body) | EFI runtime cold/warm/shutdown cycles (COM260 evidence) |
| `0008` SPCR re-add + UART XScale binding | SPCR v4 (16550-with-GAS, namespace `\_SB.COM0`) back in the INF; COM0 `_DSD` declares `"spacemit,k3-uart", "intel,xscale-uart"` (gates the kernel's PORT_XSCALE fixed-type quirk); BaudRate fixed to 115200 (6.12 spcr.c treats 0 as "already configured"); UART clock 14745600 | iasl-clean DSDT matching the proven v10 COM0 AML; full RELEASE build; SPCR decoded from DXEFV (GAS mmio32 0xd4017000, GSI 42). **Hardware-qualified** on pico-acpi-v11 (2026-11-20): serial console through full RHEL boot, no autoconfig hang |
| `0009` ACPI 6.6 conformance fixes | A1 processor devices (`Cpu.asl` re-included: 8×ACPI0007 + 2×ACPI0010 matching PPTT), A2 APLIC NumSources 511→512, A3 MADT revision 6.5→6.6 (0x07), A4 APLIC HardwareId `SPMT0001`, A5 device `_CRS` ResourceConsumer, A7 dead split-ASL removal, A8 RINTC/RHCT count static asserts. A6 (`RSCV0006` SYSMSI) deliberately excluded — firmware-side unvalidated-MSI-target hole | Full RELEASE build; decoded from DXEFV: rev 7, HwId=SPMT0001, 512 sources, 8 RINTC, 8×ACPI0007/2×ACPI0010, consumer flags verified by AML decompile. **Hardware-qualified** on pico-acpi-v11 (2026-11-20): 8 CPUs enumerated and processor objects bound (Task 9 prerequisite), no regressions in thermal/fan/EC/EEPROM/GMAC |
| `0010` DSDT v12 promotion | Full qualified peripheral set (GPIO/I2C2+EEPROM/eSPI+EC+PWM+fan/tsensor) + MPXY (`RSCV0005`) + RCLK (`riscv,rpmi-clock`) promoted from the experiment AML; ResourceConsumer on all device MMIO | **Hardware-qualified** on pico-acpi-v12 (2026-11-20): first boot with NO GRUB DSDT override — all peripherals bound from the firmware DSDT, MPXY mailbox 5 channels, clk-rpmi with real rates |
| `0011` Audit fixes | RHCT ISA completion (full X100 HWCAP set), PCI `_OSC` support/control bitfield separation (MSI vs PCIeCapability), hart contract (8 X100 only), borrowed-ID docs (808622B7/AMZN0001), GMAC1/2 ClockDxe register retargeting, EnableClock zero-address failure semantics, comment corrections | **Hardware-qualified** on pico-acpi-v12: RHCT HWCAP full set live in `/proc/cpuinfo`; `_OSC` truthful mask live (`platform does not support [PCIeHotplug PME AER LTR DPC]`) |
| `0012` platform `_OSC`; `_LPI` removed | `\_SB` `_OSC` PCLPI-only (2-DWORD contract, revision/UUID error paths). `_LPI` REMOVED: the deployed OpenSBI has no genuinely retentive path (type 0 = cluster power-down; CPU_NR hangs without the kernel timer-stop override). Restoration prerequisites tracked in the checklist + patches/opensbi/ | `_OSC` handshake **proven live** (`OS control mask [00000080]`); built DSDT verifies zero `_LPI` |

## Deliberately not in this series

- `Uart.asl` worktree edits: superseded (the exported DSDT v8 carries its
  own COM0 device; SPCR is now re-added via 0008 with the kernel-side
  autoconfig hazard closed).
- `AcpiNvsDxe`, `Pcct.aslc`, `K3.dec` PcdK3PccEndpointPresent,
  `Soc/Power/Platform.asl`: the PCC power-model design remains unwired draft
  (no DSC/FDF reference); it must not ship until the ESOS PCC endpoint passes
  the acceptance requirements in
  `docs/k3-maintained-efi/acpi-platform-management-architecture.md`.
- CLUSTER_NR `_LPI` state: deferred pending cluster wake-mechanism
  qualification (was part of the DSDT v10 experiment AML; the v12 promotion
  carries the qualified subset).

The edk2-platforms worktree also carries uncommitted design/validation docs
(`docs/k3-maintained-efi/acpi-*.md`) and further validated-but-unexported
peripheral state; exporting those is follow-on work.

## v12 hardware validation (2026-11-20)

`pico-acpi-v12` flashed and verified: full RHEL boot with the
firmware-baked DSDT (no GRUB override), all peripherals enumerated
(serial/NVMe/GMAC/GPIO/I2C+EEPROM/eSPI+EC+PWM+fan/tsensor), MPXY+RCLK
transport live with all 13 RPMI clocks at real hardware rates
(ufs_aclk 491.52 MHz), RHCT ISA complete (HWCAP correct), _OSC real
mask, processor objects bound (8x acpi_processor).

## Provenance

The ACPI integration work is user-authored, derived from DT research and
hardware testing (see repo `docs/provenance.md`). No upstream submission is
claimed. Upstream file licenses are preserved; three upstream files carry CRLF
line endings and the patches preserve them.
