# ESOS shared-domain ownership and retained wake (P1)

This directory preserves Brian 'redbeard' Harrington's original design notes
and a snapshot of the model's C source and header. The ESOS build takes
the implementation from the numbered patches, starting with
[0007](../../../patches/esos/0007-k3-domain-ownership-p1.patch).

## Original implementation notes

ESOS-side P1 implementation per the suspend-ownership plan (OpenSBI
owns the hart's architectural suspend/resume; ESOS owns shared-
resource eligibility and hardware coordination):

P1-a EXPLICIT RESOURCE OWNERSHIP: per-cluster consumer tracking
    (X100 AP, A100, GPU, display, DMA, management). Unknown
    ownership is a sticky BLOCKER. An active consumer prevents the
    shutdown of every resource it requires.
P1-b SHARED-DOMAIN STATE MACHINE: active/entering/committed/asleep/
    restoring/aborted with single-owner transitions under the
    cluster lock. ABORTED is transient (no hardware change happened
    on the ESOS side) and returns to ACTIVE immediately; the
    generation bump rejects any stale commit from the aborted
    transaction.
P1-c TRANSACTIONAL POWER VOTES: requests carry a generation number;
    stale or duplicate requests cannot leave a domain eligible for
    shutdown (request_sleep re-validates the generation after the
    bounded wait).
P1-d RETAINED WAKE MECHANISM: the existing M2 hardware contract
    (AP_Cx_M2_ENTER/EXIT interrupts, clusterx_m2_lp_ctrl handshake,
    AUDIO_WAKEUP_EN_REG wake enables, corex assert on exit) is wired
    to the state machine. The unbounded spin in the M2-enter path is
    replaced by a semaphore with a BOUNDED wait; a timeout aborts
    entry and leaves the cluster runnable with no stale vote.

Quiescence: a consumer acquiring during ENTERING/COMMITTED aborts
the entry (new work never strands behind a committing shutdown).

Cluster shutdown itself is deliberately NOT implemented (per plan:
do not implement cluster shutdown as the next automatic step). The
suspend_prepare gate DENIES cluster-class suspends unless the model
reports eligibility; the actual power sequencing lands only after
this model plus the wake mechanism are hardware-qualified.

Diagnostics: retained per-cluster counters (m2 enter/exit counts,
wake reasons by class, aborted entries, stale-vote rejections) —
debugger-readable, NO serial logging in the transition path.

Files:
  k3_domain_ownership.h — the design contract (states, consumers, API)
  k3_domain_ownership.c — the implementation + test hook
  k3-os0_hsm.c — M2 ISRs wired to the state machine; the RPMI
    hart_suspend_prepare gate; domain init
  k3_hsm.h — K3_SUSPEND_CLUSTER_MASK

Build-verified: fresh cross-build of the working tree (scons,
rt24/os0_rcpu, the qualified toolchain); the semaphore-name format
strings confirm the model is in the binary. Fault-injection host
tests (tests/test_k3_domain_ownership.py): 21 checks covering
rejected transitions, sticky unknown ownership, bounded-wait
timeout abort with retry, late-consumer abort, wake races, wake
accounting — all passing.

HARDWARE QUALIFICATION REQUIRED before cluster states return:
per the plan's acceptance criteria (last-hart entry, sibling-wake
races, timer/IPI/UART retention, no stale votes under duplicate or
delayed messages) — with fault injection on hardware followed by
power measurements.
