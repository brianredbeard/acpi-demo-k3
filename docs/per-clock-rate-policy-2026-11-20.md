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

## Patch walk results (2026-11-21): 0005 is the clock-service killer

Walk step 1 (v12-proven 0001-0004 + 0005 only, via build_esos.py,
one variable): the RPMI transport dies at boot (shmem-mbox -12,
MPXY unavailable, empty Linux clock tree, deny probe never
reaches firmware). IDENTICAL signature to every v20+ failure.

CONCLUSION: patch 0005 (the CCU transposed-field fix) is the
patch that has broken the clock service — and the whole RPMI
transport — since v20. It was never hardware-verified before
landing in the v20 manifest (the v20 cycle checked deny+UFS,
both of which pass without the clock service, and never the
clock tree).

Static analysis so far: the macro swap (axi_clk from
DIV_FC_MUX_GATE to the gate-less DIV_FC_MUX) and the field
swaps compile cleanly and are structurally sound on host mocks
(the initializer repro shows identical shape, NULL-gate handled
by the framework's 'if (!gate)' guards). The kill is in the
RUNTIME init walk of the changed tables — root cause not yet
identified; reproducing the CCU init walk on the host (mocked
framework, real tables) is the identified test gap.

THE TEST GAP (the reason this shipped broken): the host harness
covers the service callbacks, the ownership model, and the build
— nothing executes the CCU driver init against the patched clock
tables. That is the exact layer 0005 changed.

## Verified-on-hardware state after the walk (the honest P1/P2 ledger)

P0 (all hardware-qualified, live on the v26 recovery image):
- OpenSBI explicit dispatch, genuine type-0 WFI, error
  propagation, rejection semantics — v16 cycle
- _LPI (WFI + SBI_WFI states) — v18 cycle
- UFS with true sys1clk (clocks resolve: zero fallback
  warnings) + the RPMI clock service itself (0001-0004) — v12
  composition, re-verified on v26

P1 (host-qualified; NOT in the flashed firmware):
- The ownership model + sequencer + policy (patches 0007
  content + the policy): 64-assertion locked-source suite
- The RPMI-routed gate (OpenSBI 0x11000000 routing): hardware-
  exercised in the v21-v23 cycles but only alongside the broken
  0005; re-qualification requires the 0005 fix first
- Patches 0005/0006: NOT hardware-verified; 0005 kills the boot

P2: unstarted (device-domain ops, CPPC backend, EC coordination,
system suspend) — all blocked on the P1 re-landing.

RECOVERY: the board runs v26 (v12 vendor-equivalent ESOS with
patches 0001-0004 + v21g OpenSBI + v19 EDK2) — clocks at truth
rates, full regression green, reboot clean.

## Walk step A result + the string-table revelation (2026-11-21)

Step A (the v12-era-COMMITTED 3-patch series through today's
reproducible flow): DEAD clock service. The committed 6f1bb7e
patches were never the working content.

THE STRING-TABLE REVELATION: the SHIPPED v12 binary contains
'rpmi-clk: CCU clock '%s' not found (id %d)' — a print that
exists ONLY in the d032c00-revised patch 0003. The shipped v12
already carried the d032c00 framework revision (the 'audited
field fixes' in its qualification note). Therefore:

- The framework revision is NOT the killer (v12 shipped with it)
- No post-d032c00 commits touched 0002/0003 — the current series
  0001-0006 IS the d032c00 state
- walk5 (died) = d032c00 series MINUS 0006; v20 (died) = the full
  series PLUS 0007

STEP B (frwk2 = 0001-0006, the closest reconstruction of the
shipped v12) discriminates the two remaining hypotheses:
- BOOTS -> 0006 is REQUIRED alongside 0005 (the 0003 init-time
  name lookup uses hw->init->name which is NULL after
  registration — 0006 fixes exactly that; without it the
  resolve-at-init fails and the service publishes dead clocks),
  AND the v20 killer is patch 0007 (P1) independently
- DIES -> the series is broken beyond 0006; diff frwk2 against
  the shipped v12 binary for the remaining amendments

## Walk step B result (2026-11-21): frwk2 dies; the failure is BUILD LAYOUT, not patch content

Step B (frwk2 = 0001-0006 current series, the closest
reconstruction of the shipped v12): DEAD clock service, same
signature. The cros_ec_espi -517 errors the user observed are a
downstream deferred-probe cascade of the dead MPXY chain, not an
independent defect.

The binary comparison of frwk2 vs the SHIPPED v12 settles the
mechanism:
- identical total size (267264) and .data size
- .text differs by 16 bytes; string tables IDENTICAL except the
  version stamps
- ~37,924 differing bytes in ~8,888 scattered regions — the
  classic signature of LINK-ORDER/layout differences (same code,
  different addresses), not content differences

CONCLUSION: the shipped v12 cannot be rebuilt reproducibly from
ANY committed source state (6f1bb7e, d032c00, current). Its
working behavior depends on build-artifact layout (link/init
ordering), and the boot has an init-order sensitivity that makes
equivalent-but-differently-laid-out firmware DIE before the RPMI
transport comes up.

This is a build-reproducibility defect at the ESOS layer:
- every "same content" rebuild produces a different layout
- the difference is fatal (dead transport)
- the shipped v12 binary is the only known-good artifact

The v24 arc's entire failure cascade traces here: v20 was the
first rebuilt-from-source ESOS flash; the layout lottery killed
its transport; every subsequent content-bisect was chasing noise.

OPTIONS (user decision required):
A. Root-cause the init-order sensitivity (find which driver
   ordering matters, make it explicit) — the thorough path
B. Treat the shipped v12 FIT payload as the pinned ESOS base
   artifact (like the OpenSBI pin) and re-land P1 via surgical
   binary patches — the pragmatic path, weakens source-truth
C. Reproduce the v12 build's link order (find the scons/env
   difference that orders objects differently and pin it) —
   the reproducibility fix, unknown difficulty
