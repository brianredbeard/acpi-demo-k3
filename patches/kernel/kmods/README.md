# Build one patched K3 kernel module

Pick the spec for the driver you want to change. Each source RPM contains the driver source, any required private headers, and its EL10 patch. A binary build uses the target's RISC-V `kernel-devel` package and checks the kernel release at the start of the module's vermagic. The build host can boot a different kernel.

| Driver change and RPM spec | Required setting in target kernel | Default target |
| --- | --- | --- |
| UFS ACPI platform support, corrected build-5 patch ([kmod-ufs-spacemit](kmod-ufs-spacemit.spec)) | `CONFIG_SCSI_UFS_SPACEMIT=m` | acpidebug |
| ACPI thermal zones ([kmod-k3_tsensor](kmod-k3_tsensor.spec)) | `CONFIG_SPACEMIT_K3_TSENSOR=m` | acpidebug |
| PRP0001 radio control ([kmod-rfkill-gpio](kmod-rfkill-gpio.spec)) | `CONFIG_RFKILL_GPIO=m` | acpidebug |
| GPIO ACPI v3 ([kmod-gpio-spacemit-k1](kmod-gpio-spacemit-k1.spec)) | `CONFIG_GPIO_SPACEMIT_K1=m` | stock SRPM baseline |

The specs default to `6.12.0-284.acpidebug.1.el10.riscv64` for the custom kernel and `6.12.0-284.rv.0.el10.riscv64` for the stock SRPM baseline. Each spec checks its required setting in the target's `.config`. The stock baseline supports the GPIO module job. Build 6 uses modules for UFS and thermal support and builds GPIO and rfkill GPIO into the kernel. The rfkill job therefore needs a compatible build of that baseline configured with `CONFIG_RFKILL_GPIO=m`, even when the release string matches. [Build 6 config](../el10-284/config-acpidebug)

Use the full kernel RPM to test changes to a built-in driver, the eSPI controller, or the ACPI MCFG quirk on hardware. The board's `~/kernel-dev` workspace supports object compiles before packaging. [Full kernel build](../el10-284/README.md) · [Native rig](../../../docs/kernel-dev-rig.md)

## Stage sources once

From the repository root, unpack the stock RISC-V SRPM and select a job. Both build methods below use these variables.

```bash
jobs=$PWD/patches/kernel/kmods
job=kmod-k3_tsensor
top=$HOME/rpmbuild-k3-modules
stock=$(mktemp -d)
rpm2cpio /path/to/kernel-6.12.0-284.rv.0.el10.src.rpm |
    (cd "$stock" && cpio -idmu)
"$jobs/prepare-sources" "$stock" "$top/SOURCES"
```

The staging helper checks the stock tarball and BSP patch hashes, extracts the required files, and copies the maintained patches into `$top/SOURCES/`. After editing a patch, rerun the helper or copy the updated patch from the kernel series before rebuilding. Bump the spec's Release counter when distributing a new build for the same ABI. [Staging helper](prepare-sources) · [Kernel series](../el10-284/)

## Native rpmbuild

Install the matching `kernel-devel` RPM and the spec's other BuildRequires on the RISC-V builder. Then build the selected job's binary and source RPMs.

```bash
rpmbuild --define "_topdir $top" -ba "$jobs/$job.spec"
rpm -qlp "$top"/RPMS/riscv64/"$job"-*.riscv64.rpm
```

## Mock

Create the small SRPM on an RPM build host.

```bash
rpmbuild --target riscv64 --define "_topdir $top" -bs "$jobs/$job.spec"
```

On the RISC-V Mock builder, set `srpm` to the exact file from that command. Initialize the dedicated root once. If its repositories lack the matching `kernel-devel-uname-r`, supply the devel RPM from the target build with `--install`.

```bash
srpm=/path/to/kmod-k3_tsensor-1-1.6.12.0_284.acpidebug.1.el10.riscv64.src.rpm
results=$(mktemp -d "$HOME/k3-module-results.XXXXXXXX")
opts=(-r rhel-10.3-riscv64 --uniqueext=k3-module-rpms)
mock "${opts[@]}" --init
# Uncomment to supply a local kernel-devel RPM.
# mock "${opts[@]}" --install /path/to/matching/kernel-devel.rpm
mock "${opts[@]}" --no-clean --no-cleanup-after --resultdir "$results" --rebuild "$srpm"
```

Reuse the initialized root for subsequent builds against the same kernel. To target another compatible build of the same source baseline, pass `--define 'kernel_release FULL_UNAME_R'` both when producing the SRPM and when rebuilding it with rpmbuild or Mock. When two builds share a release string, select the devel RPM from the build you intend to boot so its symbol versions match.

## Inspect the result

Each binary RPM installs one module under `/lib/modules/<release>/updates/k3/`, requires the matching kernel, and runs depmod on installation and removal. Check the RPM's file list with `rpm -qlp` and dependencies with `rpm -qp --requires` before deployment. These specs produce unsigned modules. Sign with a trusted key if the target enforces module signatures. For a driver needed during early boot, include the module in the matching initramfs.
