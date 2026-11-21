# gpio-spacemit-k1 patch sets (kernel 6.12.0-284 dbg1 build)

## downstream-acpi/ (our series, not upstream)

0001: the ACPI mode on top of the upstream driver —
PRP0001 companionship, flat 128-pin chip spanning 4 banks,
nested threaded IRQ dispatch off the shared parent GSI,
immutable-irqchip reqres/relres hooks (matching upstream's
IMMUTABLE treatment of the DT chip), remove-time quiesce
(all banks masked + status cleared), K3 register data.

## upstream-backports-considered/ (rejected, documented)

Audited against upstream master (torvalds/linux) on
2026-11-21. Upstream history for the file:

  d005532 2025-04 original K1 driver
  e6382fc 2025-06 MODULE_DEVICE_TABLE
  0634111 2025-09 gpio-generic chip API + IRQCHIP_IMMUTABLE
  64f89f6 2025-09 BGPIOF_ -> GPIO_GENERIC_ rename (TREEWIDE)
  da64eb5 2026-01 K3 SoC support
  aa7e37f 2026-01 PDR direction fix
  47a9050 2026-03 set_config callback
  4dd10fb 2026-11 devm_kmalloc_obj treewide

The dbg1 tree's snapshot ALREADY CONTAINS: the gpio-generic
rework, K3 register data (identical to upstream's converged
values: offsets 0x0/0x4/0x8... banks 0x0/0x40/0x80/0x100),
the PDR direction fix semantics, and set_config (via
gpiochip_generic_config). Verified by content-diff and
patch-application dry-runs (aa7e37f/47a9050 detect as
already-applied; the k3_gpio_data blocks are identical).

NOT backported:
  - 64f89f6 flag rename: treewide (22 files incl.
    include/linux/gpio/driver.h); zero functional change;
    churning the shared 6.12 tree for a rename isn't worth it
  - 4dd10fb devm treewide: global API churn, no functional
    gain

## Packaging (not a patch)

CONFIG_GPIO_SPACEMIT_K1=y in the dbg1 build: the GPIO
controller is core ACPI platform infrastructure on the K3 —
its consumers (cros_ec_espi, the EC PWM fan path) probe
during kernel init; a modular GPIO controller cannot serve
built-in consumers before userspace exists (the -517
deadlock, root-caused 2026-11-21: EC probe 1.9s, defer wait
blocks init 25s, module loads only at initrd userspace,
retry window long gone). The distro multi-board kernel keeps
=m; the dbg1 bring-up kernel builds it in.
