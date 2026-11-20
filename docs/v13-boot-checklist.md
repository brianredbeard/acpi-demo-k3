# v13 boot cycle — payload, checklist, and evidence ledger

**This document supersedes all earlier revisions and addenda of the v13
checklist.** The `_LPI` bring-up went through five fix rounds (gate ledger
below); earlier text describing three states or `CLUSTER_NR` is historical.

## Firmware deltas vs the qualified v12 flash

ESOS/OpenSBI/FSBL/agent: **unchanged** from the live v12 payload
(`37533b27` ESOS). Only edk2.bin changes:

| Patch | Content |
|---|---|
| 0011 | RHCT ISA completion (HWCAP), PCI `_OSC` support/control bitfield separation, hart contract docs, borrowed-ID docs, GMAC1/2 ClockDxe retargeting, EnableClock failure semantics, comment corrections (clock bring-up scope, SDT rationale) |
| 0012 | `_LPI` (WFI + CPU_NR) + `\_SB` platform `_OSC` (PCLPI, 2-DWORD contract, revision/UUID error paths) |

## Flash artifact (authoritative)

`fitimage/MUSE-Pico.itb` — sha256
`8b511a13c1da3ecc2f1a131318d4b549be96efc3561b826841e7b5bef5687402`,
size 3248128. Built from the maintained tree at the comment-fix tip
(series 0001–0012 replaying clean from the pinned baseline `8e686e13`).
Earlier artifact hashes (`27f40…`, `0d0f…`, `694e…`, `5969…`) are
superseded — do not flash them; they predate the FFH/flags/index fixes.

## Verification checklist (in order)

1. **Boot health** — full RHEL boot, zero BUG/WARNING/ERROR; SPCR console
   active.
2. **RHCT HWCAP** (0011, already proven on the v12 boot) — `/proc/cpuinfo`
   isa carries the full X100 set.
3. **`_OSC`** (proven live on the previous boot) — `platform _OSC: OS
   control mask [00000080]`.
4. **`_LPI` / cpuidle** — THE milestone:
   - `dmesg`: NO `Invalid FFH LPI data` (the previous boot's failure)
   - `/sys/devices/system/cpu/cpu0/cpuidle/` with exactly TWO states:
     `LPI-0` = WFI and `LPI-1` = CPU_NR
   - State semantics: index 0 is the special path (`cpu_do_idle()`, no SBI
     suspend). **LPI-0 usage proves idle entry; only LPI-1 usage proves
     actual suspend entry.** There is no LPI-2; CLUSTER_NR is deferred.
   - Soak: `sleep 60 && cat /sys/devices/system/cpu/cpu*/cpuidle/state*/usage`
     — both LPI-0 and LPI-1 counts increase
5. **Wake sources after idle** (the hard requirements):
   - IPI across CPUs, serial console responsiveness, NVMe I/O, GMAC traffic
6. **Tick broadcast under CPU_NR timer-stop** — CPU_NR stops the local
   timer (ArchFlags bit 0). KERNEL DEPENDENCY: the deployed 6.12 kernel
   has NO `arch_get_idle_state_flags` RISC-V override (only ARM64 maps the
   flag), so `CPUIDLE_FLAG_TIMER_STOP` is NOT set unless the one-line
   kernel override is carried. **Without it, CPU_NR may stop the local
   timer without the kernel arranging broadcast — a potential idle-entry
   hang.** Carry the kernel override in the validation kernel, or watch
   `dmesg | grep -iE 'tick|broadcast'` and be prepared to restrict to
   WFI-only if hangs appear. Test CPU_NR (not CLUSTER_NR — deferred).
7. **`_OSC` sanity** — PCIe still enumerates (NVMe root on MSI-X).
8. **No regressions** — thermal, fan, EC, EEPROM, GMAC, the 13 RPMI clock
   rates (ufs_aclk 491.52 MHz).

## Rollback

Single edk2.bin reflash of the v12 payload; GRUB retains the previous
kernel entry.

## Gate ledger (historical, all fixed in the current artifact)

| # | Gate | Failure signature | Fix |
|---|---|---|---|
| 1 | `_OSC` presence | silent `-EOPNOTSUPP` | `\_SB._OSC` added; proven live (`OS control mask [00000080]`) |
| 2 | `_OSC` buffer contract | CDW3 past the 8-byte buffer | 2-DWORD method (CDW1/CDW2 only) |
| 3 | FFH encoding | `Invalid FFH LPI data` ×8 (live) | param in low 32 bits: `0x1000000090000000` |
| 4 | state Flags | zero flattened states | Flags=1 (ENABLED) on both states |
| 5 | index-0 semantics | CPU_NR would never suspend | WFI at index 0, CPU_NR at 1; CLUSTER_NR removed |
