# Per-clock rate-change policy (P1 final row) — v24 (2026-11-20)

## The regression found first

Reading the live clock service before implementing the policy
exposed that patches 0002-0006 (the entire RPMI consumer-clock
service) were NEVER applied to the reset-handoff build tree used
for v21f-v23: that tree carried only 0001 (the reset-handoff
work), while the v20 build correctly used build_esos.py (all
patches). The v21f+ debug cycles hand-built from the under-patched
tree, so the live clock tree had regressed to rproc_clk only —
the UFS "regression passes" on those cycles passed on the driver's
tolerated fallback, not the clock truth. Patches applied to the
tree now; v24 restores the clocks AND delivers the policy.

## The policy (k3-os0_clk.c)

  IDMPOTENT STATE   enable-when-enabled / disable-when-disabled
                    = SUCCESS (the ufs_refclk -EALREADY root
                    cause, fixed in the service layer — the
                    driver-side workaround in ufs-spacemit can be
                    retired in a future kernel cycle)
  RATE ALLOWLIST    explicit per-clock qualification; consumer
                    clocks start LOCKED (capability is necessary
                    but not sufficient — the vendor's own comment
                    named this gap)
  SHARED PARENT     set_rate refused while any sibling published
                    clock on the same CCU parent is enabled
  BOOT SNAPSHOT     the service init records the firmware-enabled
                    set; the first Linux enable is recognized as
                    idempotent, not an unexpected state

Guard order verified in the object disassembly. Host coverage
decision: the guards are thin conditionals around framework
calls; a mocked-framework harness would test the mocks (the
audit's no-wiring-tests rule). The rules are exercised on
hardware instead (below).

## Hardware qualification (v24 flash)

[results appended after the cycle]

## The post-mortem (added 2026-11-21): the clock service has been dead since v20

The v24 debugging arc ended in the correct but humbling conclusion:
the RPMI clock service was not broken by the rate policy, the hand
builds, or the v21+ hsm wiring — it was broken from v20 onward, by
the P1 patch series itself (the first flash carrying MY ESOS
changes). Every "green" cycle from v20 to v23 verified deny + UFS,
both of which pass WITHOUT the clock service (deny needs only the
HSM path; UFS throughput does not depend on the RPMI clocks). The
clock tree was never once checked in those cycles.

Evidence chain:
- v14-v16 (v12 vendor ESOS + rebuilt OpenSBI): clocks verified
  working (ufs_aclk 491.52MHz in the v16 boot-health check)
- v20 (P1 patch via build_esos.py): deny worked (transport alive),
  UFS worked — but the clock tree was never verified. In hindsight
  it was already dead.
- v24-v25b: every build variant (patches-only, patches+model,
  patches+model+policy, v20-exact lock rebuild, hand and
  reproducible paths) showed the same signature: live transport,
  dead clock service, Linux clock tree empty, rclk device deferred
  ('SBI MPXY extension not available' — the mpxy-mbox provider
  chain breaks when the shmem clock-service group fails to serve).
- v26 RECOVERY (v12 vendor ESOS + v21g OpenSBI + v19 EDK2): the
  v14-v16 era composition — clocks return (17 entries, truth
  rates), zero UFS fallback warnings, full regression green
  (P0 -1/-2/-3/-2, type-0 0, _LPI live, UFS 673 MB/s), reboot
  clean.

## State after the recovery

- The board runs the PROVEN composition: v12 vendor ESOS, v21g
  OpenSBI (all P0 work live), v19 EDK2 (_LPI + UFS0).
- The P1 ESOS work (ownership model, sequencer, gate, policy) is
  committed in the repo (audit-fixed, 64-assertion locked-source
  suite) but NOT in the flashed firmware.
- Re-landing protocol (the only sanctioned path): one patch at a
  time, each flash verified by the CLOCK TREE first (the check
  every prior cycle skipped), then the rest of the regression.
  The clock-service registration in the P1 patch series is the
  prime suspect; the specific hunk is not yet identified.
