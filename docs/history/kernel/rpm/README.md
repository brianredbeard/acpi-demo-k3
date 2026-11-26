# Kernel RPM patch series (the mock build)

The acpidebug kernel (6.12.0-284.acpidebug.1) built with
mock -r rhel-10.3-riscv64 from the distro 284 SRPM:

- 0000: the upstream spacemit UFS driver (Yixun Lan's series
  v1, lore/linux-riscv 20260702; the driver our destroyed
  tree carried was an early revision of this same code)
- 0001: our ACPI platform-data path for the UFS driver
  (the includes hunk applies manually against the upstream
  driver: property.h + iopoll.h + regmap.h after io.h)
- 0002: the gpio-spacemit-k1 ACPI mode (immutable irqchip,
  flat pin space, nested IRQ, quiesce-on-remove). Two hunks
  apply manually against the 284 distro driver: the ACPI
  match-data fallback (the newer upstream uses
  device_get_match_data + devm_kzalloc_obj; keep the new
  forms, add the has_acpi_companion fallback) and the
  BGPIOF hunk is SKIPPED (284 already carries the renamed
  GPIO_GENERIC_UNREADABLE_REG_SET)
- config: gpioy-deploy/config-gpioy (GPIO_SPACEMIT_K1=y —
  the EC first-probe fix)

The manual hunk applications are recorded here; a future
revision regenerates clean patches against 284.

For current builds, see the [kernel and module RPM instructions](../../../../patches/kernel/README.md).
