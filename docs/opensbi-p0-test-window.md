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
