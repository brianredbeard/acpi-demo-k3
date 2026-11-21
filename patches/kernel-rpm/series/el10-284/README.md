# el10-284 series (generated, regeneratable)

The build artifacts for 6.12.0-284.acpidebug.1.el10:

- kernel.spec — the modified distro spec (buildid
  .acpidebug.1, Patch900002/3 for our patches, changelog,
  with_configchecks 0)
- config-acpidebug — GPIO_SPACEMIT_K1=y (the EC first-probe
  fix), first line `# riscv`, version cruft stripped
- k3-ufs-acpi.patch — the payload spliced onto the BSP
  driver (175 lines, modification not new-file)
- k3-gpio-acpi.patch — the GPIO ACPI mode (the flat-pin
  chip, probe branch; note: the 284 driver already has
  IRQCHIP_IMMUTABLE and the BGPIOF rename — our patch
  carries only the ACPI additions)

SRPM: rpmbuild -bs with kernel.spec from ~/rpmbuild/SPECS,
SOURCES = the distro SRPM contents + these files.
Mock: mock -r rhel-10.3-riscv64 rebuild <srpm>.
