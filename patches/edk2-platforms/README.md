# edk2-platforms K3 ACPI patch series

Hardware-validated ACPI bring-up series for the Spacemit K3 MUSE-Pico, exported
from the `k3-maintained-efi` working tree at the state proven on flash as
bundle `pico-acpi-v9c-20261119` (v9e adds the ESPI clock row; the eSPI/EC
DSDT v10 is a separate un-promoted experiment — see below).

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
| `0008` SPCR re-add + UART XScale binding | SPCR v4 (16550-with-GAS, namespace `\_SB.COM0`) back in the INF; COM0 `_DSD` declares `"spacemit,k3-uart", "intel,xscale-uart"` (gates the kernel's PORT_XSCALE fixed-type quirk); BaudRate fixed to 115200 (6.12 spcr.c treats 0 as "already configured"); UART clock 14745600 | iasl-clean DSDT matching the proven v10 COM0 AML; full RELEASE build; SPCR decoded from DXEFV (GAS mmio32 0xd4017000, GSI 42). Hardware boot pending |

## Deliberately not in this series

- `Uart.asl` worktree edits: superseded (the exported DSDT v8 carries its
  own COM0 device; SPCR is now re-added via 0008 with the kernel-side
  autoconfig hazard closed).
- `AcpiNvsDxe`, `Pcct.aslc`, `K3.dec` PcdK3PccEndpointPresent,
  `Soc/Power/Platform.asl`: the PCC power-model design remains unwired draft
  (no DSC/FDF reference); it must not ship until the ESOS PCC endpoint passes
  the acceptance requirements in
  `docs/k3-maintained-efi/acpi-platform-management-architecture.md`.
- DSDT v10 (eSPI/EC/PWM-fan experiment): lives in the outer workspace
  `patches/acpi-kernel/experiments/task4-espi-ec/` until promoted after
  hardware qualification.

The edk2-platforms worktree also carries uncommitted design/validation docs
(`docs/k3-maintained-efi/acpi-*.md`) and further validated-but-unexported
peripheral state; exporting those is follow-on work.

## Provenance

The ACPI integration work is user-authored, derived from DT research and
hardware testing (see repo `docs/provenance.md`). No upstream submission is
claimed. Upstream file licenses are preserved; three upstream files carry CRLF
line endings and the patches preserve them.
