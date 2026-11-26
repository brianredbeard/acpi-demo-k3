# Day summary — 2026-11-22

## State at end of day

### Kernel RPM (the mock rebuild) — IN FLIGHT, healthy

- SRPM `kernel-6.12.0-284.acpidebug.1.el10` on BOTH machines,
  carrying two patches, both PRE-FLIGHT COMPILE-VERIFIED
  (make <file>.o in a dead mock tree, the 30s rig):
  - k3-gpio-acpi.patch (v3): relocation of data defs above the
    ACPI block (def@315 < use@629), no macro, escape-safe.
    433 lines. Catches forever: struct layout, declaration
    order, macro capture.
  - k3-ufs-acpi.patch (v2): rebuilt for the 284 BSP driver
    shape (probe is a one-line wrapper; reset guard inside
    ufs_spacemit_init; APMU define before first use). 171
    lines. Roundtrip-verified.
- Board MOCK cycle: 20 attempts -> 4 distinct failure classes,
  all closed (ledger in docs/history/kernel/rpm/adapters/el10-284.md).
- Board chroot: ccache 4.11.3 enabled via EPEL riscv mirror
  (http://192.168.137.45/repos/epel-riscv64/), persistent
  /var/tmp/k3-ccache. Future kernel cycles warm-cache.
- Builder MOCK19: running the same SRPM (clean authoritative).
- On RPM completion (watcher bg_322): install on board -> GRUB
  entry -> boot verify (EC ~2s, uname 6.12.0-284.acpidebug.1.el10)
  -> rhct10 flash.

### Firmware — rhct10 STAGED (inspect-gated, NOT flashed)

BRS check driver + _OSC error paths + FVB VA fix + PCI-03/04.
Flash deferred: the board is the kernel builder; rebooting it
kills the build. rhct10 rides AFTER kernel verification.
Commandment-compliant: ~/bundles/pico-acpi-rhct10 inspect PASS
(2026-11-22, from persistent storage).

### Wi-Fi/10G-NIC defect — ACPI-WIFI subagent IN FLIGHT (~30%)

Root cause established (user investigation): ACPI describes 1
of 3 active PCIe host bridges (seg 0 only). Segments 2 (10G
NIC 10ec:8127) and 4 (RTL8852BE 10ec:b852) absent from DSDT +
MCFG. rfkill-gpio blocker identified (pin 35 low, no driver,
CONFIG_RFKILL_GPIO unset in every config incl. ours).
Subagent: DSDT seg 2+4 devices, MCFG entries, rfkill GPIO
nodes, kernel next-cycle patches, rhct11 bundle. Not flashed.

### Bundles persistent

All staged bundles + the SRPM live in ~/bundles/ (tmpfs-proof,
inspect-gated from there). /tmp copies remain volatile.

## What the day actually delivered

1. The mock recipe is DONE as engineering artifact: tracked
   payload/adapters/series, 20-cycle post-mortem ledger, the
   iteration-latency rig (30s preflight, module subsets,
   short-circuit, persistent ccache). The next kernel cycle
   on this repo costs minutes of human time, not hours.
2. Both K3 kernel patches compile-verified for the first time
   against the REAL 284 distro driver shapes (they were written
   against older revisions — the root cause of cycles 15-20).
3. Wi-Fi defect root-caused and fix designed.
4. rhct10 + rhct11 staged and gated.

## Open at end of day

- RPM completion + boot verify + rhct10 flash (mechanical, all
  staged, watchers armed)
- ACPI-WIFI deliverables (subagent, in flight)
- RQTS attempt 2, syssusp, PCI-01 kernel-side (designs ready)
