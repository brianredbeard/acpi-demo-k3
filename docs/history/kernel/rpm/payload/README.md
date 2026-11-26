# Kernel payload (semantic content, baseline-free)

The acpidebug kernel's custom content, separated from any
specific kernel version's context:

- ufs-acpi-adds.txt — the ACPI platform-data path for the
  spacemit UFS driver: the APMU reset define, the
  ufs_acpi_clocks table (axi->ufs_aclk, ref->ufs_refclk),
  ufs_spacemit_acpi_init (lanes + RPMI clocks into hba's
  clk_list_head), ufs_spacemit_acpi_reset (the
  spacemit,apmu-ufs-reg regmap sequence), the probe_acpi
  function + the of_node dispatcher.

Each payload ships as splice-ready text (find anchors, not
line numbers). The series/ dirs hold the GENERATED diffs
per kernel version (build artifacts, regeneratable).
