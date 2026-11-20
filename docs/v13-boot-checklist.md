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

## Addendum: first v13 boot failed silently — root cause + fix

Symptom: _LPI present in the DSDT (24 strings), processor devices bound
(ACPI0007, firmware_node paths resolve), but NO cpuidle directory and zero
LPI-related dmesg. Config verified on the running kernel:
ACPI_PROCESSOR_IDLE=y, RISCV_SBI_CPUIDLE=y, ffh_lpi_probe present in
kallsyms.

Root cause: acpi_processor_get_lpi_info() gates ALL _LPI parsing on
osc_pc_lpi_support_confirmed, which is set only by the platform-wide _OSC
handshake (Linux acpi_bus_osc_support at \_SB, UUID 0811B06E-...,
OSC_SB_PCLPI_SUPPORT = 0x80). The DSDT had no \_SB._OSC, so the handshake
failed and the whole path bailed with -EOPNOTSUPP before touching _LPI —
and the resulting "No ACPI power information" is pr_debug, invisible at
default loglevel.

Fix (patch 0012 amended, maintained b1a2bd8b): \_SB._OSC confirming
PCLPI (0x80) only. Unknown UUIDs return _OSC failure; PR3/GED/hotplug-OST
not confirmed (not provided by this firmware).

Expected evidence on the fixed boot:
- dmesg: "ACPI: \_SB_: platform _OSC: OS control mask [00000080]" (or the
  support-mask line reflecting 0x80)
- /sys/devices/system/cpu/cpu0/cpuidle/ with LPI-0/LPI-1/LPI-2
- the checklist items 3-5 as originally written

## Addendum 2: _OSC buffer contract fix (supersedes the first fix)

The first \\_SB._OSC implementation (b1a2bd8b) had a buffer overrun:
the platform _OSC from acpi_bus_osc_negotiate_platform_control() passes
u32 capbuf[2] — DWORD[0] Query/Status, DWORD[1] Support, NO Control
DWORD. Creating CDW3 at offset 8 reads past the 8-byte buffer
(AE_AML_BUFFER_LIMIT on every evaluation), which would have broken the
handshake this method exists to perform.

Fixed in cfe7bc63 / regenerated patch 0012: the \\_SB._OSC creates only
CDW1/CDW2 and handles both handshake passes (query pass with
OSC_QUERY_ENABLE set, then the direct pass). The PCI0 _OSC legitimately
keeps CDW3 — pci_root.c passes capbuf[OSC_CXL_CAPABILITY_DWORDS=5].

Current artifact: fitimage/MUSE-Pico.itb sha256
0d0f407d4feddb7beddd6c364b2e334e0eb23f138b8fafc88c3918011cc271e6.

Expected evidence unchanged from Addendum 1 (PCLPI 0x80 confirmed,
LPI-0/1/2, usage soak, wake sources).

## Addendum 3: FFH address encoding fix

The second boot (with the _OSC fixes) confirmed the handshake works —
dmesg: `platform _OSC: OS control mask [00000080]` (PCLPI acknowledged,
_LPI parsing enabled) — but then: `ACPI: CPUx: Invalid FFH LPI data` on
all 8 CPUs.

Root cause: the FFH addresses were malformed. The RISC-V FFH LPI
encoding is (1ULL<<60) | sbi_suspend_param with bits[59:32] RESERVED
ZERO — the param goes in the LOW 32 bits (same convention as the CPPC
FFH registers already in Cpu.asl: 0x1000000000000005 = (1<<60)|5). The
0x19-prefixed form put the param in the reserved field, and
acpi_cpu_init_idle's RISCV_FFH_LPI_RSVD_MASK check rejected every state.

Fixed (maintained e0fcedf5, patch 0012 regenerated): CPU_NR =
0x1000000090000000, CLUSTER_NR = 0x1000000091000000. Built DSDT
verified: 8x correct addresses, no bad form, _LPI count 8.

Gate status after three fixes: _OSC presence → _OSC buffer contract →
FFH encoding. The next boot is the first where all three are correct.
