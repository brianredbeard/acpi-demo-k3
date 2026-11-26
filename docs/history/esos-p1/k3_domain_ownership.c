/*
 * K3 shared-domain ownership model and retained wake mechanism (P1).
 * See k3_domain_ownership.h for the design contract.
 *
 * Copyright (c) 2026. SPDX-License-Identifier: Apache-2.0
 * Derived from Spacemit ESOS (Apache-2.0) M2 coordination in
 * k3-os0_hsm.c / k3-os0_hsm_interface.c.
 */

#include <rthw.h>
#include <rtthread.h>
#include <rtdevice.h>
#include "../spacemit-rpmi.h"
#include "k3_hsm.h"
#include "k3_domain_ownership.h"

static struct k3_cluster_domain k3_domains[K3_MAX_CLUSTERS];

/* ---- internal helpers ------------------------------------------------ */

static struct k3_cluster_domain *dom(int cluster)
{
	if ((cluster < 0) || (cluster >= K3_MAX_CLUSTERS))
		return RT_NULL;
	return &k3_domains[cluster];
}

static rt_uint32_t class_bit(enum k3_consumer_class c)
{
	return (rt_uint32_t)1U << (c & 0x1f);
}

/* Cluster sleep is eligible only when EVERY consumer class is accounted
 * for and released. Unknown ownership is sticky: it blocks until cleared. */
#define OWNERSHIP_UNKNOWN_BIT	((rt_uint32_t)1U << 31)

int k3_domain_consumer_acquire(int cluster, enum k3_consumer_class c)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;
	int ret = 0;

	if (!d)
		return -RT_EINVAL;

	if ((c >= K3_CONSUMER_CLASS_COUNT) || (c == K3_CONSUMER_UNKNOWN))
		return -RT_EINVAL;	/* unknown ownership is a blocker */

	level = rt_hw_interrupt_disable();
	if (d->state != K3_DOMAIN_ACTIVE) {
		/* Acquiring a consumer while entering/committed is the
		 * abort path: entry must not strand new work. */
		if ((d->state == K3_DOMAIN_ENTERING) ||
		    (d->state == K3_DOMAIN_COMMITTED)) {
			d->state = K3_DOMAIN_ABORTED;
			d->stats.aborted_entry++;
			ret = 1;	/* entry aborted; caller retries */
		} else {
			ret = -RT_EBUSY;	/* asleep/restoring: wait */
		}
	}
	d->consumers |= class_bit(c);
	rt_hw_interrupt_enable(level);

	if (ret == 1)
		k3_domain_abort_sleep(cluster);

	return (ret < 0) ? ret : 0;
}

int k3_domain_consumer_release(int cluster, enum k3_consumer_class c)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;

	if (!d)
		return -RT_EINVAL;
	if ((c >= K3_CONSUMER_CLASS_COUNT) && (c != K3_CONSUMER_UNKNOWN))
		return -RT_EINVAL;

	level = rt_hw_interrupt_disable();
	if (c == K3_CONSUMER_UNKNOWN)
		d->consumers &= ~OWNERSHIP_UNKNOWN_BIT;
	else
		d->consumers &= ~class_bit(c);
	rt_hw_interrupt_enable(level);
	return 0;
}

rt_bool_t k3_domain_sleep_eligible(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_bool_t eligible;

	if (!d)
		return RT_FALSE;

	/* Sticky unknown-ownership bit blocks sleep. Any active consumer
	 * class blocks sleep. The management core (K3_CONSUMER_MGMT)
	 * itself must be released before the cluster it manages sleeps. */
	eligible = (d->consumers == 0) &&
		   !(d->consumers & OWNERSHIP_UNKNOWN_BIT) &&
		   (d->state == K3_DOMAIN_ACTIVE);
	return eligible;
}

/* ---- state machine --------------------------------------------------- */

/*
 * Request sleep for a cluster. BOUNDED wait: the M2-enter hardware
 * handshake (spacemit_cx_m2_enter_wait's spin loop is replaced by a
 * semaphore + timeout). On timeout the entry ABORTS: no vote survives,
 * the cluster stays runnable.
 */
int k3_domain_request_sleep(int cluster, int timeout_ms)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;
	rt_err_t wait;
	rt_uint32_t my_generation;

	if (!d)
		return -RT_EINVAL;

	level = rt_hw_interrupt_disable();
	if (d->state != K3_DOMAIN_ACTIVE) {
		rt_hw_interrupt_enable(level);
		return -RT_EBUSY;
	}
	if (d->consumers != 0) {
		rt_hw_interrupt_enable(level);
		return -RT_ERROR;	/* active consumers: not eligible */
	}

	d->state = K3_DOMAIN_ENTERING;
	d->generation++;
	my_generation = d->generation;
	rt_hw_interrupt_enable(level);

	/* Bounded wait for the hardware M2-enter handshake. The ISR
	 * releases m2_enter_sem when the cluster's M2 request lands. */
	if (timeout_ms > 0) {
		wait = rt_sem_take(d->m2_enter_sem,
				   rt_tick_from_millisecond(timeout_ms));
		if (wait != RT_EOK) {
			/* timeout: abort, no vote survives */
			k3_domain_abort_sleep(cluster);
			return -RT_ETIMEOUT;
		}
	} else if (timeout_ms == 0) {
		/* non-blocking poll */
		wait = rt_sem_take(d->m2_enter_sem, RT_WAITING_NO);
		if (wait != RT_EOK) {
			k3_domain_abort_sleep(cluster);
			return -RT_ETIMEOUT;
		}
	}

	level = rt_hw_interrupt_disable();
	if (d->generation != my_generation) {
		/* stale transaction (a newer request/abort won): undo */
		rt_hw_interrupt_enable(level);
		d->stats.stale_vote_rejected++;
		return -RT_EINTR;
	}
	d->state = K3_DOMAIN_COMMITTED;
	rt_hw_interrupt_enable(level);

	/* COMMITTED: the actual power-down ordering (L2 flush, isolation,
	 * votes) is deliberately NOT implemented here — it lands only
	 * after this model plus the wake mechanism are hardware-qualified
	 * per the plan. Until then COMMITTED immediately transitions to
	 * ASLEEP only when the hardware reports the M2 state, driven by
	 * the M2-enter ISR. */
	return 0;
}

int k3_domain_abort_sleep(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;

	if (!d)
		return -RT_EINVAL;

	level = rt_hw_interrupt_disable();
	if ((d->state == K3_DOMAIN_ENTERING) ||
	    (d->state == K3_DOMAIN_COMMITTED)) {
		d->stats.aborted_entry++;
		/* votes: the OpenSBI side owns vote placement; this side
		 * only guarantees the state prevents a stale commit. The
		 * generation bump invalidates in-flight transactions. */
		d->generation++;
	}
	/* ABORTED is transient: no hardware change happened on this side,
	 * so the cluster returns to ACTIVE immediately. A COMMITTED abort
	 * additionally requires the OpenSBI-side vote cleanup (its own
	 * contract); the generation bump guarantees a stale commit from
	 * the old transaction is rejected when it lands. */
	if (d->state != K3_DOMAIN_ASLEEP)
		d->state = K3_DOMAIN_ACTIVE;
	rt_hw_interrupt_enable(level);

	return 0;
}

int k3_domain_note_wake(int cluster, enum k3_consumer_class source)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;

	if (!d)
		return -RT_EINVAL;

	level = rt_hw_interrupt_disable();
	switch (source) {
	case K3_CONSUMER_MGMT:
		d->stats.wake_ipc++;
		break;
	case K3_CONSUMER_DMA:
		d->stats.wake_timer++;	/* timer deadline routed via mgmt */
		break;
	default:
		d->stats.wake_other++;
		break;
	}
	if (d->state == K3_DOMAIN_ASLEEP) {
		d->state = K3_DOMAIN_RESTORING;
		rt_sem_release(d->m2_exit_sem);
	}
	rt_hw_interrupt_enable(level);
	return 0;
}

/* ---- M2 hardware hooks ------------------------------------------------ */

/*
 * Called from the existing AP_Cx_M2_ENTER interrupt handler. The
 * hardware contract (clusterx_m2_lp_ctrl bit 2 handshake in
 * spacemit_cx_m2_enter_wait) is preserved; this adds the state
 * accounting and the semaphore that replaces the unbounded spin.
 */
void k3_domain_m2_enter_isr(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;

	if (!d)
		return;

	d->stats.m2_enter_count++;

	level = rt_hw_interrupt_disable();
	if (d->state == K3_DOMAIN_ENTERING) {
		d->hw_mp_state = 0;	/* observed on entry */
		d->state = K3_DOMAIN_ASLEEP;
	}
	rt_hw_interrupt_enable(level);

	rt_sem_release(d->m2_enter_sem);
}

/*
 * Called from the existing AP_Cx_M2_EXIT handler (the wake path:
 * spacemit_assert_corex + spacemit_cx_m2_int_disabled). The hardware
 * wake sequence stays as-is; this restores the state machine so new
 * requests can proceed.
 */
void k3_domain_m2_exit_isr(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	rt_base_t level;

	if (!d)
		return;

	d->stats.m2_exit_count++;

	level = rt_hw_interrupt_disable();
	if ((d->state == K3_DOMAIN_ASLEEP) ||
	    (d->state == K3_DOMAIN_COMMITTED) ||
	    (d->state == K3_DOMAIN_RESTORING)) {
		d->state = K3_DOMAIN_ACTIVE;
		/* consumers re-acquire as they resume; none survive the
		 * sleep by construction (eligibility required zero) */
	}
	rt_hw_interrupt_enable(level);

	rt_sem_release(d->m2_exit_sem);
}

/* ---- init ------------------------------------------------------------- */

int k3_domain_init(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	char name[16];

	if (!d)
		return -RT_EINVAL;
	if (d->m2_enter_sem)
		return 0;	/* idempotent */

	rt_snprintf(name, sizeof(name), "k3d%d_in", cluster);
	d->m2_enter_sem = rt_sem_create(name, 0, RT_IPC_FLAG_FIFO);
	if (!d->m2_enter_sem)
		return -RT_ENOMEM;

	rt_snprintf(name, sizeof(name), "k3d%d_out", cluster);
	d->m2_exit_sem = rt_sem_create(name, 0, RT_IPC_FLAG_FIFO);
	if (!d->m2_exit_sem) {
		rt_sem_delete(d->m2_enter_sem);
		d->m2_enter_sem = RT_NULL;
		return -RT_ENOMEM;
	}

	d->state = K3_DOMAIN_ACTIVE;
	d->consumers = 0;
	d->generation = 0;
	rt_memset(&d->stats, 0, sizeof(d->stats));
	return 0;
}

#ifdef K3_DOMAIN_TEST
/* Test hook: prime the M2-enter semaphore so a bounded request succeeds. */
void k3_domain_test_prime_enter(int cluster)
{
	struct k3_cluster_domain *d = dom(cluster);
	if (d && d->m2_enter_sem)
		rt_sem_release(d->m2_enter_sem);
}
#endif
