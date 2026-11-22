# A100 accelerator design guidelines

## Purpose and architectural direction

A100 provides explicitly requested compute acceleration for workloads such as inference, media processing, and numerical kernels. X100 remains the default execution environment for applications, operating-system housekeeping, and virtualization.

The initial direction is **Linux-managed A100 compute workers behind an accelerator runtime**. This reuses the existing software ecosystem while keeping ordinary application scheduling on X100. A separate firmware-managed execution environment is deferred; it would require replacing substantial existing infrastructure.

Accelerator semantics do not require excluding A100 from Linux CPU enumeration. Enumeration describes hardware Linux manages; execution eligibility requires a separate, enforced kernel contract.

## 1. Preserve explicit ownership and execution boundaries

- Ordinary application threads must remain on X100 unless explicitly admitted to A100 execution.
- A100 workers must remain within a compatible execution class throughout their active lifetime.
- Kernel scheduling, affinity fallback, CPU hotplug, and administrative affinity changes must preserve that restriction.
- Required per-CPU kernel activity is distinct from general application scheduling.
- KVM and its privileged operations must remain confined to capable X100 cores.
- Exactly one subsystem must own A100 lifecycle operations. Linux CPU management and a separate accelerator controller must never independently start, stop, or reset the same harts.

An accelerator library should expose work submission, completion, and resource allocation. Applications should not need to manipulate hart IDs or write procfs controls directly.

## 2. Treat heterogeneous vector support as a kernel ABI problem

X100 and A100 have different vector-register lengths. Larger save buffers alone do not make arbitrary migration safe.

Qualification must cover:

- Vector allocation, context switching, and restore.
- Signal frames, alternate signal stacks, ptrace, and core dumps.
- Fork, clone, exec, and worker teardown.
- Kernel vector use and preemption.
- CPU offline and scheduler fallback.
- Per-class feature discovery and library initialization.
- KVM guest vector state independently of host allocation sizes.

Admission must occur at a demonstrably safe point. A fresh process admitted before `exec` is the initial reference model. In-process worker admission requires separate proof that prior vector use and shared library state cannot invalidate it.

Failed admission, unsupported instructions, or incompatible vector state must produce an explicit error before specialized kernels run. Logging a warning and continuing is insufficient.

The existing [vendor HMP implementation](https://github.com/spacemit-com/linux-6.18/blob/7d17e358c660f1046eb1f27f26eea33955813afd/drivers/soc/spacemit/hmp.c) is implementation evidence to audit, not an interface to adopt unchanged.

## 3. Make ACPI descriptions truthful and policy-independent

For Linux-managed A100 execution:

- Provide consistent processor identities across DSDT, MADT/RINTC, RHCT, and PPTT.
- Describe each class's actual ISA, interrupt resources, MMU properties, and cache topology.
- Preserve existing X100 identities.
- Never advertise H on A100 to preserve a system-wide capability.
- Keep hardware discovery separate from permission to schedule ordinary tasks.
- Define and review the execution-class discovery contract before enabling A100 in a release.

Prefer existing standardized descriptions where they express the required information. Any additional property must have a documented binding, named consumer, and defined semantics. Do not represent a vendor-specific property as a standardized `_DSD` mechanism merely because it uses a standard property UUID.

Adding processor objects must be coordinated with kernel support. An ACPI table change alone cannot provide safe heterogeneous scheduling.

## 4. Keep the runtime replaceable and source-buildable

Use a small integration boundary covering capability discovery, resource acquisition, kernel submission, completion, synchronization, and resource release.

Separate:

| Layer | Responsibility |
|---|---|
| Framework integration | Select operations, layouts, and fallback implementations |
| Compute runtime | Allocate workers, dispatch work, synchronize, and manage scratch storage |
| Linux | Enforce admission, task isolation, memory protection, and lifecycle rules |
| OpenSBI | Provide required privileged hart-management operations |
| ESOS | Coordinate physical power, reset, clocks, and shared-domain dependencies |

[SpineRuntime](https://github.com/spacemit-com/spine-runtime) provides useful prior art for streams, tiles, futures, and resource allocation. Its currently published prebuilt implementation must remain an optional dependency unless corresponding source and reproducible build inputs become available.

Do not confuse cooperative runtime allocation with kernel-enforced isolation. Discover actual capabilities rather than embedding CPU numbers, vector widths, or scratch-buffer sizes in application code.

## 5. Define memory and failure semantics before concurrency

Document ownership and lifetime for submitted buffers, packed weights, scratch memory, and DMA mappings.

Distinguish ordinary coherent memory access from transfers involving TCM or DMA. Completion must establish that results are visible and relevant memory activity has finished.

Specify behavior for:

- Admission or allocation failure.
- Worker exit and application termination.
- Submission timeout and cancellation.
- CPU hotplug and system suspend.
- Runtime failure during outstanding work.

A timeout does not prove that execution or DMA has stopped. Buffers must not be freed or reassigned until access has ended.

Do not promise independent accelerator reset until the hardware's reset boundaries are verified.

## 6. Integrate power management with real activity

Track separately:

- Allocated compute resources.
- Runnable and executing jobs.
- Outstanding memory transfers.
- Retained scratch data.
- Shared-domain dependencies.

Persistent workers should use bounded spinning followed by blocking where appropriate. An idle runtime must not keep all A100 cores busy indefinitely.

ESOS must receive reliable ownership information before shared-domain shutdown is enabled. Queue emptiness, stream destruction, and CPU idleness are not interchangeable proofs of quiescence.

Begin with functional execution and qualified shallow idle. Add deeper states only after wake, retention, and concurrency behavior are demonstrated on A100.

## 7. Select acceleration by measured benefit

A100 is not automatically the fastest destination for all vector workloads.

Keep X100 implementations available. Select execution using operation type, dimensions, packing cost, memory demand, and measured end-to-end benefit. Distinguish plain RVV performance from IME2 acceleration.

Use scalar-reference tests and numerical residuals as correctness gates. A microbenchmark improvement does not justify a change that worsens complete-model latency, memory use, or energy consumption.

The [OpenSolvers IME tests](https://github.com/opensolvers/benchmarks/tree/main/ime), [HPL discussion](https://forum.spacemit.com/t/topic/1684), and [A100 RVV measurements](https://camel-cdr.github.io/rvv-bench-results/spacemit_a100/index.html) provide complementary qualification workloads.

## 8. Deliver through independently reviewable stages

1. Record the current vendor contracts and pin source revisions.
2. Audit kernel heterogeneity support and establish negative tests for forbidden execution.
3. Add coordinated ACPI discovery under an experimental profile.
4. Demonstrate safe explicitly admitted workers and numerical correctness.
5. Integrate a replaceable runtime with one framework.
6. Qualify concurrency, recovery, power consumption, and system suspend.

Retain a reproducible X100-only configuration throughout. Every milestone must identify the exact firmware, kernel, runtime, and workload artifacts tested.

Release claims must distinguish **described**, **implemented**, **hardware-tested**, and **qualified** behavior. Sixteen enumerated harts are not, by themselves, evidence of a safe accelerator platform.
