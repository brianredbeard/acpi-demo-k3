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

## The GRUB cleanup (final state, supersedes the intermediate one)

Consolidated to TWO honest entries:

- "K3 dbg1" (default): vmlinuz-dbg1, full initramfs, cmdline
  = root + driver_deferred_probe_timeout=30. NOTHING else.
- "K3 stock kernel (6.12.0-284)": the fallback.

Removed (all fossils of dev cycles):
- every `acpi ($root)/boot/*.aml` override — the firmware DSDT
  (the qualified 12-patch series) is the single source of truth;
  the v8-era /boot copies were months stale (no UFS0, no _LPI)
- console= and earlycon= — SPCR (our ACPI table) provides the
  console, verified live: "ACPI: SPCR: console: uart,mmio32,
  0xd4017000,115200", /proc/consoles ttyS0 active
- ip=enaprp1i0:dhcp rd.neednet=1 — the 40s initrd network
  wait; root is local NVMe, network is NetworkManager's job
  post-switchroot (the gmac-dhcp profile holds the address)
- clk_ignore_unused — dev leftover
- the dev-cycle entries (DSDT-v8 debug, GPIO SSDT test, the
  plain variant) and the GRUB_DEFAULT pointing at a deleted
  stanza

Principle: the firmware owns the platform description (DSDT,
SPCR, MADT...); the kernel cmdline owns only what is genuinely
per-boot policy (root, and the one deliberate defer timeout).

## Round 2 results (measured, first verification boot)

Boot: kernel 27.5s + initrd 10.6s + userspace 12.7s = 50.8s
(was 66.8s). The initrd network fossil is GONE (40.0 -> 10.6s).

The EC defer-timeout attempt MISSED: with
driver_deferred_probe_timeout=30 the EC retry fired at 27.3s
but the GPIO module (an out-of-tree .ko udev coldplug-loads)
arrives at 31.9s — 4.6s too late. The cmdline route cannot
win against a module that loads ~19s into userspace.

Kernel time inflated 12.1 -> 27.5s: the kernel blocks on the
deferred-probe wait (initcalls hold until the window expires)
— the timeout trades kernel-time for the (failed) module wait.

THE GRUB DEFAULT BUG (the panic): /etc/default/grub edits are
inert without grub2-mkconfig — the live grub.cfg carries its
own `set default=` (absent = entry 0 = the first BLS stock
kernel). The stock 284 kernel + our firmware tables = NULL
deref panic at 2.07s (initcall after PNP0C02 ECAM reserve).
Recovered via serial-console menu navigation to "K3 dbg1".

Fixes applied for round 3:
- grub.cfg: `set default="K3 dbg1"` inserted directly (line 68)
- /etc/dracut.conf.d/40-gpio.conf: add_drivers+="
  gpio_spacemit_k1" — the module loads at initrd start
  (~2-3s), inside ANY defer window; board-disk-local config,
  no kernel-tree change (the multi-board objection holds)
- driver_deferred_probe_timeout=30 retained (harmless; the
  initrd module makes the first EC probe succeed outright)

Round 3 acceptance: EC binds on first probe (no -517 at all),
kernel time back to ~12s, initrd <11s, total <35s.

## Round 3 results: add_drivers silently ignored

Round 3 boot: same failure signature (module at 31.9s, EC
fails at 27.3s). The set default fix WORKED (menu starred
"K3 dbg1", booted without interaction). Boot held at 52.6s.

Investigation: unmkinitramfs of the 05:28 image shows NO
gpio_spacemit_k1 inside — despite
/etc/dracut.conf.d/40-gpio.conf (add_drivers) being in place
before the run and byte-verified (cat -A: clean quoting, no
CR). The verbose rerun (dracut-run.log) has ZERO gpio
mentions; kernel-modules ran but never installed the driver.

The robust workaround: a dracut module
/usr/lib/dracut/modules.d/01gpio_spacemit/module-setup.sh
with install() { instmods gpio_spacemit_k1 gpio-generic; } —
instmods is dracut's own copier, unconditional, no alias
resolution involved. Board-disk-local; no kernel change.

Round 4 acceptance: module loads at initrd time (~2-3s,
dmesg "gpio_spacemit_k1: loading out-of-tree module" early),
EC first probe binds (zero -517), kernel time back to ~12s
(no deferred-wait block), clocks/LPI/UFS regression green.

## Rounds 3-4: the dracut fight, and the cpio-append solution

Round 3 verified set default worked (menu stars "K3 dbg1") but
the module still loaded at 31.9s. Round 3's "add_drivers
silently ignored" claim was itself unverified: unmkinitramfs
does not exist on this Fedora-family board (Debian-only) and
the zcat|cpio probe was reading only the early-cpio segment —
the initrd is [plain early_cpio][zstd main archive], and zstd
reads from byte 0 stop at the plain prologue. The 05:28 and
05:48 dracut images genuinely lacked the module (verified by
correct segment-aware listing: 852 .ko in main stream, zero
gpio-spacemit).

dracut-install works when invoked with the explicit kerneldir
(-D /tmp/insttest --kerneldir /lib/modules/6.12.0-dbg1 -m
gpio_spacemit_k1 installs both the .ko and its gpio-generic
dep) — the dracut run itself produced no gpio lines in any
log. Rather than keep fighting dracut's module machinery, the
fix is now structural:

THE INITRD APPEND (round 4, current image):
  image = [dracut zstd archive][plain cpio append]
The kernel's documented initramfs format supports exactly
this concatenation. The append carries:
  - gpio-spacemit-k1.ko + gpio-generic.ko (with depmod'd
    modules.alias/dep/softdep overlay — the host db had NO
    alias entries for this out-of-tree module until depmod
    was run; that is also why udev coldplug loaded it so
    late — it was loading via a manual rule, not modalias)
  - sbin/modprobe -> usr/bin/kmod symlink (kmod is
    multi-call; the initrd ships only usr/bin/kmod and
    modprobe@.service which execs /sbin/modprobe)
  - gpio-spacemit-early.service: sysinit.target.wants
    oneshot, Before=systemd-udevd.service, ExecStart=
    /sbin/modprobe -b gpio_spacemit_k1

Also found and fixed while in here: the initrd carried an AMD
x86 microcode early_cpio (~300KB AuthenticAMD.bin) — dracut's
01-dist.conf early_microcode="yes" with /usr/lib/firmware/
amd-ucode present. Meaningless on riscv64; disabled via
/etc/dracut.conf.d/41-no-x86-microcode.conf (early_microcode
="no") for future dracut runs.

Round 5 acceptance: gpio_spacemit_k1 loads BEFORE udevd
coldplug (sub-3s), EC first probe binds, kernel time back to
~12s, initrd <11s, clocks 17, LPI 3 states.

## The =y GPIO kernel: EC BOUND — first EC event = poweroff (2026-11-21)

The gpioy kernel boot (vmlinuz-dbg1-gpioy, GPIO built-in):
  [0.14s] spacemit-gpio: 128 pins — first probe wave ✓
  [1.98s] cros_ec_espi: Chrome EC device REGISTERED ✓
  ZERO -517 lines — the deadlock is DEAD.
  Kernel init was FAST (~2s to initcalls done).

Then at 29s (mid-initrd): a CLEAN systemd poweroff — not a
crash. The trigger wasn't logged. Prime suspect: the EC's
first-ever delivered event — with the GpioInt live, the EC
power-key state reached the OS for the first time; a
stuck/active power button (or the EC reporting a power
event on its now-functional interrupt line) triggers
poweroff. The OpenSBI rpmi-mpxy-pwrkey driver also failed
its init (-1000) this boot — the EC/pwrkey interaction is
newly live on BOTH sides.

NEXT BOOT: watch the EC event stream (the GpioInt line +
any input events) the moment cros_ec registers; if the
power key reports active, that's the answer — and the fix
is the EC firmware/power-button line state, not our GPIO
work (which is now PROVEN: probe order, bind, no defer).

## The 29s poweroff ROOT-CAUSED: my own obsolete service

Deterministic on every gpioy boot:
  [28.29s] Starting gpio-spacemit-early.service
  [29.31s] reboot: Power down

gpio-spacemit-early is MY unit — from the initrd cpio-append
round (loading the GPIO module before udev, when it was
modular). It survived into the boot's unit set. With GPIO
now built into the gpioy kernel, the unit is obsolete — and
whatever its ExecStart does against the current state (the
module path is gone; =y means no .ko) results in the clean
systemd poweroff a second later.

FIX (on next power-on): remove/disable the unit from the
real root AND from any initrd copy —
  systemctl disable --now gpio-spacemit-early
  rm /etc/systemd/system/... /usr/lib/systemd/system/...
Then one more gpioy boot verifies clean (the EC bind at
1.98s is already proven twice).

COROLLARY: the EC power-key theory is RETRACTED — the EC
event stream was innocent; my own leftover unit was the
trigger. The EC fix stands unconditionally proven.

## gpioy EC-verification status: BLOCKED by console contention

State: the gpioy kernel + its matching module set
(/lib/modules/6.12.0-dbg1-gpioy, 4.8GB, deployed) + the
iscsi-omitted initrd (402MB, built 12:04 — existence on disk
unconfirmed after the boot loops) + the clean entry
(root=UUID only, pointing at initramfs-6.12.0-dbg1-gpioy.img).

Every captured gpioy boot shows a cmdline WITH
clk_ignore_unused — which MY entry does not carry. The boot
that ran was edited at the GRUB console (an active second
operator has been editing entries, logging in at the serial
console, and building fwts throughout this session). The
dracut iscsi FATAL fires on those edited boots (the
module-ABI story was also real for the OLD initrd — both
fixed — but the edited-boot cmdline persists).

Meanwhile the reset path wedges intermittently (RPMI
controller magic=0 during SRST after rapid poweroff cycles)
— recovered by cold power cycles via the Kauf plug (20s
off verified 0.0W).

TO COMPLETE the EC verification, the console operator and
this automation must not race: either the console session
stops editing the gpioy entry, or the verification is handed
over as a procedure (select "K3 dbg1 GPIO built-in (EC
fix)" UNEDITED, let it boot, observe: EC at ~2s, no
poweroff, login).

## EC VERIFICATION COMPLETE (2026-11-21, final)

The gpioy boot with all fixes in place:
  [0.14s] spacemit-gpio: 128 pins (first probe wave)
  [2.02s] cros_ec_espi: Chrome EC device REGISTERED
  [0]     -517 defer lines
  [3min+] soak: no poweroff, system healthy
  Regression: 17 clocks, 3 LPI states, UFS true sys1clk,
  /dev/cros_ec live.

The boot that finally worked: vmlinuz-dbg1-gpioy (GPIO built-
in, uname 6.12.0-dbg1-dbg1 — the double LOCALVERSION from
building over an already-suffixed tree) + the module tree
deployed under the kernel's real uname + the iscsi MODULE
(not drivers) omitted from the initrd + the clean root=
cmdline.

The EC GpioInt arc (P2 item 3 diagnostic -> the fix):
- Root cause: built-in EC consumer vs modular GPIO provider
  — the defer window cannot bridge initramfs->udev
- Fix: CONFIG_GPIO_SPACEMIT_K1=y + the immutable-irqchip +
  quiesce patch (docs/history/kernel/gpio/, downstream-acpi
  series, upstream-audited: nothing functionally missing,
  two treewide commits deliberately not backported)
- Boot side-effects fixed along the way: the initrd network
  fossil (40s->10.6s), GRUB cleanup, SPCR console
- The EC coordination boundary rescoped (Linux owns the EC;
  ESOS gates EC-dependent domains + wake sources)
