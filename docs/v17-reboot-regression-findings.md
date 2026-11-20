# v17 reboot hang — root cause and rollback decision (2026-11-20)

## Symptom

`reboot` on v17: systemd shutdown completes cleanly, kernel restarts,
OpenSBI SRST trace shows the RPMI reset message posted and CONSUMED
(queue head advances 10->11 within 10ms), but no reset occurs; the
controller block reads magic=0 version=0; OpenSBI falls back to
sbi_exit and parks. No "k3 sysreset:" diagnostic ever prints —
the ESOS sysreset callback never executed.

## Root cause: provenance, not P1

The v12-qualified ESOS firmware embeds version id
"os0_rcpu:deab75ceda21" — built from a git tree at commit
deab75ceda21 which no longer exists in any local checkout. The v17
ESOS was rebuilt from the reset-handoff tree (HEAD e0b8d955b,
stamps "os0_rcpu:e35ee0d27c2b") + the reset-handoff patch series +
P1. That is a DIFFERENT source baseline than the firmware that ran
v12-v16 without a reboot issue.

The P1 code itself is exonerated by construction: the M2 ISR hooks
and k3_domain_init are non-blocking, and the dormant-gate analysis
(v17 cycle) showed nothing in the AP path reaches them. But the
baseline rebuild invalidates the "one variable per flash" rule for
the v17 cycle: the flash changed the entire ESOS firmware, not
just the P1 delta.

## Decision

Roll the ESOS region back to the byte-identical v12 image
(sha256 37533b27df727921...) for the v18 (_LPI restoration) cycle.
The _LPI change is EDK2-only; pairing it with a qualified ESOS
restores one-variable discipline. The P1 model stays tracked
(patches/esos/p1/) with its host test suite; re-flashing it is
deferred until the v12 ESOS build tree is reconstructed (find or
recreate commit deab75ceda21) so the delta is genuinely just P1.

## Recovery

Board was power-cycled into BootROM/FDL mode (console shows the
USB enumeration traffic); flash from there.
