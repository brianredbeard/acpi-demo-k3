# Early EL10-284 kernel RPM patches

These were the first inputs collected for the `6.12.0-284.acpidebug.1.el10` kernel using the RISC-V distro SRPM and the `rhel-10.3-riscv64` mock configuration. The 284 SRPM already supplied a different UFS driver through its `linux-kernel-test.patch`. The packaged build therefore needed patches adapted to that BSP. For a new build, use the [maintained kernel and module RPM guide](../../../../patches/kernel/README.md).

| Archived patch | Purpose and adaptation |
| --- | --- |
| [0000 · SpacemiT UFS driver](0000-ufs-spacemit-upstream-driver.patch) | A copy of the driver from Yixun Lan's July 2026 upstream submission, including Kconfig and Makefile changes. This patch creates the driver files. |
| [0001 · UFS ACPI support](0001-ufs-spacemit-ACPI-platform-data-path.patch) | Adds the ACPI clock, reset and probe paths. When adapting it to the submitted driver, the original notes placed `property.h`, `iopoll.h` and `regmap.h` after `io.h`. The distro driver also needed different insertion points for the reset guard and probe branch. |
| [0002 · GPIO ACPI support](0002-gpio-spacemit-k1-ACPI-mode.patch) | Exposes a flat 128-pin chip and dispatches nested interrupts. The port needed the ACPI match-data fallback and the target driver's flag spelling. The EL10 series retained `GPIO_GENERIC_UNREADABLE_REG_SET`. [GPIO patch history](../gpio/README.md) |

The hand-built `gpioy` configuration enabled `CONFIG_GPIO_SPACEMIT_K1=y` so the Chrome EC could acquire its GPIO interrupt at first probe. Build 5 completed mock packaging, then panicked in eSPI on its recorded ACPI boots before EC registration or UFS attachment. [Build-5 boot record](../../../kernel-284-build5-boot-2026-11-22.md)

The [source fragments and design notes](payload/README.md) show the proposed driver changes. The [EL10-284 revisions](series/el10-284/README.md), [adapter notes](adapters/el10-284.md) and [validation ledger](VALIDATED.md) trace their integration and testing.
