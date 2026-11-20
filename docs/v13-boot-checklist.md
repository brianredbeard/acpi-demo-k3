# v13 boot cycle — payload request and verification checklist

Firmware deltas vs the qualified v12 (edk2 = v12 + 0011 + 0012; ESOS unchanged
from the 0006-fixed build):

| Patch | Content |
|---|---|
| 0011 | RHCT ISA string completed (zicntr zicond zicsr zifencei zihintpause zihpm zfh zfhmin zba zbb zbc zbs zkt zvbb..zvkt svinval svnapot), `_OSC` real support mask (PCIeCapability only), DBI0 ResourceConsumer, GMAC1/2 ClockDxe rows retargeted, EnableClock failure semantics, hart contract docs, borrowed-ID docs |
| 0012 | `_LPI` on all 8 ACPI0007 devices: CPU_NR (`(1<<60)|0x90000000`) + CLUSTER_NR (`(1<<60)|0x91000000`), vendor latencies |

ESOS/OpenSBI/FSBL/agent: unchanged from the qualified v11/v12 payloads.

## Flash payload request

- `edk2.bin`: rebuild from the maintained tree at `3faadd7b` (series 0001-0012)
  with `ACPI_ENABLE=TRUE`, RELEASE. The built FV on this workstation already
  verifies: 8× `_LPI` with both states, RHCT carries zicond/zvbb/zicsr,
  `SUPP=(CDW2&0x10)`, DBI0 consumer.
- Everything else: keep v11/v12 bytes.

## Verification checklist (in order, serial console)

1. **Boot health** — full RHEL boot, zero BUG/WARNING/ERROR; SPCR console
   still active (`ACPI: SPCR: console: uart,mmio32,0xd4017000,115200`).
2. **RHCT HWCAP** — `grep -m1 isa /proc/cpuinfo` must now show
   `zicbom zicboz zicntr zicond zicsr zifencei zihintpause zihpm zfh zfhmin
   zba zbb zbc zbs zkt zvbb... svinval svnapot` (the 0011 fix; the v12 boot
   showed only the RHCT subset). Also `dmesg | grep -i 'riscv: base ISA'`.
3. **_LPI / cpuidle** — the new milestone:
   - `ls /sys/devices/system/cpu/cpu0/cpuidle/` exists with states
     `LPI-0` (safe) and `LPI-1`/`LPI-2` (CPU_NR/CLUSTER_NR)
   - `cat /sys/devices/system/cpu/cpu*/cpuidle/state*/name` — expect
     `LPI-0`, `LPI-1`, `LPI-2` on all 8 CPUs
   - `dmesg | grep -iE 'LPI|cpuidle'` — no `Invalid LPI entry method`,
     no `acpi_cpu_init_idle` failure
   - Soak: `sleep 60 && cat /sys/devices/system/cpu/cpu*/cpuidle/state*/usage`
     — LPI-1/LPI-2 usage counts must increase
4. **Wake sources after deep idle** (the audit's hard requirements):
   - IPI: task across CPUs, no hang
   - UART: serial console still responsive after idle soak
   - NVMe: `dd` from the root device after the soak
   - Network: GMAC still passes traffic (cluster votes + M2 coordination)
5. **Timer behavior** (local-timer-stop): `dmesg | grep -iE 'tick|broadcast'`
   — if the tick stops in CLUSTER_NR and nothing broadcasts, restrict to
   CPU_NR for the next cycle (drop the CLUSTER state from the macro).
6. **_OSC sanity** — `dmesg | grep -i _OSC`: no new capability-granted
   errors; PCIe still enumerates (NVMe root present).
7. **No regressions** — thermal zones, fan RPM, EC, EEPROM, GMAC link, the
   13 RPMI clock rates (ufs_aclk 491.52 MHz).

## Rollback

GRUB retains the previous kernel entry; the firmware payload is a single
edk2.bin replacement — reflash v12's edk2 if `_LPI` wedges the boot (the
`_LPI` object failing to parse is non-fatal to boot; a bad suspend state
entry is not, so the first CPU_NR idle entry is the risk point).

## v13 flash artifact (ready)

`fitimage/MUSE-Pico/MUSE-Pico.itb` — sha256
`27f40cb4c47dc205fb7d975020ea22fcdb80e6a8e932af241eb9ecf15e535aa3`,
size 3248128. Built from the maintained tree at `3faadd7b` (series
0001-0012 = the flashed v12 payload's edk2 content + 0012 `_LPI` only).
ESOS/OpenSBI/FSBL/agent unchanged from the live v12 payload — the ONLY
delta is edk2.bin. The built FV verifies 8x `_LPI` (both states, correct
FFH addresses).

v12-boot status of the checklist: items 1, 2, 6, 7 CLOSED live (zero
errors; full RHCT HWCAP; _OSC truthful mask with PCIe intact; all
peripherals + real clock rates from the firmware DSDT, no GRUB
override). Remaining on the v13 boot: items 3-5 (cpuidle states, usage
soak, wake sources, tick broadcast) — the `_LPI`-specific checks.
