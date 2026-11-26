# Archived EL10-284 kernel patch revisions

This directory preserves earlier attempts to port UFS, GPIO and PCIe to the Pico ACPI kernel. The package spec, config and selected patches now live with the [maintained EL10-284 build instructions](../../../../../../patches/kernel/el10-284/README.md).

| Archived revision | What it establishes |
| --- | --- |
| [UFS ACPI patch](k3-ufs-acpi.patch) | An early port to the distro BSP. The reset guard and probe branch land at file scope and produce invalid C. The spec selects the [corrected build-5 UFS patch](../../../../../../patches/kernel/el10-284/k3-ufs-acpi-build5.patch). |
| [GPIO reconstruction](k3-gpio-acpi.patch) | The flat 128-pin ACPI chip and probe branch. This reconstruction references `k3_gpio_data` before its definition. |
| [Build-5 GPIO patch](k3-gpio-acpi-build5-authoritative.patch) | The patch recovered from the build-5 SRPM places the probe after the register data. It establishes the base used by the later v3 patch. |
| [GPIO v2](k3-gpio-acpi-v2.patch) | Adds a probe check for a register window of at least `0x140` bytes. The spec selects [GPIO v3](../../../../../../patches/kernel/el10-284/k3-gpio-acpi-v3.patch). |
| [Early ECAM filter](k3-ecam-mcfg-quirk.patch) | Proposed rejecting nonzero root-bus device/function numbers on segments 0, 2 and 4. |
| [Three-part PCIe series](ecam/README) | Introduced viewport operations for segments 2 and 4. The maintained [combined patch](../../../../../../patches/kernel/el10-284/k3-ecam-segs24.patch) also handles segment 0 and restricts access to each viewport controller's root-port DBI header to device/function zero. |

The [adapter notes](../../adapters/el10-284.md) record the compile failures and the changes recovered from the SRPM. The [release audit at `33daace`](../../../../../project-audit-33daace.md) identified the invalid UFS patch and the packaging config error.

## Source44 configuration

The distro spec reads `kernel-riscv64-rhel.config` as Source44.
Staging only the old patch directory left the stock config in use, with modular GPIO and PCIe and disabled rfkill GPIO.

The maintained build stages `config-acpidebug` under Source44's name.
The intended effective config sets `CONFIG_PCIE_SPACEMIT_K1=y`, `CONFIG_GPIO_SPACEMIT_K1=y` and `CONFIG_RFKILL_GPIO=y`. [Config and staging instructions](../../../../../../patches/kernel/el10-284/README.md)
