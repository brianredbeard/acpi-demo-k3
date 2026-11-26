# ESOS shared-domain ownership and retained wake (P1)

This directory preserves Brian 'redbeard' Harrington's first P1 design and the two model files recovered in commit `46b3f8d`. OpenSBI handles suspend and resume on the affected hart. ESOS decides when shared resources may sleep and coordinates the cluster's M2 entry and wake. For a firmware build, use the numbered patches selected by the lock and the supported ESOS build procedure. [Source lock](../../../sources.lock.json) · [ESOS build guide](../../esos-build.md)

## Original design and recovered source

| Part | Design and implementation in this snapshot |
| --- | --- |
| P1-a. Resource ownership | A per-cluster bitmask tracks X100 AP, A100, GPU, display, DMA and management consumers. An active bit prevents sleep. The design calls for a sticky blocker on unknown ownership. The archived acquire function returns an error for an unknown consumer before setting that bit. |
| P1-b. State transitions | The model defines active, entering, committed, asleep, restoring and aborted states. The management core masks interrupts around state changes. A consumer arriving during entry or after commitment takes the abort path. |
| P1-c. Transactional votes | A sleep request records the generation before waiting for M2 entry and compares it afterward. The recovered code misses an invalidation when a late acquisition sets the state to aborted before calling the abort helper. The later numbered patch invalidates the generation in the same critical section as the state change. |
| P1-d. Retained wake | The model provides M2 enter/exit callbacks, a semaphore wait with a caller-supplied timeout, and retained counters for M2 interrupts, wake reasons, aborts and stale votes. The first design left physical cluster shutdown for a later sequencer. |

The [header](k3_domain_ownership.h) defines the states, consumers and API. The [C source](k3_domain_ownership.c) implements the model and host-test hook. The design uses the existing M2 enter/exit interrupts, the `clusterx_m2_lp_ctrl` handshake and `AUDIO_WAKEUP_EN_REG` wake enables. Only the model and header survived from the first working tree. The integrated `k3-os0_hsm.c` interrupt and RPMI suspend-prepare changes appear in [patch 0007](../../../patches/esos/0007-k3-domain-ownership-p1.patch). [Patch 0011](../../../patches/esos/0011-ownership-sticky-block-and-provider-release.patch) revokes qualification on unknown ownership and rechecks all holders before entry.

## Verification history

Commit `58f0515` reported an `rt24/os0_rcpu` working-tree cross-build and 21 host checks. That harness rejected an unknown acquire and used an A100 acquisition to exercise blocking. The original qualification plan called for last-hart entry, sibling wake races, timer/IPI/UART retention, duplicate or delayed requests, and power measurements. The repository’s fault-injection harness compiles the **locked, prepared ESOS source**. [Ownership tests](../../../tests/test_k3_domain_ownership.py)

The November 21 closeout records later P1 hardware work. On the `lpi2q` stack, the reported mean wall draw fell from 18.80 W to 16.71 W with CPUs 4–7 offline. Those measurements belong to the firmware composition identified in that record. [P1 closeout](../../arc-closeout-2026-11-21.md) · [Power measurements](../../power-evidence-2026-11-21.md)
