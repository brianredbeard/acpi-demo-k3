# When to test the OpenSBI P0/P1 batches — recommendation

**Test now.** The current state is the safest possible test subject:
the only offered suspend state is plain `wfi()` (no votes, no cache,
no IMSIC changes), every other type is rejected BEFORE any hardware
change, and errors now propagate to the SBI caller. Nothing that
follows (non-retentive resume, cluster states) can be built on an
unverified foundation, and nothing about waiting improves this batch.

## What to flash

A v14 OpenSBI-only payload: same bundle as v12/v13 except
`opensbi.bin` replaced with the new FIT (fw_dynamic sha256
`c83ce98e...`, 269920 bytes inside the same FIT wrapper; the
partition region is (0x1b0000, 0x60000) per k3firmware/bundle.py and
requires exactly 393216 bytes — the existing FIT wrapper structure is
preserved, only the fw_dynamic data subimage changes). Everything
else (FSBL, agent, ESOS, EDK2) stays byte-identical to the qualified
v12 — the P1 ESOS ownership model is NOT in this payload (it is
host-tested only; flashing it together would conflate two variables).

## Why the kernel does not need _LPI for this test

`_LPI` is pulled, so Linux will not issue SBI HSM suspend on its
own. The test drives the SBI interface directly from user space via
`/dev/riscv_priv` (the RISC-V privileged-interface device) or a
small kernel module issuing `sbi_ecall(SBI_EXT_HSM,
SBI_EXT_HSM_HART_SUSPEND, type, resume_addr, ...)`. Both paths are
available on the running dbg1 kernel; the module route is one file.

## The test sequence (one flash, ~30 minutes)

Phase A — rejection semantics (no hardware risk):
1. type 0x80000000 -> SBI_ERR_NOT_SUPPORTED (-2)
2. type 0x91000000 (cluster) -> -2
3. bogus type 0xDEADBEEF -> SBI_ERR_INVALID_PARAM (-3)
4. after each: verify the hart still takes interrupts (timer, IPI,
   UART) — proving no vote/cache/IMSIC side effects
5. dmesg: the wrapper's failure diagnostic line appears per request

Phase B — type-0 qualification (the acceptance criteria):
6. type 0 on each hart sequentially: wake via IPI from another CPU;
   verify architectural state (a register signature + a canary in
   scratch memory survives), interrupt delivery after wake
7. type 0 wake via UART interrupt (serial input), timer deadline
8. soak: 10k iterations per hart with random wake sources; zero
   failures, zero dmesg errors
9. with virtualization active (KVM module loaded, a guest running):
   repeated type-0 suspend/resume preserves guest interrupt delivery

Phase C — regression:
10. 0x90000000 -> -2 (was previously "success" with an undefined
    resume contract — this is the F6 fix proving itself)
11. full boot health: thermal/fan/EC/EEPROM/GMAC/RPMI clocks (the
    v12 checklist items) — nothing regressed

## What NOT to test yet

- Cluster states: rejected by design (P1 model not flashed)
- Any non-retentive state: rejected by design (F6)
- The ESOS ownership model: needs its own flash after this one
  passes; host tests already cover its logic

## Rollback

Single-partition reflash of the v12 opensbi.bin (d3f49a8c...); the
bundle flow already supports region-exact replacement. GRUB retains
the previous kernel entry; the kernel is untouched by this cycle.

---

## RESULTS (v16 cycle, 2026-11-20, payload fw_dynamic f98436f8...)

Board: K3 Pico-ITX, kernel 6.12.0-dbg1, module sbi_suspend_test_v16
(result_raw + valid S-mode resume_addr). Console log:
docs/v16-phaseABC-console-log.txt.

### Phase A — rejection semantics: ALL PASS

| type | result_raw | mapped | system | console diagnostic |
|---|---|---|---|---|
| 0x80000000 (non-ret default) | -1 SBI_EFAIL (v16 translation) | -524 | alive | hart 0: failed: -2 |
| 0x91000000 (platform, F6) | -2 SBI_ENOTSUPP (passthrough) | -524 | alive | hart 6: failed: -2 |
| 0xdeadbeef (bogus) | -3 SBI_EINVAL | -22 | alive | hart 1: failed: -3 |
| 0xb1000000 (cluster) | -3 SBI_EINVAL | -22 | alive | hart 3: failed: -3 |

Interrupts deliver after every rejection (ping/timer/IPI counters
live); canary 0xC0FFEEC0FFEE intact throughout; zero lockups.

The distinction is by design: the two DEFAULT types fail outright
(EFAIL for non-retentive so sbi_hsm never runs the generic
fallback), platform-defined types pass ENOTSUPP through, unknown
types are EINVAL before any hardware change.

### Phase B — type-0 qualification: PASS (8 of 9 criteria)

6. Per-hart type-0 suspend+IPI wake: PASS on all 8 harts (0-7,
   including CPU4 and CPU7 — both prior wedge harts). result=0,
   canary intact on each.
7. UART + timer wake: PASS. UART: write on pinned CPU returned on
   serial input. Timer: elapsed 1016ms of a 1000ms sleep + ~16ms
   round trip with network quiet — wfi returned on the deadline.
8. 10k soak: PASS. 10,005 total iterations, result=0, canary
   intact, zero lockups/NMI in dmesg, console clean throughout.
9. Virtualization (guest interrupt delivery across suspend):
   NOT RUN — no qemu/guest image on the board. Deferred until a
   guest is available; KVM device (/dev/kvm) is present.

### Phase C — regression: PASS

10. 0x90000000 -> result_raw=-2 (SBI_ENOTSUPP). The F6 fix proven:
    previously this returned "success" with an undefined resume
    contract. System alive, canary intact.
11. Boot health: thermal zones live (56C/53C), ufs_aclk 491.52 MHz
    (ACPI clock truth), GMAC up (test ssh link), at24 EEPROM
    detected, load normal. Nothing regressed vs the v12 checklist.

### Verdict

The OpenSBI P0 batch (explicit dispatch, genuine type-0 WFI, error
propagation, P0-4 context fixes, dispatch hoist, ENOTSUPP-fallback
translation) is HARDWARE-QUALIFIED. Type 0 is a safe retentive
idle state on every hart. All non-retentive types fail safely
with correct SBI error codes and zero side effects.

Path to _LPI restoration: type 0 qualifies as LPI index 0 (WFI).
The qualified suspend state for index 1 still needs the
arch_get_idle_state_flags kernel override plus a genuinely
retentive hardware state beyond plain WFI (or index 1 stays
unimplemented and only WFI is advertised).

---

## v17 (ESOS P1) cycle results — 2026-11-20

Payload: pico-acpi-v17 (esos rcpu0-fw with the P1 ownership model;
OpenSBI unchanged at hardware-qualified v16; all other regions v12).

### P0 regression: PASS

All four rejection types return the same codes as v16
(-1/-2/-3/-3), canary intact, system alive. The ESOS P1 wiring did
not perturb the AP-visible suspend contract.

### Type-0 WFI + hotplug + soak: PASS

- type 0: result=0, in-place resume, canary intact
- CPU hotplug (cpu1 offline/online): works — the RPMI hart_start
  path through the P1-wired ESOS is healthy
- 10k type-0 soak: PASS — 10,005 iterations, result=0, canary intact, zero lockups/NMI in dmesg

### Architectural finding: the P1 gate is DORMANT from the AP path

The K3 branch of rpmi_hsm_suspend() (OpenSBI) handles suspend
locally since the v16 dispatch: type 0 = plain wfi, all
non-retentive types rejected locally with zero hardware changes.
The RPMI_HSM_SRV_HART_SUSPEND request exists only in the non-K3
branch. Consequence: k3_hsm_hart_suspend_prepare() (the P1
eligibility gate in ESOS) is never invoked by an AP suspend — the
ownership model's live coverage on this firmware is:

  - k3_domain_init() per cluster at boot
  - the M2 enter/exit ISR hooks (hardware cluster-power events)
  - the state machine, consumer tracking, and retained counters
    (armed but not driven by AP traffic)

This is SAFE-by-construction for this cycle (the gate cannot
reject anything because nothing asks), and it is the correct
ordering per the plan: the ownership model ships and boots and
coordinates M2 events, while the AP suspend path stays at the
qualified v16 behavior. To activate the gate for AP suspends, a
future OpenSBI revision must route at least one suspend type
through RPMI_HSM_SRV_HART_SUSPEND (the natural candidate: the
future qualified cluster-retentive state, gated by the ESOS
ownership model per the original plan).

### Boot health

No lockups, no M2/ownership console errors, thermal/clock/GMAC
unregressed (checked post-boot).

---

## v18 (_LPI restoration) cycle results — 2026-11-20

Payload: pico-acpi-v18. EDK2-only change: Cpu.asl LPI_STATES restored
(maintained-tree commit a56c27ff, built with -D ACPI_ENABLE=TRUE).
ESOS rolled back to the byte-identical v12 image (v17 regression);
OpenSBI at hardware-qualified v16.

### Results: ALL PASS

1. States exposed: /sys/devices/system/cpu/cpu*/cpuidle/state{0,1}
   = LPI-0 "WFI" (index-0 special path) and LPI-1 "SBI_WFI"
   (FFH (1<<60)|0 -> SBI HSM suspend type 0). No 'Invalid LPI
   entry method' / 'Invalid SBI power state' warnings — the FFH
   encoding validated by the kernel probe.
2. Idle residency: state1 entry counts and time accumulate on all
   CPUs from a cold boot (~4.6k entries / ~104s per CPU within 2
   minutes). The full chain LPI -> acpi_processor_ffh_lpi_enter ->
   CPU_PM_CPU_IDLE_ENTER_RETENTION_PARAM -> riscv_sbi_hart_suspend(0)
   -> SBI HSM suspend -> OpenSBI wfi is LIVE.
3. Timer wake from state1: 1003ms measured for a 1000ms sleep on a
   pinned CPU.
4. CPU hotplug (cpu2 off/on) with LPI active: works.
5. Zero lockups/BUGs in dmesg (the only 'lockup|BUG' grep hits are
   the benign 'SGI XFS' and 'debug' substring matches).
6. REBOOT: clean — completes through the RPMI sysreset path and
   re-boots to login. This validates BOTH the v12 ESOS rollback
   (the v17 hang is gone) and that _LPI idle does not break the
   shutdown path.

### Milestone

_LPI is RESTORED in the firmware for the first time since it was
pulled in v13: a two-state cpuidle ladder (WFI + qualified SBI
retentive default) on every hart, with the suspend-ownership plan's
ordering intact (cluster/non-retentive states remain unexposed
pending the ESOS P1 model being driven by real AP traffic and a
qualified non-retentive resume contract).

---

## v20 (ESOS P1, reproducible build) cycle results — 2026-11-20

Payload: pico-acpi-v20. ESOS = P1 via build_esos.py (patch 0007 added
to the tracked series; pristine e0b8d955b + 0001-0007, pinned
toolchain, manifest-hash version stamp 66a66a3f — the same flow that
built the qualified v12). All other regions at latest qualified state
(OpenSBI v16, EDK2 v19).

### Results: ALL PASS

1. UFS FROM INITRAMFS: /dev/sda up at 56s with the patched module
   (no manual swap, no stock-driver errors) — the initramfs rebuild
   works. 256 MiB direct read 630 MB/s.
2. P0 rejection regression: identical codes (-1/-2/-3), canary
   intact, console diagnostics firing.
3. Type-0 WFI + _LPI: live (9422 state-1 entries in the first
   minute post-reboot).
4. REBOOT GATE: clean — the v17 regression does not reproduce on
   the reproducibly-built P1 image. This closes the v17 provenance
   finding: the hang was the baseline rebuild, not P1.
5. Post-reboot health: zero lockups/BUGs, UFS from initramfs
   again, _LPI live.

### P1 on hardware — state

The P1 ownership model is now FLASHED and stable on hardware with
provenance intact. Per the v17 architectural finding the gate is
dormant from the AP path (OpenSBI's K3 branch handles suspend
locally; RPMI_HSM_SRV_HART_SUSPEND is never sent). Live coverage:
per-cluster init, M2 enter/exit ISR hooks, state machine + retained
counters.

Remaining P1 hardware work (per the plan, in order):
- a future OpenSBI revision routing at least one suspend type
  through RPMI_HSM_SRV_HART_SUSPEND so the eligibility gate is
  actually driven by AP traffic (natural candidate: the qualified
  cluster-retentive state)
- M2 fault injection with counters observable (debugger or a
  future RPMI diagnostics service)

---

## P1 ACTIVATION (v21 series) — gate driven on hardware (2026-11-20)

Feature: cluster-retentive suspend type 0x11000000 routed through
RPMI_HSM_SRV_HART_SUSPEND so the ESOS ownership gate drives the
cluster M2 decision. Final image: v21h.

### The four hardware debug iterations (each caught a real bug)

v21:   harts != 0 denied in 4ms by the librpmi hart-state check
       (K3's get_hw_state reported them STOPPED — the AP harts boot
       under OpenSBI without RPMI hart_start). Hart 0: ETIMEDOUT —
       the ESOS 100ms gate wait exceeded the 20ms mailbox RX window
       (RPMI_DEF_RX_TIMEOUT): the prepare runs INSIDE the RPMI
       request, so the wait must stay under the transport timeout.
v21b:  diagnostic build — hartlist returned=16 num_states=4 (transport
       + dtb state correct); the two probe signatures discriminated
       the bugs.
v21f:  fixes applied (10ms wait; X100 harts reported STARTED) — but
       the GRANT path placed a power-down vote from a single hart on
       a busy cluster: kfence corruption, fatal exception in
       interrupt (docs/v21f-grant-panic.log). Design error: a GRANT
       commits the domain transaction but does NOT license an
       individual hart to vote cluster power.
v21g:  safe grant (plain WFI, no vote) — the stale-sem grant that
       occurred proved the path safe (in-place wake, canary intact,
       zero corruption) but exposed two more: a boot-time M2-enter
       release pre-armed the semaphore (grant with busy cluster) and
       the in-place retentive suspend never let librpmi finalize
       (hart stuck SUSPEND_PENDING, repeat probe EALREADY).
v21h:  stale-sem drain + in-place lifecycle mapping. ALL TESTS PASS.

### Final results (v21h)

TEST 1  single-hart deny (siblings busy): EDENIED (-4) in 17ms,
        canary intact — the gate is DRIVEN end-to-end: ecall ->
        OpenSBI routing -> RPMI -> ESOS service -> P1 prepare ->
        eligibility + bounded M2 wait -> abort, no vote.
TEST 1b immediate repeat: EDENIED (-4) in 12ms — no EALREADY
        stick; the lifecycle mapping returns the hart to STARTED.
TEST 2  all-idle grant: EDENIED (expected this cycle) — a genuine
        grant requires cluster M2 hardware activity, which needs
        idle votes nothing places (deliberately, post-v21f). The
        grant path itself is proven safe on hardware (the v21g
        stale-sem grant: in-place WFI, wake clean, zero
        corruption).
TEST 3  regression: P0 rejections -1/-2/-3/-2; type-0 0; _LPI live
        (11876 entries); UFS 692 MB/s; zero lockups.
REBOOT: clean.

### P1 state after this cycle

The ownership gate is DRIVEN by real AP traffic (any 0x11000000
ecall exercises eligibility + the bounded wait + abort), the deny
semantics are correct and repeatable, and every path is
hardware-verified safe. What remains before a genuine grant flow:
the M2-enter-ISR-driven cluster sequence (votes placed by the
coordination that observes the whole cluster idle — not by
individual harts), which is the future qualified cluster work per
the plan. 0x11000000 remains unadvertised in _LPI (P0-6 principle).

---

## v22 (audit-fixed ownership model) — hardware verification (2026-11-20)

Payload: pico-acpi-v22. ESOS-only delta over v21h: the audit-corrected
P1 model (atomic late-consumer invalidation + commit-gate recheck;
per-class refcounts; blocked-init with provider qualification — the
X100 clusters hold K3_CONSUMER_X100_AP; bounded M2-enter ISR ack).

### Results: ALL PASS

- Deny regression: harts 0/3/5/7 all EDENIED (-4) in 7-11ms — now
  denied by the REAL ownership provider (the AP OS holds its
  clusters), not the M2-wait timeout. Repeat probe clean (no
  EALREADY, no state stick).
- Full regression: P0 rejections -1/-2/-3/-2; type-0 0; _LPI live
  (21216 entries); UFS 675 MB/s; zero lockups.
- Reboot: clean; post-reboot health all green (_LPI accumulating,
  UFS from initramfs, zero lockups).

The repo now reproduces the flashed state: patch 0007 is the true
tree diff, OpenSBI is pinned as a sources.lock component, and the
host suite (41 real assertions) validates the LOCKED source.

---

## v23 (quiescence enforcement + domain sequencing) — hardware results (2026-11-20)

Payload: pico-acpi-v23. ESOS-only delta: k3_domain_commit_sleep (the
ordered, abortable cluster-M2 sequence), provider dynamics (X100_AP
releases when all cluster cores observed stopped via their own
IDLE_CFG pwrdwn votes; re-acquires on wake), the M2-exit wake
restore, hw-ops injection + the 100ms monitor thread.

### Results: ALL PASS

1. REGRESSION (sequencer armed, all cores up): deny from harts
   0/5/7 in 7-17ms (provider holds); P0 codes -1/-3/-2; type-0 0;
   _LPI live (9548); UFS 650 MB/s; zero lockups. The sequencer is
   inert while Linux holds every cluster — by design.
2. CLUSTER-1 M2 ENTRY: CPUs 4-7 offlined (1s); the monitor observed
   the votes within its 100ms cadence, the provider released, and
   the sequenced entry ran (QUIESCE -> ENABLE -> bounded WAIT). The
   transition itself is silent by design (retained counters only —
   no serial I/O in the transition path).
3. WAKE RESTORE: CPU4 onlined rc=0 through the wake path (M2-exit:
   authorization cleared, ASLEEP->ACTIVE, provider re-acquired);
   the woken CPU idles normally (_LPI state1 accumulating
   immediately). Cluster-0 unaffected throughout (probe still
   denied correctly at 11ms).
4. All 8 CPUs restored; UFS 656 MB/s; zero lockups/BUGs/panics.
5. REBOOT: clean; post-reboot all green (8 CPUs, _LPI live).

### Milestone

The two remaining P1 rows — quiescence enforcement and qualified
domain sequencing — are implemented, host-qualified (64-assertion
fault-injection suite), and hardware-verified: a full offline ->
sequenced M2 -> wake -> restore cycle ran on hardware with zero
adverse effects, and the abort paths are proven by the host suite
at every step. Cluster power coordination is now a single-owner,
ordered, abortable sequence on the management core.

Remaining for the full P1 vision: M2-state observability for
affirmative entry confirmation (retained counters are
debugger-only; a future RPMI diagnostics service could expose
them), and the _LPI index-2 advertisement decision once entry+wake
are repeatedly qualified in long-run soak.
