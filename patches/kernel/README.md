# K3 kernel RPMs

- **Full EL10 kernel.** Use this for built-in drivers, ACPI PCI enumeration, or changes to the kernel config. The spec applies the K3 series after the distro patches. [Build the kernel RPMs](el10-284/README.md)
- **One driver module.** Use a module RPM when the target kernel config builds that driver as a module (`=m`). Four specs reuse patches from the full kernel series. [Build a module RPM](kmods/README.md)

For board results, see the November 25 build 6 qualification in the [Pico-ITX audit](../../docs/rhct12-firmware-acpi-audit-2026-11-22.md#build-6-qualified-the-fully-self-sufficient-packaged-kernel-2026-11-25-night). Earlier UFS and GPIO bring-up, backport decisions, and RPM patch revisions are in the [kernel history](../../docs/history/kernel/README.md).
