# COM260 IFX contribution plan — scoping analysis (2026-11-24)

## What exists

The MUSE-Pico ACPI flow (13-patch edk2-platforms series) is a single-board
DEFAULT-SKU build. The DSC already declares a COM260 SKU (SkuId 1) with
board-correct PCIe/USB/GMAC/SD/CTF2301 PCDs, and SkuSelectDxe picks it from
the DTB model string ("COM260" in "SpacemiT K3 Com260 IFX" — case-insensitive
match). K3DeviceTree.inf already ships k3-com260-ifx.dts. But the ACPI tables
(DSDT/MCFG) are SKU-blind: they describe the Pico-ITX's DEFAULT hardware.

## Hardware delta (OS DT inventories + pico-com260-differences.md)

COM260 IFX enabled set vs Pico:
- GMAC1 (0xcac82000, RGMII+RTL8211F) not GMAC0
- PCIe0 (x4 NVMe) + PCIe3 (0x80c00000, seg 3) + PCIe4 (0x81000000, wifi);
  NO PCIe2. Segments: 0 @0x1100000000, 3 @0x1280000000, 4 @0x12c0000000
- USB3B (0x81400000, SS via combophy sel2 + hub) + USB3A (0xcad00000);
  no USB3C/D, no eSPI/EC (fan is i2c6 CTF2301 @0x4c, not cros-ec-pwm)
- i2c0 fusb301 TCPC, i2c1/i2c2 EEPROMs (ONIE TLV), i2c8 P1 PMIC, i2c6 CTF2301
- SD (mmc@d4280000, cd gpio bank0 line4), UFS, tsensor, P1 dldo4 always-on
- 32 GiB RAM on tested unit

## What a COM260 contribution needs

1. DSDT: SKU-appropriate devices. Options: (a) runtime AML (WLEN-style _STA
   gating by SKU PCD) — complex, unauditable; (b) per-SKU DSDT selected at
   build (ACPI table INFs become SKU-aware like the PCDs); (c) a separate
   COM260 platform directory (COM260-IFX.dsc/fdf) reusing Silicon/Spacemit/K3
   — cleanest, mirrors how the DT already splits per board.
2. MCFG: segments 0/3/4 (NOT 0/2/4 — patch 0013's seg 2 is Pico's 10G NIC
   port; COM260 uses port D = segment 3 @0x1280000000).
3. PCIe PCD gap: SKU1 (COM260) sets `PcdPcieHostEnableMask|0x09` ("Port A +
   Port D") but the board enables PCIe0+PCIe3+PCIe4 (wifi = Port E, bit 4).
   Correct mask is **0x19** (A+D+E). This is a real vendor bug: wifi never
   trains on a COM260 SKU build. (The per-port controller/root-bridge tables
   in `[PcdsFixedAtBuild.common]` are SKU-shared and already contain all 5
   ports including seg 3 @0x1280000000 — only the enable mask is wrong.)
4. Fan: Ctf2301Dxe writes PWM=0xFF (max!) at boot — this is the loud-fan
   firmware cause on COM260. Contribution: either fix the register program-
   ming (auto LUT + enable) or leave to OS (lm63 driver + hwmon LUT, already
   working on the board).
5. rfkill: W_DISABLE1# is INVERTED on this carrier (pad 73 low = enabled).
   Pico patch 0013's WLEN GpioIo pin 35 polarity is WRONG for COM260; COM260
   needs pin 73 with inverted polarity or a gpio-hog / _DSD approach.
6. k3-firmware tooling: bundle.py rejects board != 'pico-itx'; cli --board
   choices=['pico-itx']. Needs a com260 profile + memory-contract care
   (RCPU0 legacy layout: shmem 0x100800000, identity 0x100e04000).

## Recommended sequencing (contribution-shaped)

Phase A (upstreamable now, board-agnostic):
- Ctf2301Dxe 0xFF write: make the boot fan policy configurable or auto-mode
- k3_thermal sensor-id -19 failure (d4018000): missing sensor registration
  under ACPI — likely tsensor_map/_DSD gap, worth diagnosing on COM260 since
  both boards share the SoC tsensor
Phase B (COM260 ACPI enablement):
- COM260-IFX.dsc + DSDT (GMAC1, seg 0/3/4, USB hub, SD, CTF2301+lm63 path)
- k3-firmware com260 bundle profile
- Flash-cycle qualification per AGENTS.md (one variable per flash)

## Evidence from the running board (2026-11-21..24, DT-mode RHEL 10.3)

- WiFi fixed and reboot-persistent on this board via a patched DTB
  (gpio-hog driving pad 73 low; see
  `~/Projects/ai/system_troubleshooting/k3-wifi-troubleshooting.md`).
  Chip-side GPIO_IN_9 measurements prove the W_DISABLE1# inversion.
- Fan: CTF2301 on i2c6 @0x4c binds as lm63 (RHEL kernel); stock firmware
  LUT is all-127C/255 (never spins down); `pwm1_enable=2` + sane LUT gives
  4.5 krpm @ 37C vs 8.7 krpm before. Immediate relief: systemd unit or
  udev rule programming the LUT; qualification path: Ctf2301Dxe fix.
- The eSPI/cros-ec DSDT devices from patch 0010 do NOT apply to COM260:
  its fan is i2c CTF2301 and it has no eSPI EC. A COM260 DSDT must not
  carry ESPI/EC0/PWM0; FAN0 must reference the CTF2301 PWM instead
  (or be left to lm63 hwmon, which needs no DSDT node beyond the i2c
  controller + device).

## Immediate actions possible without a flash cycle

1. OS-side fan quieting on the current install (udev rule + lm63 LUT).
2. Draft the Ctf2301Dxe fix + 0x19 mask + MCFG seg-3 patches as a clean
   series against the pinned edk2-platforms revision; host-verifiable with
   the existing test_acpi_pcie_segments.py pattern (extend
   EXPECTED_MCFG_SEGMENTS per-SKU).
3. File the two vendor bugs (enable mask, CTF2301 max-duty) upstream with
   the evidence above.
