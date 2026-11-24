# Segment 0 with generic PCI configuration access

**The unfiltered Linux scan saw the single Pico NVMe controller at 32 addresses.** The first failing milestone is PCI enumeration, before NVMe binding or root mount. A subsequent gpioy boot on the same board applied `k3_dw_ecam_ops`, found one controller, created eight default queues and mounted the XFS root on `nvme0n1p2`. Repeating the unfiltered scan on the existing layout would reproduce an already observed failure.

## What the captures establish

| Saved boot | Segment 0 evidence |
| --- | --- |
| rhct12, build 5, Nov 22 20:07:31 UTC kernel | Plain ECAM mapping followed by 32 distinct BDFs reporting `1dee:5216` and the same initial BAR 0. The later eSPI panic is a separate failure. The captured kernel-core RPM SHA-256 is `76baaa6c0373a7d27829771f7dc71b60ea83b92ef494362d835e37891074a253`. |
| After the rhct13 flash, Nov 23 05:12:00 UTC com260 kernel build, `6.12.0-284.acpidebug.1.el10.riscv64` | PCI0 mapped at `0x1100000000–0x110fffffff`. All 32 addresses from `0000:00:00.0` to `0000:00:1f.0` reported `1dee:5216`, class `010802`, type 00 and initial BAR 0 `0x1120000000–0x1120003fff`. Linux then assigned resources to the apparent devices. |
| Following gpioy recovery, `6.12.0-dbg1-dbg1`, build #26 | Kernel printed the PCI0 MCFG quirk line, then the plain ECAM mapping line. Only `0000:00:00.0` reported the NVMe ID. Its type-00 endpoint header identifies what Linux actually saw at the root bus. |

The rhct13 transaction recorded EDK2 FIT SHA-256 `13024d1360c915fb73bce809de750dfee82f8b866eba116e73bd6771e1e3bda4` on board `HW4MPK3161280211`, platform commit `8b17165463eff040bb8f486be0b08416daff9f2b`. The two later serial sections show the same SPMT DSDT length `0x2099` and MCFG length `0x3c`. The saved live rhct13 DSDT hashes to `915e8d9d86dbd9031b50c466b26f886dfdf3ccd5a94dc4ec08a470e8a9688367`. The failed boot supplies a table header and kernel banner only. The paired kernels differ in multiple respects.

The original workstation capture is `/tmp/k3-serial-full.log`. Retrieve the two bounded Linux sections with the commands below. Their SHA-256 values, including original line endings, are `40a7d668a165b0390de57fb7f072c07b33b514c827e385798b6562502472ee8a` and `603f4cf916f748ff19d16389054820f90fe3820cd8bbf3b5d3bcb7d97a00509b` respectively. The second section covers enumeration. The NVMe and XFS messages follow it.

```sh
sed -n '152079,152500p' /tmp/k3-serial-full.log > com260-enumeration.serial
sed -n '152619,153000p' /tmp/k3-serial-full.log > gpioy-enumeration.serial
sha256sum com260-enumeration.serial gpioy-enumeration.serial
for capture in com260-enumeration.serial gpioy-enumeration.serial; do
    rg -ao 'pci 0000:[0-9a-f:.]+: \[1dee:5216\]' "$capture" | sort -u | wc -l
done
```

## Why the firmware and Linux see different topologies

rhct13's MCFG publishes segment 0, buses 0–255, at `0x1100000000`. EDK2's PCI library uses DBI at `0x80000000` for bus 0, device 0, function 0 and rejects every other root-bus function in software. The generic OS maps each function at `base + (bus << 20) + (device << 15) + (function << 12)`. The two routes to bus zero give different headers. EFI Shell enumeration through the firmware PCI protocol therefore cannot validate an OS's ECAM accesses. [Firmware access routine](../../edk2-platforms/Silicon/Spacemit/Library/DesignWarePciSegmentLib/DesignWarePciSegmentLib.c) · [Pico controller and resource definitions](../../edk2-platforms/Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc)

Firmware sets up a 2 MiB outbound CFG0 window covering both bus 0 and bus 1, then a CFG1 window starting at bus 2. The comment in the setup routine predicts a DBI response at bus zero. The logged endpoint ID, type and repeated BAR contradict that prediction. Linux's DesignWare host code documents downstream type-0 slot aliasing. Its own root-port access routine selects DBI and filters slots. ACPI MCFG supplies the linear aperture and bus range. It has no field to describe these software access rules. [Window setup](../../edk2-platforms/Silicon/Spacemit/Library/DesignWarePcieControllerLib/DesignWarePcieControllerLib.c) · [DesignWare slot filter](https://github.com/torvalds/linux/blob/20eef29b7c8465ac98d7dd6d6f2ac07a8d8056ca/drivers/pci/controller/pci-host-generic.c) · [Root-port DBI access](https://github.com/torvalds/linux/blob/20eef29b7c8465ac98d7dd6d6f2ac07a8d8056ca/drivers/pci/controller/dwc/pcie-designware-host.c)

**Firmware feasibility question.** Can Port A's host interconnect decode the first ECAM function as the root-port DBI configuration header, return the PCI absent-device value for unused BDFs, and route the secondary bus to CFG0 and later buses to CFG1? Require documentation or a verified hardware mapping for that decode. The vendor manual gives a 64 KiB minimum iATU window. Earlier Pico DXE serial agrees (`DwPcie 0: iATU: unroll T, 32 ob, 32 ib, align 64K, limit 4G`). Each PCI function is 4 KiB and each device slot is 32 KiB. A single minimum-sized CFG0 window still spans two slots. An earlier experiment also reported the optional DBI ECAM base/control registers did not retain writes. Current evidence supports retaining an explicitly scoped OS quirk until physical decoding is demonstrated. [K3 PCIe manual, features table](https://github.com/spacemit-com/docs-chip/blob/4879ed5dfb5415212099dd898906cd893b3fa286/en/key_stone/k3/k3_docs/k3_usermanual/14_connectivity/pcie.md) · [Earlier hardware investigation](../../edk2-platforms/docs/k3-maintained-efi/acpi-status-2026-11-18.md)

## Regression capture for a changed segment-0 decode

1. Use the known one-drive Port A topology. Preserve the board, NVMe identity, firmware readback, BLS entry, kernel image, modules and initramfs hashes for both legs. Use the same kernel, arguments and boot medium for the firmware A/B. Record the complete kernel build banner. Verify in its prepared source that PCI0 reaches `pci_generic_ecam_ops`, including `pci_ecam_map_bus` and generic reads/writes. Check that no K3 early initcall programs the iATU, no other host driver filters root slots, and the console capture begins before MCFG matching. Keep the gpioy recovery entry available. A known independent boot medium can carry the diagnostic kernel and initramfs when the NVMe is under test.
2. Record the firmware's EFI boot-device path and NVMe Block I/O, the GRUB selection, the Linux ACPI interpreter message, the actual MCFG mapping and the full PCI scan on continuous serial. A plain `ECAM at` line appears even on the gpioy quirked boot. Check for a preceding `MCFG quirk:` on the **same root**. A truncated log or unverified image leaves the access path unresolved. Enumeration itself can write BARs. Abort the qualification on the first duplicate endpoint and retain the capture.
3. For a candidate that exposes a conventional root port, expect one type-01 PCI bridge at `0000:00:00.0`, one `1dee:5216` type-00 NVMe on its secondary bus, and a BAR inside the advertised segment-0 memory window. Compare unique BDFs across the **entire** segment. An empty root bus, aliases, or the same endpoint at both root and child fail the topology check. One endpoint on bus zero alone would establish only the flat direct-attached topology.
4. If userspace is reached, collect the following read-only output as root through the captured shell. Set `nvme_bdf` from the unique enumerated endpoint and `ns` to its verified namespace using the sysfs paths. The 4-byte read at offset 256 samples the first extended-config capability header. Compare the bytes with a known-good read from the same device and check the expected extended capability ID. A short read or an unexpected all-zero or all-ones result leaves extended configuration unverified.

```sh
uname -a
cat /proc/cmdline
sha256sum /sys/firmware/acpi/tables/{DSDT,MCFG}
lspci -Dnnk -s '0000:*:*.*'
lspci -Dt
ls -l /sys/class/nvme/*/device /sys/class/block/nvme*n*/device
findmnt -no SOURCE,FSTYPE /
cat "/sys/bus/pci/devices/$nvme_bdf/resource"
od -An -tx1 -j 256 -N 4 "/sys/bus/pci/devices/$nvme_bdf/config"
ls "/sys/bus/pci/devices/$nvme_bdf/msi_irqs"
cat /proc/interrupts
dd if="$ns" of=/dev/null bs=1M count=16 iflag=direct status=none
printf 'NVMe direct read exit status %s\n' "$?"
cat /proc/interrupts
```

Record the read exit status and compare counts for the endpoint's allocated MSI/MSI-X vectors. A candidate passes the direct-attached NVMe milestone when the verified generic path yields the expected topology, driver bind, valid configuration access, successful namespace reads, interrupt delivery and an ordinary NVMe root boot. Keep bridge/switch expansion, multifunction endpoints, INTx, and the 64 KiB viewport controllers on segments 2/4 as separate qualification results. [Segments 2/4 resource and access analysis](rhct12-firmware-acpi-audit-2026-11-22.md)

## Kernel cycle 3d — segments 2 and 4

The EL10 spec applies `k3-ecam-segs24.patch` as Patch900007 after the GPIO patch. Its SHA-256 is `5eeeffdb3da337d10de2091ddfeb48ab6b859d8afc0582a2bbbf82d4a7f73f0a`. The host test checks the packaged driver against the standalone C source. [Active patch](../patches/kernel-rpm/series/el10-284/k3-ecam-segs24.patch) · [284 input configuration](../patches/kernel-rpm/series/el10-284/config-acpidebug)

| Gate | Finding in this patch and 284 source |
| --- | --- |
| Early linkage | `CONFIG_PCIE_SPACEMIT_K1=y` is mandatory. With `=m`, Kbuild makes the object a module, `#ifdef CONFIG_PCIE_SPACEMIT_K1` omits both built-in MCFG rows, and the module references the unexported `dw_pcie_prog_outbound_atu()` and `dw_pcie_version_detect()`. With `=y` the rows and the driver are in vmlinux, and `pci_mcfg.c` declares `k3_dw_ecam_ops`/`k3_dw_seg0_ops` under the same guard. The driver carries `MODULE_LICENSE("GPL")` even though it is built in. An isolated object compile misses both linkage cases. |
| Match and resource | rhct13's packaged MCFG has OEM ID `SPMT  `, table ID `K3      `, OEM revision **1**, and just segment 0. The rows now match revision **1** and supply 64 KiB physical `cfgres` for segments 2 and 4 (`0x1200000000`, `0x12c0000000`). `MCFG_BUS_ANY` keeps buses 0–255, and `k3_dw_ecam_ops.bus_shift = 8` gives `pci_ecam_create()` a 256-bus range over the 64 KiB window. Segment 0 keeps the generic 256 MiB ECAM aperture from MCFG; its row has no `cfgres`. |
| Access correctness | On segments 2 and 4 only devfn 0 reaches the root-port DBI page. Downstream accesses program the iATU with the physical `cfg->res.start` and return the CPU mapping at `cfg->win`; both offsets are masked with `PCIE_ECAM_REG_MASK`. DW geometry is set explicitly (`region_align = SZ_64K`, `region_limit = SZ_4G - 1`, `num_ob_windows = 1`) instead of the scratch-probing `dw_pcie_iatu_detect()`. The PHY AHB link-status register gates downstream access, and the PCI core's `pci_lock` covers target selection plus the actual config load/store, so the driver keeps no private sleeping mutex. |

### Audit close-out, 2026-11-23

Host audit and fixes in the active patch/source:

- Removed the private `k3_ecam_atu_lock` mutex. `pci_lock` already spans
  `map_bus` and the config access, so the driver takes no sleeping lock in
  IRQ-disabled PCI configuration context.
- Masked `where` with `PCIE_ECAM_REG_MASK` in both the root and downstream
  maps. Previously `where = 0x1000` returned `DBI + 0x1000` and `0x100000`
  returned `VA + 0x100000`, which is the translated PCI I/O aperture.
- The viewport controllers expose one DBI header apiece. Reject every
  nonzero root devfn on segments 2 and 4. Segment 0 retains its ECAM
  function addressing and its root device-slot filter.
- Split the CPU mapping from the iATU base: `cfg0_base = cfg->win` for
  accesses, `cfg0_phys = cfg->res.start` for `parent_bus_addr`.
- Set DW geometry explicitly (`region_align = SZ_64K`,
  `region_limit = SZ_4G - 1`, `num_ob_windows = 1`) and called
  `dw_pcie_version_detect()`; did not call `dw_pcie_iatu_detect()`, which
  scratch-probes live windows.
- Mapped the full unrolled iATU file (`SZ_16K`) instead of `0x3f20`.
- Added the PHY AHB link gate (`+0x4`, SMLH `BIT(1)`, RDLH `BIT(12)`) for
  segments 2/4; root DBI access remains available while the link is down.
- Added `MODULE_LICENSE("GPL")`, declared both ops in `pci_mcfg.c` under
  `CONFIG_PCIE_SPACEMIT_K1`, and changed the config to `=y`.

Firmware facts rechecked against the current tree:

- DSDT `RES2`/`RES4` now reserve the 64 KiB viewports
  (`0x1200000000–0x120000FFFF`, `0x12C0000000–0x12C000FFFF`). The earlier
  16 MiB note was stale.
- MCFG publishes only segment 0 at `0x1100000000`; the segment-2/4
  `cfgres` entries are fabricated by the kernel quirk. The DSDT `RES2`/
  `RES4` comments say "declared in MCFG", which is true only for segment 0;
  this is a firmware comment inconsistency, not a driver defect.
- The ATU blocks (`0x80B00000`, `0x81300000`) and PHY link blocks
  (`0x82D00000`, `0x82B00000`) are not reserved in DSDT; the driver
  `devm_ioremap()`s them.
- DSDT `AddressTranslation` gives segment-2 non-prefetchable memory CPU
  base `0x1200110000` and segment-4 `0x12C0110000` (translation base
  `0x1200000000` plus the per-segment PCI minimum).

The local host harness checks all 256 root devfns on each viewport
controller and models the two PHY status registers independently at
`0x82d00004` and `0x82b00004`. Applying the spec's patch sequence to
the local EL10-284 source RPM produced a driver byte-identical to the
repository copy (SHA-256 `e37411053bca3d4545041e1a2d2b7f6efc2aed77c9ead01e003b7eb842a6a7a8`).
A host sweep of its extracted map/init functions checked all 130,560
downstream BDF selections across both segments with zero mismatches.
Hardware qualification is pending.

**Nov 24 boot evidence.** The operator's serial capture shows two kernels.
The dbg1 GPIO control mounted NVMe root, reached login and rebooted cleanly.
The 284.acpidebug.1 kernel built at 01:59:28 UTC matched both viewport
quirks, enumerated 0002:01:00.0 [10ec:8127] and 0004:01:00.0 [10ec:b852],
and assigned their BARs. Endpoint driver binding, I/O, EC registration and
boot to userspace remain open for this candidate. The trace establishes
the enumeration milestone for the booted binary. Its file digest is unknown.

At 2.033 s the candidate faulted at address 0x2b0 in devm_kmalloc+0x16,
called from cros_ec_register+0x8c and cros_ec_espi_probe+0x208.
All three addresses match the local 3k kernel-core System.map after the
reported relocation. The transport's backported allocator returns a
zeroed EC with no owning device; the 284 core uses ec_dev->dev for its
first managed input buffer allocation. The next discriminating change
is to initialize that pointer and retain the existing buffer sizes. Check
EC registration, then PWM/fan binding, on a separately identified boot.

**Build and boot records.** In the proposed launcher, `pgrep -f` searches command lines. The unquoted heredoc expands `$$` in the shell writing the script, and `grep -qv` applies a substring filter to the PIDs. The loop can proceed after a failed 3c. Its cleanup then removes 3c's RPMS and build tree, and its final RPM count can return success after rpmbuild failed.

Wait for the exact 3c job's completion receipt and archive its log, effective config, input SRPM and output RPM hashes before using its result as the UART-fix control. Give 3d a fresh RPM topdir and result directory, a separate mock root if using mock, and its own log. Set Kconfig in the new input tree and check the effective `.config` after `olddefconfig`. Capture the rpmbuild exit status immediately, publish it with the cycle ID and artifact hashes via a same-directory atomic rename, and exit with that status. If logging through a pipeline, also check the log writer's exit status. Count and inspect only RPMs produced by the successful job.

For 3d, verify the applied spec and sources, resolved Kconfig, both linked rows and ops in the packaged kernel before deployment. Record the kernel build ID, selected kernel, modules and initramfs hashes, serial banner, command line and running build identity. On rhct13 ACPI, require a matched root and usable viewport on each segment, one expected Linux endpoint (`10ec:8127` on 2 and `10ec:b852` on 4), then driver bind and I/O for each. Preserve segment-0 NVMe as a regression control. Its generic compatibility has the independent gate above. [Existing firmware and endpoint evidence](rhct12-firmware-acpi-audit-2026-11-22.md)
