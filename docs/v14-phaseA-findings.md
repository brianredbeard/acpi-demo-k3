# v14 phase-A findings — CPU4 wedge on 0x80000000 rejection (2026-11-20)

## What ran

- Payload: pico-acpi-v14 (OpenSBI fw_dynamic c83ce98e...; all other
  regions byte-identical to qualified v12). Flashed via the qualified
  k3-firmware tool; full-NOR readback verified.
- Boot: clean to RHEL login. SBI v2.0, HSM extension detected.
- Test module loaded (sbi_suspend_test.ko, built against the running
  dbg1 kernel). First probe: type 0x80000000 (SBI_HSM_SUSPEND_NON_RET_
  DEFAULT) written to /sys/kernel/sbi_suspend_test/type on CPU4.

## Observed

1. The OpenSBI diagnostic FIRED: "rpmi-hsm: hart 4 suspend type
   0x80000000 failed: -2" — the error propagation (P0-3) and the
   rejection (P0-1) both work, and the message identifies hart and
   type exactly as designed.
2. CPU4 never returned to the kernel: no shell response, and two NMI
   attempts ("Sending NMI ... to CPUs 4:" at 204.2s and 241.3s)
   produced NO backtrace for cpu 4 — CPU4 does not service NMIs.
3. Cascade: every other CPU (0,1,2,3,5,6,7) soft-locked in
   smp_call_function_many_cond waiting for CPU4's IPI response.
   42 lockup dumps over ~6 minutes; the serial console itself kept
   working (interrupts deliver on the reporting CPUs).
4. The shell did not recover within the observation window; network
   (GMAC) also stopped responding.

## Interpretation

The REJECTION PATH ITSELF is proven working end-to-end (the
diagnostic proves __rpmi_hsm_suspend returned -2 and the wrapper
printed it). The wedge is in what happens AFTER the return on this
specific hart — CPU4 is one of the four "special" harts (8/12/1/4)
whose vote was previously UNCONDITIONAL.

Leading hypothesis: my P0-4 restructure moved the type dispatch
(type==0x80000000 -> SBI_ENOTSUPP) to a point AFTER the IMSIC save
block (the pending-check + save run before the dispatch). The save
block itself rewrites IMSIC CSRs (miselect/mireg indirect accesses)
and masks the hart's IRQs (spacemit_mask_irq). If the return path
from the ENOTSUPP does not undo the mask (it does NOT — the cleanup
is only in the never-called k3_hsm_cleanup_wake), the hart returns
to S-mode with interrupts masked and IMSIC state half-saved: it
executes WFI-equivalent forever (no timer, no IPI), exactly matching
"no NMI backtrace".

This is a REAL FINDING of the fault-injection methodology: the
rejection is not side-effect-free on the current code layout. The
dispatch rejection must happen BEFORE spacemit_mask_irq and the IMSIC
save — i.e., hoist the type validation above the entire
hardware-touching block (it currently sits after the save).

## Fix (next OpenSBI patch revision)

Move the explicit-dispatch validation (the ENOTSUPP/EINVAL checks)
to the TOP of __rpmi_hsm_suspend, before the pending-interrupt
check, the mask, and the IMSIC save. Then a rejected type performs
ZERO CSR writes and ZERO PMU writes — matching the disassembly claim
made for the original P0-1 (which was true of THAT layout; the P0-4
edit inserted the save block above the dispatch and invalidated it).

Also: k3_hsm_cleanup_wake should be called on any return path after
spacemit_mask_irq, until the hoist makes that unreachable.

## Status

- P0-3 error propagation: PROVEN on hardware (the diagnostic line).
- P0-1 rejection semantics: CORRECT at the SBI level (-2 returned),
  but the implementation performs hardware changes before rejecting
  on this path — a bug found by the test, to fix before re-testing.
- Phase B (type-0 WFI): NOT reached this cycle.
- Board state: wedged; needs a hard reset (power cycle or reset
  button). The NOR is intact (flash verified by readback; the wedge
  is a runtime state, not corruption).
