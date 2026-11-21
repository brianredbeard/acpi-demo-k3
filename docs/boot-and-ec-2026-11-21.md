# Boot-time audit + EC GpioInt fix (2026-11-21)

## The boot-time problem (measured)

systemd-analyze on the lpi2q image:
  kernel 12.1s + initrd 40.0s + userspace 14.7s = 66.8s total

THE INITRD IS 60% OF BOOT. Root cause: every GRUB entry carried
`ip=enaprp1i0:dhcp rd.neednet=1` — the initramfs waited for a
DHCP lease (on an interface name that no longer matches the
renamed enaprp1i5, compounding the delay) before mounting a
root that is LOCAL NVMe. The network wait in the initrd is a
fossil: it predates the local-root NVMe workflow.

The fix (applied to the "K3 -dbg1 ACPI FULL" entry): drop
ip=/rd.neednet from the kernel line. Network moves entirely to
NetworkManager post-switchroot (the gmac-dhcp profile on
enaprp1i5 exists and holds the current address — verified).

Expected effect: initrd drops from ~40s to single digits
(NVMe enumerate + mount); total boot roughly halves.

## The EC GpioInt fix (P2 item 3 diagnostic)

Root cause chain (dmesg):
- 1.3s: cros_ec_espi (=y, built-in) probes; asks for the
  GpioInt -> -517 EPROBE_DEFER (the GPIO controller driver
  isn't available yet)
- 12.1s, 12.2s: defer retries — still nothing
- 16.9s: udev loads gpio-spacemit-k1 (a MODULE, from the real
  root) — too late; the EC's deferral window expired

The kernel's ordering mechanism (EPROBE_DEFER) is working
correctly. The failure is a packaging mismatch: a built-in
consumer whose dependency is a module that only arrives after
udev. The kernel's default deferral window
(driver_deferred_probe_timeout) is 10s with CONFIG_MODULES —
shorter than the udev module load.

THE FIX (the distribution-correct one, per the user's
architectural point: this kernel builds for many boards, so
per-board =y is untenable): kernel cmdline
`driver_deferred_probe_timeout=30` — the kernel waits up to 30s
for modules before failing deferred probes. Board-agnostic,
kernel unchanged, one GRUB line.

Considered and rejected:
- CONFIG_GPIO_SPACEMIT_K1=y: board-specific policy in a
  multi-board kernel (the user's objection)
- GPIO module in the initrd: fragile (dracut hostonly won't
  include it; every kernel update must remember); =y and
  initrd-inclusion share the same objection
- Reboot-path check: poweroff-gpio/restart-gpio are unbound
  (this board reboots via RPMI sysreset) — no other initrd-time
  GPIO consumer exists

## The GRUB cleanup (same change)

- GRUB_DEFAULT referenced a deleted stanza ("K3 -dbg1 ACPI
  v9 (PRP0001 EEPROM + TSEN + GPIO)") — the boot fell through
  to the first entry by accident. Fixed to the actual entry:
  "K3 -dbg1 ACPI FULL (serial+PCIe+NVMe+GMAC)"
- The menu retains the historical entries (v8 DSDT overrides,
  SSDT tests) — a fossil record of the dev cycles; not deleted

## Verification (next boot)

1. Boot time: systemd-analyze — expect initrd < 10s, total
   < 35s
2. EC: dmesg — cros_ec_espi probes and BINDS (no -517), the
   GpioInt IRQ acquired; /sys/class/chromeos devices appear
3. Full regression (clocks, LPI, UFS) unchanged
