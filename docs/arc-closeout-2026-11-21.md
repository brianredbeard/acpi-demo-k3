# The arc, closed: the suspend-ownership plan executed (2026-11-21)

From working firmware (the v12-era stack) to working firmware
with P1 complete and P2 scoped — the full ledger against the
plan, with evidence.

## P0 — all six rows COMPLETE, hardware-qualified

1. **Explicit suspend-type dispatch** — COMPLETE (v16 cycle).
   Type 0 -> plain wfi; 0x80000000 -> EFAIL; 0x90000000 /
   0x91000000 -> ENOTSUPP; unknown -> EINVAL; cluster ->
   EINVAL. Disassembly-verified: zero CSR/PMU writes before any
   rejection. Evidence: the four rejection probes returning
   -1/-2/-3/-2 on every cycle since.

2. **Genuine default-retentive path** — COMPLETE (v16). Type 0
   executes wfi() before any vote/mask/IMSIC/cache operation.
   Timer wake 1016ms of a 1000ms deadline; IPI and UART wake
   proven per-hart; 10k soak, canary intact.

3. **Propagate backend errors** — COMPLETE (v16) + hardened
   (v21). The wrapper returns the backend result with the
   hart/type/error diagnostic; the ENOTSUPP-fallback translation
   prevents generic OpenSBI from consuming a default-type
   rejection as a warmboot-simulation request (the v14/v15 hart
   wedges, root-caused and fixed).

4. **Audit non-retentive context preservation** — COMPLETE AS A
   REJECTION DECISION (F6). The audit found the in-place resume
   contract unresolvable as shipped; ALL non-retentive types are
   rejected rather than half-implemented. The audit trail:
   docs/task9-hsm-suspend-audit, the P0-4 findings F1-F8, the
   cleanup-contract table. LIMITATION: the "with virtualization
   active" clause was never exercised (no guest image on the
   board; /dev/kvm present).

5. **Entry/abort/resume cleanup** — COMPLETE for the live state
   space. The dispatch hoist makes every rejection zero-touch;
   type-0 WFI needs no cleanup. The full cleanup machinery
   (k3_hsm_cleanup_wake + the P0-5 table) is a documented
   contract for the future non-retentive implementation.

6. **Versioned capability discovery** — COMPLETE BY
   CONSTRUCTION + PROVEN NECESSARY. _LPI advertises exactly the
   implemented states (WFI + SBI_WFI + SBI_CRET, each
   qualified before advertisement); the 0x11000000 dtb state was
   added only after the gate worked, and the kernel's LPI
   validation rejecting a bad FFH encoding proved the
   enforcement works end to end. No formal version interface
   was built (the plan's "where suitable").

## P1 — all eight rows COMPLETE, hardware-qualified on the
## repaired pipeline

7. **Explicit resource ownership** — COMPLETE (0007+audit fix).
   Per-class consumer refcounts; unknown ownership = blocker;
   domains start BLOCKED until qualified; the first provider
   (X100_AP) wired: Linux running holds its clusters — the
   gate's denials are for the CORRECT reason. 64-assertion
   locked-source suite.

8. **Shared-domain state machine** — COMPLETE.
   active/entering/committed/entering-wait/asleep/restoring/
   aborted with single-owner transitions; the late-consumer race
   the audit reproduced is closed (atomic invalidation +
   commit-gate recheck).

9. **Transactional power votes** — COMPLETE. Generation-guarded
   requests; stale/duplicate rejections; cancellation and wake
   cleanup. Host-tested at every step.

10. **Quiescence enforcement** — COMPLETE. ENTERING_WAIT denies
    new prepares (enforced by the state machine itself).

11. **Retained wake mechanism** — COMPLETE for the qualified
    state space. Timer/IPI/UART retention proven for type 0;
    the M2 enter/exit ISRs hooked with retained counters.
    Deadline transfer: correctly not implemented (retained-HW
    support unverified).

12. **Qualified domain sequencing** — COMPLETE.
    commit_sleep: QUIESCE -> ENABLE -> bounded WAIT -> ASLEEP,
    abort at every step, reversible at documented failure
    points. Hardware-verified through the full offline ->
    sequenced entry -> online cycle (the power evidence).

13. **Bounded management transactions** — COMPLETE. The ESOS
    wait bounded under the 20ms mailbox RX window (the v21
    hart-0 timeout, root-caused); the rcpu monitor is
    independent of Linux scheduling; every failure returns a
    safe error.

14. **Runtime clock ownership** — COMPLETE (0008). Idempotent
    enable/disable (the ufs_refclk -EALREADY root cause, fixed
    in the service layer); the boot snapshot reconciles
    firmware-enabled clocks with Linux acquisition.

15. **Per-clock rate-change policy** — COMPLETE (0008). The
    allowlist (capability necessary-not-sufficient; consumer
    clocks LOCKED), the shared-parent busy check, the boot
    snapshot. The RPROC-stub crash the host harness caught
    before hardware.

## P2 — scoped, not started (the honest state)

16. Device-domain power ops — scoped (the P1 model is the
    coordination primitive; needs per-device descriptors +
    RPMI DEVICE wiring).
17. Performance-control backend — scoped (the allowlist extends
    to it; _CPC already in the DSDT).
18. Laptop EC coordination — scoped (the cros_ec -517 defer is
    a DSDT/GPIO ordering question; cheap diagnostic first).
19. System suspend — scoped (the vendor syssusp path exists
    unqualified; the P1 sequencer is its missing layer).

## The measured outcome

Wall-power evidence (docs/power-evidence-2026-11-21.md):
offlining cluster 1 saves a measured 2.09 W (11.1% of the
board's idle draw, sd 0.06 W) through the full coordinated
stack — kernel cpuhp -> ESOS monitor -> P1 provider ->
sequencer — with the restore path returning to baseline and
zero adverse effects across every cycle.

## The process ledger (what the arc cost and taught)

- The v20-v26 failure cascade: one regenerated device tree.
  The diagnostic order it forced (payload byte-diff FIRST) is
  now the AGENTS.md FIT payload rule.
- Three flash cycles wasted on unverified observation channels
  (invisible UART, live register, unmapped DRAM).
- Two abort-and-revert cycles executed cleanly under the
  user's directive (the LPI-2 console flood; the rate-limit
  fix in the next image).
- The host harness caught a real crash (RPROC stub) before
  hardware.
- Commits: every qualification, every finding, every
  falsification — the repo is the record.

## Board state at close

The lpi2q image: OpenSBI 51a9d0f9 (quiet-deny), the full ESOS
series 0001-0008 + the 0x11000000 idle state (original dtbs),
EDK2 with _LPI index-2 (corrected FFH). Three cpuidle states;
the gate driven end-to-end; 17 clocks at truth rates; UFS at
672 MB/s; display live; clean reboot; measured power benefit.
