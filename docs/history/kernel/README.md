# Kernel bring-up history

- [UFS](ufs/0001-ufs-spacemit-ACPI-platform-data-path.patch) preserves the original storage-driver ACPI patch reviewed in the clock audit.
- [GPIO](gpio/README.md) records the downstream ACPI implementation and the upstream backports considered during bring-up.
- [Early RPM packaging](rpm/README.md) preserves the first three RPM patches, the [EL10 adapter notes](rpm/adapters/el10-284.md), the [validation ledger](rpm/VALIDATED.md), and the [superseded EL10 patches](rpm/series/el10-284/). The first RPM GPIO patch matches the downstream GPIO patch byte for byte. The two early UFS ACPI patches differ, so each stays with its original series.

For current kernel and module builds, use the [kernel patch guide](../../../patches/kernel/README.md).
