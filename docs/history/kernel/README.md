# Kernel bring-up history

The following records trace the Pico-ITX kernel changes from the first driver patches through EL10-284 packaging. For a new build, use the [kernel and module RPM guide](../../../patches/kernel/README.md).

| Record | What it preserves |
| --- | --- |
| [Original UFS patch](ufs/0001-ufs-spacemit-ACPI-platform-data-path.patch) | The clock-audit version registers an `axi` alias for `ufs_aclk` and omits the firmware-enabled reference clock. The [early RPM patch](rpm/0001-ufs-spacemit-ACPI-platform-data-path.patch) directly acquires and enables both `ufs_aclk` and `ufs_refclk`. |
| [GPIO bring-up](gpio/README.md) | The downstream ACPI patch and the upstream backport review. RPM patch 0002 is byte-identical to the downstream GPIO patch. |
| [Early RPM packaging](rpm/README.md) | The first three RPM patches, the [EL10 adapter notes](rpm/adapters/el10-284.md), the [validation ledger](rpm/VALIDATED.md) and the [superseded EL10 revisions](rpm/series/el10-284/README.md). |
