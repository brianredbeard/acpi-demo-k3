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
