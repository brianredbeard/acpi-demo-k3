/*
 * K3 shared-domain ownership model and retained wake mechanism (P1).
 *
 * Design per the suspend-ownership plan:
 *   - OpenSBI owns the hart's architectural suspend/resume contract
 *     (register operations executing on the affected hart).
 *   - ESOS owns shared-resource ELIGIBILITY and hardware coordination:
 *     whether a cluster/domain may power down, and how a sleeping
 *     cluster is woken.
 *
 * Scope of this first implementation:
 *   P1-a Explicit resource ownership: per-cluster consumer tracking.
 *     Unknown ownership is a BLOCKER (conservative).
 *   P1-b Shared-domain state machine: active / entering / committed /
 *     asleep / restoring / aborted with single-owner transitions.
 *   P1-c Transactional power votes: requests carry a generation number;
 *     stale or duplicate requests cannot leave a domain eligible.
 *   P1-d Retained wake mechanism: the M2 interrupt path (already the
 *     hardware contract: AP_Cx_M2_ENTER/EXIT interrupts, clusterx_m2_lp_ctrl
 *     registers, AUDIO_WAKEUP_EN_REG) is wired to the state machine with
 *     BOUNDED waits; a timeout aborts entry and leaves the cluster
 *     runnable with no stale vote.
 *
 * Deliberately NOT implemented here (per plan): cluster shutdown itself.
 * The model gates it; when every consumer is accounted for and the wake
 * mechanism is qualified, the actual power sequence goes through
 * k3_domain_commit_sleep() with the documented ordering hooks.
 *
 * Diagnostics (supporting deliverable): retained per-cluster counters —
 * requests, aborts, wake reasons, state transitions — readable via
 * debugger; NO serial logging in the transition path.
 */

#ifndef K3_DOMAIN_OWNERSHIP_H
#define K3_DOMAIN_OWNERSHIP_H

#include <rthw.h>
#include <rtthread.h>

/* ---- cluster/domains ------------------------------------------------ */

#define K3_MAX_CLUSTERS		4	/* C0..C3 (X100: C0/C1 only) */

/*
 * Shared-domain states. Transitions are single-owner (the ESOS management
 * core serializes through the cluster lock):
 *
 *   ACTIVE -> ENTERING -> COMMITTED -> ASLEEP -> RESTORING -> ACTIVE
 *        \              \
 *         \              -> ABORTED -> ACTIVE (no vote survives)
 *         -> ABORTED -> ACTIVE
 *
 * ENTERING: votes are being placed; a late consumer or a timeout aborts.
 * COMMITTED: the power-down decision is final; wake is the only exit.
 * ASLEEP: hardware MP state confirms the cluster is in M2.
 * RESTORING: the M2-EXIT path is waking the cluster; new requests wait.
 */
enum k3_domain_state {
	K3_DOMAIN_ACTIVE = 0,
	K3_DOMAIN_ENTERING,
	K3_DOMAIN_COMMITTED,
	K3_DOMAIN_ASLEEP,
	K3_DOMAIN_RESTORING,
	K3_DOMAIN_ABORTED,
};

/* Consumer classes for ownership accounting. Unknown = blocker. */
enum k3_consumer_class {
	K3_CONSUMER_X100_AP	= 0,	/* application cores in this cluster */
	K3_CONSUMER_A100	= 1,	/* accelerator cores (harts 8-15) */
	K3_CONSUMER_GPU		= 2,
	K3_CONSUMER_DISPLAY	= 3,
	K3_CONSUMER_DMA		= 4,
	K3_CONSUMER_MGMT	= 5,	/* ESOS/management itself */
	K3_CONSUMER_CLASS_COUNT,
	K3_CONSUMER_UNKNOWN	= 0xff,	/* blocker: unaccounted activity */
};

struct k3_wake_stats {
	rt_uint32_t m2_enter_count;
	rt_uint32_t m2_exit_count;
	rt_uint32_t wake_ipc;
	rt_uint32_t wake_timer;
	rt_uint32_t wake_other;
	rt_uint32_t aborted_entry;
	rt_uint32_t stale_vote_rejected;
};

struct k3_cluster_domain {
	/* state machine (protected by lock) */
	enum k3_domain_state	state;
	rt_uint32_t		generation;	/* vote transaction id */
	rt_base_t		lock;

	/* ownership: bitmask of active consumers (per class) */
	rt_uint32_t		consumers;

	/* entry coordination */
	rt_sem_t		m2_enter_sem;	/* AP requested entry */
	rt_sem_t		m2_exit_sem;	/* cluster exited M2 */
	rt_uint32_t		hw_mp_state;	/* last observed clx_mp_state */

	/* retained diagnostics (debugger-readable; no serial I/O) */
	struct k3_wake_stats	stats;
};

/*
 * Ownership API. All return 0 on success, negative errno on failure.
 * Unknown ownership BLOCKS sleep: k3_domain_consumer_acquire() with
 * K3_CONSUMER_UNKNOWN returns -RT_EINVAL and marks the cluster
 * permanently active until explicitly cleared.
 */
int k3_domain_consumer_acquire(int cluster, enum k3_consumer_class c);
int k3_domain_consumer_release(int cluster, enum k3_consumer_class c);
rt_bool_t k3_domain_sleep_eligible(int cluster);

/*
 * State machine + wake. Bounded waits only: timeout_ms <= 0 means
 * non-blocking poll. Entry abort leaves the cluster ACTIVE with no vote.
 */
int k3_domain_request_sleep(int cluster, int timeout_ms);
int k3_domain_abort_sleep(int cluster);
int k3_domain_note_wake(int cluster, enum k3_consumer_class source);

/* M2 hardware hooks (called from the existing IRQ handlers). */
void k3_domain_m2_enter_isr(int cluster);
void k3_domain_m2_exit_isr(int cluster);

/* One-time init per cluster (idempotent). */
int k3_domain_init(int cluster);

#endif /* K3_DOMAIN_OWNERSHIP_H */
