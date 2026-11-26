# Build the Pico-ITX EL10-284 kernel RPM

Use an EL10 RPM packaging environment and the stock RISC-V `kernel-6.12.0-284.rv.0.el10.src.rpm`. Its `linux-kernel-test.patch` supplies BSP drivers used by the K3 series. The maintained spec applies the distro patches first, then the K3 patches in `ApplyPatch` order. [Kernel spec](kernel.spec)

## Stage the source RPM

From the repository root, unpack the stock SRPM in a fresh RPM build tree. Stage the spec, config, and patches together. Source44 reads the config under the name `kernel-riscv64-rhel.config`.

```bash
series=$PWD/patches/kernel/el10-284
stock_srpm=/path/to/kernel-6.12.0-284.rv.0.el10.src.rpm
top=$(mktemp -d "$HOME/rpmbuild-k3-kernel.XXXXXXXX")
mkdir -p "$top/SPECS" "$top/SOURCES"
rpm2cpio "$stock_srpm" | (cd "$top/SOURCES" && cpio -idmu --quiet)
install -m 644 "$series/kernel.spec" "$top/SPECS/kernel.spec"
install -m 644 "$series/config-acpidebug" "$top/SOURCES/kernel-riscv64-rhel.config"
install -m 644 "$series"/*.patch "$top/SOURCES/"
rpmbuild --define "_topdir $top" --target riscv64 -bs "$top/SPECS/kernel.spec"
```

## Rebuild and check the packaged config

Use a builder configured with the `rhel-10.3-riscv64` Mock profile. Check its active jobs and free space on the filesystems holding the Mock root and results before starting the full build. The commands below assume the SRPM is in `$top/SRPMS` on that builder.

```bash
release=6.12.0-284.acpidebug.1.el10
mock -r rhel-10.3-riscv64 --uniqueext="$(basename "$top")" \
    --resultdir "$top/results" --rebuild "$top/SRPMS/kernel-$release.src.rpm"

kernel=$release.riscv64
rpm2cpio "$top/results/kernel-core-$kernel.rpm" | \
    cpio -i --quiet --to-stdout "./lib/modules/$kernel/config" | \
    grep -E '^CONFIG_(PCIE_SPACEMIT_K1|GPIO_SPACEMIT_K1|RFKILL_GPIO|DEBUG_INFO_BTF)='
```

Expect four `=y` lines. The PCIe quirk must be built in for boot-time enumeration. Build 6 also included both GPIO drivers and enabled BTF for the spec's bpftool step. Several builds shared this kernel release, so retain the SRPM and output RPM hashes with the effective config when comparing board results. The November 25 record identifies the qualified build by SRPM SHA-256 prefix `f670b0d2`. [Pico-ITX build 6 results](../../../docs/rhct12-firmware-acpi-audit-2026-11-22.md#build-6-qualified-the-fully-self-sufficient-packaged-kernel-2026-11-25-night)

The host tests compile functions from the ECAM driver source and compare that source with the file added by patch 900007. [ECAM source](ecam/pcie-k3-acpi-ecam.c) · [Packaged patch](k3-ecam-segs24.patch)
