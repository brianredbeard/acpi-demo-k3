# el10-284 series (generated, regeneratable)

The build artifacts for 6.12.0-284.acpidebug.1.el10:

- kernel.spec — the modified distro spec (buildid
  .acpidebug.1, Patch900002/3/7 for our patches, changelog,
  with_configchecks 0)
- config-acpidebug — GPIO_SPACEMIT_K1=y (the EC first-probe fix),
  CONFIG_RFKILL_GPIO=y (the WLEN/BTEN rfkill-gpio devices, added for
  the rhct11-wifi cycle), first line `# riscv`, version cruft stripped
- k3-ufs-acpi.patch — the payload spliced onto the BSP
  driver (175 lines, modification not new-file)
- k3-gpio-acpi.patch — the GPIO ACPI mode (the flat-pin
  chip, probe branch; note: the 284 driver already has
  IRQCHIP_IMMUTABLE and the BGPIOF rename — our patch
  carries only the ACPI additions)
- k3-ecam-segs24.patch — Patch900007 provides segment-0 ECAM and
  segment-2/4 viewport operations. Only devfn 0 reaches each viewport
  controller's root-port DBI header. The spec applies it after GPIO.

SRPM: rpmbuild -bs with kernel.spec from ~/rpmbuild/SPECS,
SOURCES = the distro SRPM contents + these files.
Mock: mock -r rhel-10.3-riscv64 rebuild <srpm>.
