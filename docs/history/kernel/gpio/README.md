# SpacemiT GPIO bring-up on the dbg1 kernel

The early ACPI patch exposes one GPIO chip for the K3's four 32-pin banks. Firmware pin 43 therefore selects bank 1, line 11 for the Chrome EC interrupt. The patch uses the K3 register layout for a `PRP0001` ACPI companion and dispatches child interrupts from the shared threaded parent handler with `handle_nested_irq()`. [Archived downstream patch](downstream-acpi/0001-gpio-spacemit-k1-ACPI-mode-flat-pin-space-nested-IRQ.patch)

The archived diff masks bank interrupts and clears edge enables **at probe**. Its ACPI irqchip flags contain only `IRQCHIP_MASK_ON_SUSPEND`, and it adds no removal callback. The build-5 revision adds `IRQCHIP_IMMUTABLE` to the ACPI irqchip. [Build-5 GPIO patch](../rpm/series/el10-284/k3-gpio-acpi-build5-authoritative.patch)

## Upstream review on November 21, 2026

The review compared the dbg1 tree with these Linux GPIO commits. It recorded matching K3 register offsets and bank offsets (`0x0`, `0x40`, `0x80`, `0x100`), plus dry runs identifying the direction and configuration changes as already present. Three patch files are preserved under [upstream backports considered](upstream-backports-considered/).

| Commit date | Upstream commit | Change | Disposition for dbg1 |
| --- | --- | --- | --- |
| 2025-04 | `d00553240ef8` | Original K1 driver | Baseline |
| 2025-06 | `e6382fcf9890` | Module device table | Upstream driver history |
| 2025-09 | `063411108de6` | Generic GPIO chip API | Already present |
| 2025-09 | `64f89f6e1f2b` | Treewide `BGPIOF_` to `GPIO_GENERIC_` flag rename | Omitted from dbg1. It renamed flags in 22 files. |
| 2026-01 | `da64eb51595b` | K3 SoC register data | Already present |
| 2026-01 | `aa7e37fd770b` | Use PDR for pin direction in the generic bank driver | Already present |
| 2026-03 | `47a9050e678c` | Add `set_config` via `gpiochip_generic_config` | Already present |
| 2026-11 | `4dd10fbbeb9c` | Treewide managed-allocation API conversion | Omitted from dbg1 |

## Why GPIO was built in

The EC probed early and deferred with `-EPROBE_DEFER` while the GPIO controller was modular. On the November 21 `gpioy` boot with `CONFIG_GPIO_SPACEMIT_K1=y`, the 128-pin controller appeared at 0.14 s and the Chrome EC registered at 2.02 s. The record reports zero `-517` deferrals. [Boot observations](../../../boot-and-ec-2026-11-21.md#ec-verification-complete-2026-11-21-final) · [Maintained EL10 build](../../../../patches/kernel/el10-284/README.md)
