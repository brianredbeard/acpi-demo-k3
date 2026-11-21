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
