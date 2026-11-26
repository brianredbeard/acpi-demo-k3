# K3 Pico-ITX ACPI bring-up patches

These 13 patches reconstruct the early Pico-ITX ACPI bring-up on the edk2-platforms baseline `8e686e13d9f76e9acc478fa03bf1ba74f06517a2`. For the qualified rhct17b firmware, use the separate build recipe pinned to `64ba91f0`. [rhct17b reproduction](../../recipes/edk2/rhct17-varwrite/README.md)

## Applying the series

`meta.py prepare` reads the order and SHA-256 values from the edk2-platforms component in the [source lock](../../sources.lock.json). The [series file](series) lists the same filenames for manual application. On a clean checkout of the exact baseline, run `git apply --check` and then `git apply` for each patch before checking the next. Preserve the CRLF context in the vendor files.

## Patch ledger

| Patch | Change in this series |
| --- | --- |
| 0001 | Add the Pico DSDT and ACPI table wiring, including the AIA interrupt topology and RHCT. |
| 0002 | Add thermal sensor (TSEN) and eSPI clocks to ClockDxe. Correct table counts that led to writes to address zero. |
| 0003 | Enable TSEN and eSPI clocks at ReadyToBoot for Linux. UEFI device drivers manage GMAC, PCIe, and USB during boot. |
| 0004 | Wire the clock driver into the Pico ACPI build, install the ACPI SDT protocol, and reduce boot-console output. |
| 0005 | Leave the GMAC bus clocks enabled at ExitBootServices so the OS can access the controller. |
| 0006 | Map buses 0 and 1 through a 2 MiB DesignWare configuration window. The kernel quirk filters ghost devices on the root bus. |
| 0007 | Route resets through SBI system reset. The recorded cold, warm, and shutdown checks for this change used COM260. |
| 0008 | Restore SPCR v4 for the serial console at 115200 baud and publish the XScale-compatible UART binding on COM0. |
| 0009 | Add the processor objects matching the eight X100 harts, correct MADT/APLIC fields, and fix device resource flags. |
| 0010 | Promote the tested GPIO, I2C2/EEPROM, eSPI/EC, fan, thermal, MPXY mailbox, and RPMI clock descriptions into the firmware DSDT. |
| 0011 | Complete the RHCT ISA string, correct PCI `_OSC` masks, and fix GMAC clock register selection and error handling. |
| 0012 | Confirm platform-coordinated low-power idle through `_OSC` and omit `_LPI` states pending a retentive OpenSBI path. The filename reflects an earlier draft. |
| 0013 | Add PCI root bridges on segments 2 and 4, MCFG entries for both, GPIO-backed WLAN/Bluetooth controls, and port mask `0x15`. |

## What was verified on hardware

- **v11/v12 serial and clock bring-up.** With the corresponding kernel and ESOS, Linux booted on the SPCR console, bound the eight processor objects, and reported 13 RPMI clocks with real rates, including `ufs_aclk` at 491.52 MHz. The v12 firmware DSDT boot removed the GRUB table override. [Clock and v12 boot evidence](../../docs/rpmi-clock-qualification-2026-11-20.md)
- **v13 idle negotiation.** The platform `_OSC` handshake was observed with mask `0x80`. Patch 0012 omits idle states because of the suspend behavior of the OpenSBI image used in that cycle. [v13 verification record](../../docs/v13-boot-checklist.md)
- **PCIe and radio bring-up.** Patch 0013's MCFG contains segments 0, 2, and 4. The initial staged image and subsequent boot investigation are recorded separately. Later firmware advertises only segment 0 in MCFG and uses compact windows for 2 and 4. [Initial implementation](../../docs/wifi-pcie-acpi-2026-11-22.md) · [Later PCIe investigation](../../docs/rhct12-firmware-acpi-audit-2026-11-22.md)

The export leaves the PCC power-model draft unwired, omits the unvalidated SYSMSI device, and defers cluster non-retentive idle. The export record describes the first twelve patches and their scope. The ACPI work derives from device-tree research and board testing. Preserve upstream notices and the original authorship when reusing it. [Export record](../../docs/edk2-platforms-export.md) · [Provenance](../../docs/provenance.md)
