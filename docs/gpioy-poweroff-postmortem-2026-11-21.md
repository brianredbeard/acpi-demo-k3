# The gpioy/dbg1 29-second poweroff — post-mortem

## The failure

Every Linux boot (BOTH kernels) poweroff'd cleanly at ~29s
from ~12:04 onward. Intermittent SRST wedges (RPMI queue
filling, controller magic=0) followed the poweroff-reset
loops. Four cold power cycles (Kauf plug, 20s at 0W) were
needed to recover boot attempts.

## The root cause (mine, twice over)

1. My sed pointing the gpioy GRUB entry at the gpioy initrd
   matched BOTH entries — the dbg1 entry silently received
   initramfs-6.12.0-dbg1-gpioy.img. dbg1 + gpioy-modules
   initrd = kernel/ABI mismatch.

2. Both initrds (the 10:47 dbg1 rebuild and the 12:04 gpioy
   build) omitted the iscsi DRIVERS (omit_drivers) but still
   shipped the dracut iscsi MODULE scripts. On every boot,
   parse-iscsiroot.sh runs (the module is present), its
   modprobe iscsi_tcp fails (no .ko — omitted), and dracut
   DIES: "FATAL: iscsiroot requested but kernel/initrd does
   not support iscsi" -> "Refusing to continue" -> clean
   systemd poweroff. Deterministic ~29s (dracut-cmdline
   runs at the same point every boot).

The correct directive is omit_dracut_modules+=" iscsi "
(the whole module), not omit_drivers (the .ko files only).

## The retraction chain (for the record)

Three theories preceded the truth, all wrong:
- gpio-spacemit-early service (my initrd-era unit): the
  clean-initrd boot still poweroff'd
- upower/logind power-key handling: masks changed nothing
- ESOS p2q1 patches 0009/0010 crashing the RCPU: the cppc
  create REJECTS NULL shmem cleanly and the glue checks the
  return; no crash path exists. p2q1 is exonerated.

Contributing confusion: a cumulative serial capture log
(pipe-pane appending across boots) mixed old and new boots —
the clk_ignore_unused cmdlines I attributed to a "console
operator" were earlier boots in the same log. The capture
now gets truncated per boot.

## The recovery

GRUB shell boot with the .bak-append initrd (known-good for
dbg1) restored a stable system. Then:
- dbg1 entry re-pointed at the .bak
- BOTH initrds rebuilt with -o iscsi (the module, not the
  drivers)
- the gpioy entry keeps initramfs-6.12.0-dbg1-gpioy.img

## The lessons (added to the mental AGENTS.md)

- A sed that matches N entries when you meant 1: verify the
  blast radius (grep -c the pattern first). The dbg1 entry
  damage was invisible until dbg1 itself poweroff'd.
- dracut omit_drivers vs omit_dracut_modules: omitting the
  .ko but shipping the module scripts creates a guaranteed
  FATAL. Omit the module.
- Cumulative capture logs lie. Truncate per boot, or
  timestamp-check before attributing.
- Boot regression gates must include a >60s soak: "reboot
  works" must mean stays up, not survives the first 30s.
