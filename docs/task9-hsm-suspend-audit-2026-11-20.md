# Task 9 prerequisite: HSM suspend audit — 2026-11-20

Source audit of the suspend chain in the SHIPPED firmware stack (no hardware
runs; the OpenSBI binary in the pico-acpi-v11 bundle is the qualified artifact).
Answers: what suspend states exist, what they actually do, and what `_LPI` may
truthfully encode.

## The chain (as shipped)

```
Linux (ACPI: needs _LPI; DT: uses /cpus idle-states)
  -> SBI HSM hart_suspend (SBI_EXT_HSM_HART_SUSPEND)
     -> OpenSBI sbi_hsm_hart_suspend (sbi_hsm.c)
        -> hsm_device->hart_suspend = rpmi_hsm_suspend (fdt_hsm_rpmi.c)
           -> CONFIG_PLATFORM_SPACEMIT_K3: __rpmi_hsm_suspend (k3_corepm.c)
```

OpenSBI registers `rpmi-hsm` as the HSM device when the boot FDT carries the
`rpmi-mpxy-hsm` node (channel 5 — present in the shipped agent/uboot FDT).
Without the node, `sbi_hsm_hart_suspend` falls back to plain `wfi()` for the
two DEFAULT suspend types only.

## Suspend states that exist

From the shipped rcpu0-dtb-pico (image 19 of the ESOS FIT), parsed by the ESOS
RPMI HSM service (`spacemit-hsm.c` reads `riscv,idle-state` children):

| DT node | sbi-suspend-param | entry/exit/residency (us) | class |
|---|---|---|---|
| cpu-nonretentive@15 | `0x90000000` | 250 / 500 / 950 | non-retentive, platform (`NON_RET_BIT \| PLAT_BASE`) |
| cluster-nonretentive@16 | `0x91000000` | 600 / 1100 / 2700 (+wakeup 1500) | non-retentive cluster |
| home-screen@17 | `0x92000000` | 600 / 1100 / 2700 | non-retentive home-screen |

All three are **non-retentive-class platform types**. There is no retentive
platform state: the DT advertises none, and the OpenSBI K3 path treats
`0x90000000` as CPU power-down and everything else as cluster power-down.

## What the K3 implementation actually does (k3_corepm.c `__rpmi_hsm_suspend`)

1. Masks interrupts; aborts early if any S- or M-mode IMSIC interrupt is
   pending (sets `imsic->flags` so resume skips restore — correct).
2. Saves the full IMSIC state: M-mode (eithreshold/eidelivery/eie[]), S-mode
   (same), and for harts < 8 (X100/A100-class with hypervisor) the whole
   H-extension set plus per-VGEN VS-mode files.
3. Votes power-down: `spacemit_vote_powrdown_core()` for type `0x90000000`,
   `spacemit_vote_powrdown_cluster()` otherwise. (Harts 8/12/1/4 always vote
   core-down — they arbitrate cluster state for C2/C3.)
4. Disables prefetch, flushes D-cache, disables D-cache, clears the core's
   L2 snoop bit.
5. `wfi()`. On wake: restores the snoop bit, re-enables D-cache, unmasks IRQs.
   Returns to the caller in-place (retentive-style resume even though the
   state is advertised non-retentive — the PMU may or may not have actually
   powered the domain down; the vote is a request, PMU arbitrates).

`__rpmi_hsm_resume()` (restores IMSIC CSRs) is wired as the HSM device's
`.hart_resume` — that callback runs on hart START (cpu_up), not on suspend
wake, so IMSIC state after a suspend+wake is restored only via the in-band
path above. The power-down vote is never devoted in the suspend path; votes
are cleared in the M2-exit/ESOS coordination path (`spacemit_k3.c`) — i.e.,
the vote model assumes the rcpu participates in cluster transitions
(`AP_Cx_M2_ENTER/EXIT` interrupts, `spacemit_cx_m2_enter_wait`).

## What this means for `_LPI` (Task 9)

1. **Only non-retentive platform states exist.** ACPI 6.6 `_LPI` entries
   would encode, per the FFH spec, `Address = (1ULL << 60) | suspend_type`,
   i.e. `0x1000000090000000`, `0x1000000091000000`, `0x1000000092000000`
   (bits [63:60]=1 SBI, [59:32]=0, [31:0]=the param). Linux
   `drivers/acpi/riscv/cpuidle.c` validates exactly this and calls
   `riscv_sbi_hart_suspend` with the low 32 bits.
2. **No retentive state = no shallow state to expose.** The plan's guidance
   ("if only WFI is proven, retain architectural idle") applies in a new
   form: the deepest thing Linux can do without a vote is WFI. A two-state
   `_LPI` (WFI + cpu-nonretentive) is not truthful — WFI needs no `_LPI`
   entry; architectural idle already does it. So `_LPI` should expose ONLY
   the three (or a qualified subset of the) platform non-retentive states.
3. **Latency/residency numbers exist** (DT) but are vendor values, not
   measured on this board. The plan requires measured values; treat the DT
   numbers as initial placeholders and measure before freezing.
4. **Single-state validation quirk**: the plan noted the kernel rejects
   one-state `_LPI` configurations ("backend rejects one-state
   configurations" — `pr->power.count <= 1` returns -ENODEV in
   `acpi_cpu_init_idle`). Exposing all three advertised states avoids it.
5. **Wake dependence**: resume correctness depends on IMSIC state surviving
   and the M2/vote coordination with the rcpu. Any `_LPI` qualification
   must test UART/IPI/NVMe wakeups and network continuity per the plan,
   and — given the vote model — verify the GMAC's RPMI/mailbox path still
   works after cluster power-down votes (the M2 coordination is an ESOS
   contract, and ESOS is on the rcpu that arbitrates it).
6. **Timer flags**: all three DT states set `local-timer-stop`. Under ACPI
   there is no per-hart clockevent replacement announced — the tick
   broadcast story (arm timer / CLINT/ACLINT broadcast) must be verified
   before enabling cluster states; CPU-level first (plan guidance).

## Recommended `_LPI` first cut (for review, not yet written)

- CPU0-7 (`ACPI0007` from Cpu.asl): `_LPI` with the cpu-nonretentive state
  only (`0x1000000090000000`), measured latencies, no cluster state.
- Cluster states and home-screen deferred until M2 coordination + timer
  broadcast are proven under ACPI boots.

## Gaps found in the audit (worth upstream/ESOS attention, not blockers)

- `__rpmi_hsm_suspend`'s comment in `__rpmi_hsm_resume` says "save h-mode"
  while restoring (stale comment only).
- The ESOS-side `k3_hsm_hart_suspend_prepare/finalize` are `return 0` /
  empty stubs: all real work is OpenSBI-side; the RPMI HSM service is a
  pass-through for suspend under `CONFIG_PLATFORM_SPACEMIT_K3`.
- `rpmi_hsm_do_fixup` injects idle states into the DT handed to the next
  stage — meaningless under ACPI (no FDT idle-states consumer). This is
  exactly why `_LPI` must come from the DSDT.
- The DT claims non-retentive but the implementation resumes in-place
  (register state kept). If the PMU actually drops power, resume would go
  through warmboot — the `SBI_HSM_STATE_SUSPENDED`->`STARTED` transition
  and `jump_warmboot` path cover it, but only for the non-ret default.
  Treat "does the PMU actually power down" as UNMEASURED.

## Verification still required (hardware)

- `/sys/devices/system/cpu/cpu0/cpuidle/` state list and usage counts
- Wake sources after deep idle (IPI, ttyS0, NVMe IRQ, network)
- Timer behavior (local-timer-stop vs tick broadcast)
- Power measurement to confirm the votes do something
