# Early UFS and PCIe porting notes

The two files here record changes considered for the first EL10-284 kernel RPMs.

| File | Contents |
| --- | --- |
| [UFS ACPI additions](ufs-acpi-adds.txt) | C fragments for the probe branch, the `spacemit,apmu-ufs-reg` reset sequence and lane count. The code maps `axi` to `ufs_aclk` and `ref` to `ufs_refclk`, then adds resolved clocks to the UFS host's clock list. The reset guard and probe branch each belong inside their target function. |
| [PCIe enumeration proposal](k3-ecam-mcfg-quirk.txt) | A design note proposing a root-bus device/function filter for segments 0, 2 and 4. Later EL10 work kept ECAM for segment 0 and used a 64 KiB configuration viewport on segments 2 and 4. |

The [EL10 adapter notes](../adapters/el10-284.md) explain how driver layout affected patch placement. The [archived diffs](../series/el10-284/README.md) show earlier attempts. The [maintained RPM inputs](../../../../../patches/kernel/el10-284/README.md) identify the versions selected for builds.
