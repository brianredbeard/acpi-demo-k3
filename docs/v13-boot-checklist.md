# v13 boot cycle — _LPI pulled; payload and verification plan

**Supersedes all earlier revisions.** `_LPI` is REMOVED from this cycle:
the deployed OpenSBI has no genuinely retentive suspend path (analysis
below). This document describes the actual payload: the v13 firmware is
v12's qualified content + patch 0011 (audit fixes, hardware-proven on v12)
+ patch 0012 reduced to the `\_SB` platform `_OSC` only.

## Firmware deltas vs the qualified v12 flash

ESOS/OpenSBI/FSBL/agent: **unchanged** from the live v12 payload. Only
edk2.bin changes (0011 + 0012-reduced). 0011 is already hardware-proven on
the v12 boot (RHCT HWCAP, truthful `_OSC`); the only NEW content flashing
is the `\_SB` platform `_OSC` method.

## Flash artifact (authoritative)

`fitimage/MUSE-Pico/MUSE-Pico.itb` — sha256
`83618f4b13a0560e7898e24c01e32c289faa4750637b0dc2c85a1a6e00600008`,
size 3248128. Built from the maintained tree (series 0001–0012 replaying
clean from the pinned baseline). ALL earlier artifact hashes are
superseded — do not flash them.

## Why _LPI was pulled (source-path evidence)

`__rpmi_hsm_suspend()` in the deployed OpenSBI (verified byte-identical to
the preserved source audit copy) treats every suspend type except
`0x90000000` as a **cluster power-down**: PMU vote + D-cache disable +
L2 snoop clear before WFI. That includes `SBI_HSM_SUSPEND_RET_DEFAULT`
(type 0) — the SBI spec's plain retentive WFI. The rpmi-hsm device never
returns `SBI_ENOTSUPP`, so the kernel's generic plain-wfi fallback is
unreachable. Therefore:

- CPU_NR (`0x90000000`): per-CPU power-down; hung the boot without the
  kernel's `arch_get_idle_state_flags` override (no tick broadcast)
- Any "SBI_WFI" (type 0): actually a cluster power-down, not a WFI

No `_LPI` state is safely expressible against this firmware.

## Verification checklist for THIS payload

1. Boot health — full RHEL, zero BUG/WARNING/ERROR; SPCR console active
2. RHCT HWCAP + truthful `_OSC` (0011; already proven on the v12 boot —
   regression check only)
3. Platform `_OSC` live: `dmesg | grep 'platform _OSC'` → `OS control
   mask [00000080]` (PCLPI confirmed; harmless without `_LPI`)
4. cpuidle: correctly ABSENT (no `_LPI` in the DSDT — verify
   `/sys/devices/system/cpu/cpu0/cpuidle` does not exist)
5. No regressions — thermal, fan, EC, EEPROM, GMAC, the 13 RPMI clock
   rates

## _LPI restoration prerequisites (tracked)

1. **OpenSBI retentive fix** — `patches/opensbi/0001-k3_corepm-retentive-
   default-suspend.patch`: type 0 as plain `wfi()` with no vote/cache/
   snoop operations. Build-verified by disassembly (`wfi; li a0,0; ret`
   early path; non-zero types unchanged). **Hardware qualification
   before _LPI returns**: (a) type 0 reaches WFI with no side effects
   (no cluster vote, caches stay on), (b) non-retentive types 0x90000000/
   0x91000000 retain their behavior, (c) timer/IPI/UART each wake the
   hart from type-0 suspend and deliver.
2. **Kernel timer-stop override** — 6.12 RISC-V lacks
   `arch_get_idle_state_flags`; a one-line override is required for
   CPU_NR's ArchFlags bit 0 to set `CPUIDLE_FLAG_TIMER_STOP`.
3. Then re-add: WFI at index 0 (the index-0 special path never suspends)
   + the qualified suspend state at index 1.

## Next work (per re-prioritization)

Task 7 (UFS consumer wiring — clock truth already live) and Task 8
display Phase 1 (firmware-GOP handoff); both independent of cpuidle.
`_LPI` revisits after the OpenSBI fix is qualified.

## Gate ledger (historical)

| # | Gate | Failure | Fix / status |
|---|---|---|---|
| 1 | `_OSC` presence | silent `-EOPNOTSUPP` | `\_SB._OSC` added; proven live |
| 2 | `_OSC` buffer | CDW3 past 8 bytes | 2-DWORD method |
| 3 | FFH encoding | `Invalid FFH LPI data` ×8 | param in low 32 bits |
| 4 | state Flags | zero flattened states | Flags=1 |
| 5 | index-0 semantics | CPU_NR never suspends | WFI at index 0 |
| 6 | **firmware suspend semantics** | type 0 = cluster power-down; CPU_NR hangs without kernel timer-stop | **_LPI pulled; OpenSBI fix staged, qualification pending** |

## OpenSBI first implementation batch (P0 items 1-3) — staged

Per the suspend-ownership plan (OpenSBI owns the hart's architectural
suspend/resume; ESOS owns shared-resource eligibility), the first batch
is implemented and build-verified, awaiting its own flash+qualification
cycle (this is a NEW OpenSBI payload — the v13 artifact above still
carries the stock OpenSBI):

| Item | Status |
|---|---|
| P0-1 explicit dispatch | type 0 → wfi; 0x80000000 → ENOTSUPP; 0x90000000 → per-CPU vote (unchanged); 0x91000000 cluster → ENOTSUPP (deferred until ESOS ownership + retained wake); anything else → EINVAL before any hardware change |
| P0-2 genuine retentive type 0 | wfi() before votes/masking/IMSIC/cache; register state intact |
| P0-3 error propagation | wrapper returns the backend result; failure diagnostic line |

Build identity: `fw_dynamic.bin` sha256
`3a75be0412661ec8695c83f1ae82815de45a8ede89437788d0535c77308cb57b`
(269920 bytes), from the local tree with
`patches/opensbi/0001-k3_corepm-retentive-default-suspend.patch`
applied. Disassembly-verified: the type-0 path is exactly `wfi; li
a0,0; ret`; both rejection paths exit before any CSR write, vote, or
cache operation; the wrapper propagates the error.

Hardware qualification criteria (the batch's acceptance):
1. type 0 reaches WFI with no side effects (no cluster vote, caches on)
2. 0x90000000 retains its behavior (regression)
3. timer / IPI / UART each wake the hart from type-0 and deliver
4. rejected types return their SBI error with no hardware change

Explicitly deferred per the plan: cluster shutdown is NOT implemented
as the next automatic step — it requires the ESOS ownership model and
retained wake mechanism (P1) first. Remaining P0 follow-ups:
non-retentive context audit, entry/abort/resume cleanup ownership,
versioned capability discovery. Supporting deliverables (retained-
counter diagnostics, fault-injection tests) are follow-up work.
