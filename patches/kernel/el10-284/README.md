# Build the Pico-ITX EL10-284 kernel RPM

On a build host configured for EL10 RPM packaging, start with the sources from the stock RISC-V `kernel-6.12.0-284.rv.0.el10.src.rpm` staged in a dedicated RPM build tree. Its `linux-kernel-test.patch` supplies BSP drivers used by the K3 patches. The [maintained spec](kernel.spec) applies the distro patches first and then the K3 patches in its `ApplyPatch` order.

From the repository root, set `top` to that tree and stage the spec, config, and patches together. Source44 reads the config under the name `kernel-riscv64-rhel.config`.

```bash
series=$PWD/patches/kernel/el10-284
top=$HOME/rpmbuild-k3-kernel
install -m 644 "$series/kernel.spec" "$top/SPECS/kernel.spec"
install -m 644 "$series/config-acpidebug" "$top/SOURCES/kernel-riscv64-rhel.config"
install -m 644 "$series"/*.patch "$top/SOURCES/"
rpmbuild --define "_topdir $top" --target riscv64 -bs "$top/SPECS/kernel.spec"
```

Rebuild the resulting SRPM with `mock -r rhel-10.3-riscv64 --rebuild <srpm>`. Verify the effective build config has `CONFIG_PCIE_SPACEMIT_K1=y`, `CONFIG_GPIO_SPACEMIT_K1=y`, and `CONFIG_RFKILL_GPIO=y`. The build 6 config also enables `CONFIG_DEBUG_INFO_BTF` for the spec's bpftool step.

The [ECAM driver source](ecam/pcie-k3-acpi-ecam.c) feeds the host tests, which compare it with the driver carried by [patch 900007](k3-ecam-segs24.patch).
