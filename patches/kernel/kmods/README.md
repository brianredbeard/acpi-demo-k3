# Build one patched K3 kernel module

Pick one spec. Each SRPM contains that driver's sources, private headers and EL10-284 patch. A binary build runs external-module Kbuild against the exact RISC-V kernel-devel package and checks the resulting module's vermagic. The build host can boot a different kernel.

| Module / spec basename | Patch carried | Default target kernel |
| --- | --- | --- |
| `kmod-ufs-spacemit` | UFS ACPI platform support, corrected build-5 patch | `6.12.0-284.acpidebug.1.el10.riscv64` |
| `kmod-k3_tsensor` | ACPI thermal zones | Same acpidebug kernel |
| `kmod-rfkill-gpio` | PRP0001 radio control | Same acpidebug kernel |
| `kmod-gpio-spacemit-k1` | GPIO ACPI v3, including its earlier fixes | `6.12.0-284.rv.0.el10.riscv64` |

Each spec checks its driver's symbol for `=m` in the target kernel-devel configuration. The full build 6 config builds both GPIO and rfkill GPIO into the kernel. The GPIO module job targets stock 284, which has modular GPIO. The eSPI controller has a boolean Kconfig option, and the MCFG quirk changes PCI enumeration inside ACPI core. Use an object compile for iteration on those two and a kernel image for runtime tests. The staging helper uses the selected EL10 patches and the drivers from the stock SRPM.

## Stage sources once

From the repository root, use the stock RISC-V `kernel-6.12.0-284.rv.0.el10.src.rpm`. This example uses a separate RPM topdir to keep the kernel-build workspace intact.

```bash
jobs=$PWD/patches/kernel/kmods
top=$HOME/rpmbuild-k3-modules
stock=$(mktemp -d)
rpm2cpio /path/to/kernel-6.12.0-284.rv.0.el10.src.rpm |
    (cd "$stock" && cpio -idmu)
"$jobs/prepare-sources" "$stock" "$top/SOURCES"
```

The helper checks the stock tarball and BSP patch hashes, extracts just the required files, and stages the maintained patches. After editing a driver patch in [el10-284](../el10-284/), copy the updated patch into `$top/SOURCES/` before rebuilding its job. Bump the spec's Release counter when distributing a new build for the same ABI.

## Native rpmbuild

Install the matching kernel-devel RPM and the spec's other BuildRequires on the RISC-V builder. Select a job and build its binary and source RPMs:

```bash
job=kmod-k3_tsensor
rpmbuild --define "_topdir $top" -ba "$jobs/$job.spec"
rpm -qlp "$top"/RPMS/riscv64/"$job"-*.riscv64.rpm
```

## Mock

Create the small SRPM on any RPM build host, then use a RISC-V Mock builder. Its repos must supply the exact `kernel-devel-uname-r` requested by the spec. The locally produced acpidebug devel RPM may need to be supplied explicitly.

```bash
rpmbuild --target riscv64 --define "_topdir $top" -bs "$jobs/$job.spec"
# On the RISC-V builder, with that SRPM in $top/SRPMS:
opts=(-r rhel-10.3-riscv64 --uniqueext=k3-module-rpms)
mock "${opts[@]}" --init
mock "${opts[@]}" --install /path/to/matching/kernel-devel.rpm
mock "${opts[@]}" --no-clean --no-cleanup-after \
    --resultdir "$top/results/$job" --rebuild "$top"/SRPMS/"$job"-*.src.rpm
```

Initialize the dedicated root once. Reuse it for later builds. If several releases are in SRPMS, pass the exact SRPM filename. To target another compatible 284 build, pass `--define 'kernel_release FULL_UNAME_R'` both when producing the SRPM and when rebuilding it with rpmbuild or Mock. Select devel artifacts from the actual target build, particularly when different kernels have reused the same release string.

## Inspect the result

Each binary RPM carries its one module under `/lib/modules/<release>/updates/k3/`, requires the matching kernel, and runs depmod on install/removal. Check `rpm -qlp` and `rpm -qp --requires` before installation. These development builds produce unsigned modules. On a target that enforces module signatures, sign with a trusted key as part of local deployment. A module needed from the initramfs also needs to be included in that target's initramfs.

For an ordinary edit/compile loop on the board, the persistent native workspace remains available at `~/kernel-dev`. Use these package jobs when you want transferable artifacts or a clean-toolchain check.
