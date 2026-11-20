# P0-4: Non-retentive context-preservation audit — `__rpmi_hsm_suspend` / `__rpmi_hsm_resume`

Source-audited against `opensbi-controller-trace-diagnostic/platform/generic/spacemit/k3_corepm.c`
(the local tree; byte-verified against the deployed-binary source audit copy
except the two documented P0-fix deltas). Scope: the 0x90000000 (CPU
non-retentive) path — the only supported non-retentive type after the P0-1
dispatch fix. Each finding lists the **entry/abort/resume owner** per the
plan's P0-5 requirement.

## State inventory (what the path touches, in order)

| # | Operation | Type | Entry | Resume side | Preserved? |
|---|---|---|---|---|---|
| 1 | `spacemit_mask_irq(hartid)` | PMU write: `COREx_IDLE_CFG \|= CPU_MASK_FI_INTTERUPT` | bit set | `spacemit_unmask_irq` — **same bit cleared? see F1** | ✗ **F1** |
| 2 | `imsic->flags = 0` then M-mode IMSIC save (eithreshold/eidelivery/eie[]) | CSR reads into scratch | save | `__rpmi_hsm_resume` restores | ✓ (unless `flags != 0`, see F2) |
| 3 | S-mode IMSIC save | CSR reads | save | restored | ✓ |
| 4 | H-mode/VS save (harts < 8): hstatus…htimedelta + per-VGEN VS-IMSIC via `HSTATUS.VGEIN` sweep | CSR reads (with HSTATUS writes!) | save | restored — **but HSTATUS itself left at last VGEN, see F3** | ✗ **F3** |
| 5 | `spacemit_vote_powrdown_core(hartid)` | PMU write: vote bit set | set | **never cleared on the WFI wake path**, see F4 | ✗ **F4** |
| 6 | `csi_disable_data_preftch()` | CSI write | disable | **never re-enabled** — F5 | ✗ **F5** |
| 7 | `csi_flush_dcache_all()` + fences | transient | flush | — | ✓ |
| 8 | `csi_disable_cache()` | CSI write | disable | `csi_enable_cache()` ✓ | ✓ |
| 9 | `csr_clear(CSR_ML2SETUP, hart-bit)` | CSR write | clear | `csr_set(...)` ✓ | ✓ |
| 10 | `wfi()` | — | sleep | wake | — |
| 11 | *resume:* `csr_set(ML2SETUP)`, `csi_enable_cache()`, `spacemit_unmask_irq()` | — | — | restore | see F1/F5 |
| 12 | *separate hart-start path:* `__rpmi_hsm_resume()` restores IMSIC M/S/H/VS | — | — | restore | ✓ structurally; **F6: caller contract** |

## Findings

### F1 (High) — mask/unmask are not inverses: a power-down VOTE bit rides along

`spacemit_mask_irq()` sets `CPU_MASK_FI_INTTERUPT = (1<<3)|(1<<4)`. The
comment inside it says "vote core power-down & cluster power-down".
`spacemit_unmask_irq()` — if symmetric with the devote helper — clears
`CPU_MASK_FI_INTTERUPT` **plus `CPU_PWR_DOWN_VALUE (0x1f)`**. That means:

- **Entry** sets only the FI-mask bits (2 bits).
- **Resume** clears 7 bits, including the power-down vote value.

If unmask clears the vote, the vote set by step 5 is undone on wake — but
only *by accident*, through a function named "unmask irq". If any vote bits
sit outside `CPU_PWR_DOWN_VALUE|CPU_MASK_FI`, or the masks drift, the
pairing silently breaks. **Owner:** OpenSBI, both entry and resume. The
vote set and its clear must be an explicit, named pair (F4).

### F2 (Medium) — `imsic->flags` gate: pending interrupts skip the save, resume skips the restore — but entry CONTINUES

`__rpmi_hsm_suspend_pre()` aborts when an interrupt is pending (sets
`flags = 1`), and `__rpmi_hsm_resume()` returns early on `flags != 0`.
But `__rpmi_hsm_suspend()` itself **unconditionally zeroes `flags`** at
entry (`imsic->flags = 0;`) and proceeds to save — so the pending-abort
contract only holds if the caller ran `_pre()` first and honored its
result. There is **no enforcement**: `__rpmi_hsm_suspend` neither calls
`_pre()` nor checks a precondition. A caller invoking it directly
(the RPMI wrapper does exactly this) saves state while an interrupt may
fire mid-save → torn IMSIC state.

**Owner:** OpenSBI entry. Fix: fold the pending check into
`__rpmi_hsm_suspend` itself (or make `_pre()` mandatory via return-value
plumbing) and abort before the first CSR write.

### F3 (Medium) — HSTATUS left pointing at the last VGEN

The VS-IMSIC save sweeps `k = 1..IMSIC_MAX_VGEN-1` by **writing
HSTATUS.VGEIN** and never restores the original HSTATUS value (it was
saved into `imsic->hstatus` at the start, but not written back after the
sweep). On the WFI-wake path (in-place resume) HSTATUS.VGEIN retains the
last swept VGEN. For the non-retentive *power-down* path the resume comes
via `__rpmi_hsm_resume()` which restores hstatus — but only when reached
(hart-start contract, F6). In-place wake + later `resume()` is fine;
**in-place wake WITHOUT `resume()` (the current CPU_NR in-place path)
leaves virtual-interrupt routing pointing at the wrong guest file.**

**Owner:** OpenSBI entry. Fix: restore `imsic->hstatus` to HSTATUS after
the sweep.

### F4 (High) — the power-down vote is never devoted on the wake path

Entry votes `spacemit_vote_powrdown_core()`; the in-place WFI-wake path
runs only steps 9/8/11 (snoop set, cache enable, unmask) — **no
`spacemit_devote_*` call**. The vote persists after wake. Consequences:

- The PMU still considers this core a power-down candidate at the next
  idle, even if the OS now wants shallow idle.
- For the 8/12/1/4 "always core-vote" harts the vote is *unconditional*
  (they vote regardless of type) — on those harts the vote is
  effectively permanent after the first non-retentive suspend.
- The plan's P1-c transactional-vote requirement (ESOS side) cannot
  compensate: it never sees this vote.

**Owner:** OpenSBI resume (in-place wake). Fix: explicit
devote paired with the vote, gated on the same transaction.

### F5 (Medium) — prefetch disable is never re-enabled

`csi_disable_data_preftch()` on entry; the wake path re-enables cache and
snoop but **never prefetch**. Performance leak per cycle, and — worse for
the audit's "architectural state survives" criterion — it is invisible
state divergence between "never suspended" and "suspended once" harts.

**Owner:** OpenSBI resume. Fix: `csi_enable_data_preftch()` (or save/
restore the prefetch CSR) paired with the disable.

### F6 (Medium) — resume is only reachable via hart-start; the in-place wake path restores almost nothing

Two resume contracts coexist:

1. **In-place WFI wake** (the current code path): restores snoop bit,
   D-cache, unmask. Does NOT restore: IMSIC (M/S/VS), H-status, prefetch
   (F5), vote (F4). For a *retentive* suspend this would be correct —
   nothing was lost. But this path is used for the **non-retentive**
   0x90000000 type, where the core may actually have powered down.
   If the PMU honored the vote, register/CSR state (including the saved
   IMSIC file in scratch — scratch survives, CSRs do not) is LOST, and
   the hart resumes with zeroed IMSIC enables → interrupts never deliver
   again on that hart.

2. **`__rpmi_hsm_resume()` via hart-start** (`rpmi_hsm_resume` hook):
   restores the full IMSIC M/S/H/VS state from scratch. But this hook is
   the HSM device's `.hart_resume`, called on hart START (cpu_up), not
   on suspend wake.

**The core question the audit cannot answer from source alone:** does the
PMU, after the vote, actually power the core down at WFI (making path 1
catastrophically wrong), or is the vote merely an eligibility hint that
stays pending until a cluster-level decision (making path 1 correct and
F4 the real bug)? The DT advertises these as *non-retentive* states, and
`riscv_sbi_hart_suspend` for non-retentive types jumps to warmboot — but
`__rpmi_hsm_suspend` returns after WFI (in-place), so the kernel-side
non-retentive contract (resume at `resume_addr` via warmboot) **does not
match the firmware behavior (in-place resume)**. This is a contract
mismatch to resolve in the P0-4 qualification, not code to guess at.

**Owner:** OpenSBI (both paths). Fix direction: the non-retentive type
must either (a) actually power down and resume via warmboot +
`__rpmi_hsm_resume` (matching the SBI contract), or (b) be re-advertised
as retentive-in-place with votes removed. Until (a) or (b), 0x90000000
stays rejected — it currently returns success from a path whose resume
contract is undefined.

### F7 (Low) — A100 comment rot

`/* for a100 */` guards `current_hartid() < 8` — but harts 0–7 are the
X100 cluster per the vendored DT and the hart-contract documentation.
The saved H-extension state is the X100's. Comment-only.

### F8 (Low) — `htimedelta`/`henvcfg` high halves commented out

`HENVCFGH`/`HTIMEDELTAH` are RV128 leftovers and genuinely absent on
RV64 — the comments are correct. Noted for completeness: no action.

## Entry/abort/resume ownership matrix (P0-5)

| Resource | Entry owner | Abort owner | Resume owner |
|---|---|---|---|
| FI-mask bits (COREx_IDLE_CFG) | OpenSBI `mask_irq` | OpenSBI (must clear — currently missing on the EINVAL/ENOTSUPP early-outs? No: those return BEFORE the mask. ✓) | OpenSBI `unmask_irq` |
| IMSIC save / `flags` | OpenSBI | OpenSBI (nothing to undo — save is read-only into scratch) | OpenSBI `resume()` |
| HSTATUS.VGEIN sweep | OpenSBI | **OpenSBI — MISSING (F3): sweep runs, no restore if aborted after it)** | OpenSBI `resume()` |
| Core power-down vote | OpenSBI `vote_*` | **OpenSBI — MISSING (F4): no devote on any abort or wake** | **OpenSBI — MISSING** |
| Prefetch disable | OpenSBI | — | **OpenSBI — MISSING (F5)** |
| D-cache disable / snoop clear | OpenSBI | — | OpenSBI (restores ✓) |
| Cluster vote / domain state | (rejected: ENOTSUPP) | ESOS model (P1) | ESOS model (P1) |

**Abort-path gap analysis:** the P0-1 dispatch rejections
(ENOTSUPP/EINVAL) return **before** any hardware change — verified in the
disassembly (the compares precede the first CSR write). But an abort
*after* the vote (e.g. a future failure between vote and WFI) currently
has no cleanup path at all: F4's missing devote is the cleanup. The fix
below adds a single `k3_hsm_cleanup()` used by both abort and wake.

## Implementation (this batch)

1. **F2**: fold the pending-interrupt check into `__rpmi_hsm_suspend`
   (abort with `SBI_EFAIL` before the first CSR write).
2. **F3**: restore HSTATUS after the VGEN sweep.
3. **F4/F1**: explicit vote/devote pairing — `k3_hsm_vote_and_track()`
   records the vote in scratch; `k3_hsm_cleanup()` (called on every
   wake AND every post-vote abort) devotes exactly what was voted and
   clears the FI-mask via the named inverse.
4. **F5**: prefetch re-enable in `k3_hsm_cleanup()`.
5. **F6**: 0x90000000 returns `SBI_ENOTSUPP` until the resume contract
   is resolved (warmboot vs in-place) and qualified — the honest state
   machine: no non-retentive type is offered until its resume is real.
   This supersedes the P0-1 "0x90000000 keeps the per-CPU vote path"
   (that path's resume contract is the audit's F6 finding).
6. **F7**: comment fixed to "x100".

After this batch, the only offered suspend type is the qualified
retentive type-0 WFI. Every non-retentive type is rejected with a
diagnostic — which is precisely the "firmware tables cannot advertise a
state absent from the installed implementation" acceptance criterion
(P0-6's principle) applied to SBI.
