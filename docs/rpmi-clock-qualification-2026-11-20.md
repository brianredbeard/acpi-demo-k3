# RPMI clock architecture qualification — 2026-11-20

Status: **hardware-qualified end to end** on pico-acpi-v11 (Pico-ITX, RHEL 10
ACPI boot). This records the qualified configuration, the defects found and
fixed on the way, and the architectural facts that constrain the remaining
work (Tasks 5-7, 9 and the PCC model).

## Qualified stack

| Layer | State | Evidence |
|---|---|---|
| EDK2 tables (0008/0009) | SPCR v4 + ACPI 6.6 conformance live | Serial console through full RHEL boot (no autoconfig hang — the XScale compatible gating worked); 8 CPUs enumerated, processor objects bound |
| DSDT v12 | MPXY (`RSCV0005` + `#mbox-cells 2`) + RCLK (`PRP0001 riscv,rpmi-clock` + `mboxes` ref `{MPXY, 8, 0}`) | `riscv-sbi-mpxy-mbox RSCV0005:00: mailbox registered with 5 channels`; `riscv-rpmi-clock` bound to PRP0001:04 |
| Kernel (6.12-based) | clk-rpmi clkdev aliases (con_id = RPMI name, dev_id NULL) | All 13 clocks name-addressable in `/sys/kernel/debug/clk/` |
| OpenSBI (shipped, unchanged) | MPXY ecall + channels | 5 channels through the FDT's `rpmi-mpxy-*` nodes; no rebuild needed |
| ESOS (0001-0006) | RPMI CLOCK service on MPXY channel 8 wired to the CCU | All 13 clocks with real hardware rates; **ufs_aclk = 491.52 MHz** |

## Defects found and fixed during bring-up

| Defect | Layer | Fix | Caught by |
|---|---|---|---|
| GET_STATE/GET_RATE wrote through NULL outputs (librpmi passes either as NULL) | ESOS service | Guard each output independently (0003) | Audit + host regression |
| Unresolved clocks returned NOTSUPP at init, aborting the ENTIRE clock group (`rpmi_clock_tree_init` fails the group on any per-clock error) | ESOS service | Deterministic placeholders (DISABLED + 0); `was_unresolved` flag for metadata refresh | Audit (reading pinned librpmi) |
| Metadata refresh condition `rate_count == 0` unreachable (published unresolved entries carry 1) | ESOS service | Explicit entry flag | Audit |
| **`spacemit_ccu_get_clk_by_name` matched `hw->init->name`, but `__clk_register()` NULLs `hw->init` after registration — every registered clock failed the lookup; all 12 consumer clocks published as unresolved (rate 0)** | ESOS CCU lookup (0002) | Match on `clk_hw_get_name(hw)` (`core->name`, valid post-registration) — 0006 | Live v11 boot: factor clock `ufs_refclk` also read 0 (computed rate, never register-read) ⇒ clocks never resolved, not wrong registers |
| CCU field transposition (Linux `CCU_MUX_DIV_GATE_FC_DEFINE` is div-first despite the name; values passed positionally swapped) | ESOS CCU port (0004) | 0005 field fixes — ufs_aclk div↔mux/fc↔gate would have written W1C FC_REQ and cleared ACLK_EN on enable; axi enable would have flipped the source 307↔409 MHz | Board-side audit |

## Architectural facts established

1. **The RPMI clock contract works**: Linux `clk-rpmi` ⇄ MPXY mailbox ⇄
   OpenSBI ⇄ ESOS librpmi service ⇄ CCU hardware, with real rates and
   hardware gate readback. This is the reference path for every remaining
   firmware-owned resource (Tasks 5-7: MMC/SPI/UFS functional bring-up).
2. **ufs_aclk = 491.52 MHz** (manual truth). The kernel
   `UFS_AXI_CLK_LOW_FREQ_HZ` fallback assumes 409.6 MHz — UFS sys1clk
   programming is ~20% off until the UFS driver consumes the RPMI clock
   (Task 7's first consumer wiring).
3. **Consumer wiring decision**: RPMI names are unambiguous; consumers
   request them by con_id through the clkdev aliases. Per-consumer mapping
   goes through driver platform-data changes (option (a) in the Task 7
   plan), not `_DSD` clock-name indirection (ACPI has none).
4. **Placeholder opacity**: the unresolved placeholder (SUCCESS + rate 0)
   is indistinguishable from "resolved but zero" in the Linux clock tree.
   The regression test shim should NULL `hw->init` after registration like
   the real core so the post-registration lookup path is what gets
   exercised (the gap that let the 0006 bug through).
5. **SPCR + XScale quirk pair is proven**: the console-hang mechanism is
   closed on hardware; the compatible-gated `PORT_XSCALE` fixed-type quirk
   is now an upstreaming candidate with its firmware counterpart (0008)
   qualified.

## Constraints carried forward

- A6 (`RSCV0006` SYSMSI) stays excluded: the firmware-side
  `k3_os0_validate_msi_addr` accepts arbitrary targets — fix before
  describing.
- The maintained edk2-platforms worktree still carries uncommitted 0008/0009
  content plus the draft PCC files; land before the next build handoff.
- OpenSBI remains an unpinned component (the shipped binary is qualified
  but not reproducible from this repo yet).

## v12 boot verification addendum — 2026-11-20 (live)

Firmware: 0006-fixed ESOS + 0008/0009 EDK2 (SPCR + ACPI 6.6 conformance),
DSDT with MPXY/RCLK + Cpu.asl; kernel with the clk-rpmi clkdev aliases.
Verified on the serial console:

- SPCR live: `ACPI: SPCR: console: uart,mmio32,0xd4017000,115200` (table
  v04); serial console through full RHEL boot with the XScale quirk engaged
  (`RSCV0003:00: ttyS0 ... is a XScale`). No autoconfig hang.
- Processor objects: 8 CPUs, `DRIVER=processor` bound per ACPI0007 device.
  No cpuidle states — correct pre-Task-9 (no _LPI AML yet; see the HSM
  suspend audit for the encoding that is now allowed).
- MPXY/RCLK: mailbox 5 channels (RSCV0005:00), riscv-rpmi-clock bound.
- All 13 clocks with REAL rates post-0006: ufs_aclk=491.52 MHz (manual
  truth; the kernel's 409.6 MHz fallback is wrong — Task 7 consumer gap),
  emac0_bus=307.2 MHz, twsi0=31.507692 MHz, gpio=24 MHz, sdh0=204.8 MHz,
  usb2_bus=307.2 MHz, rproc=500 MHz.
- Thermal 7 zones 52-56C, fan 2294 RPM, zero BUG/WARNING/ERROR.
- set_state round-trip via debugfs on twsi0_clk: clean.

Hardware qualification for patches 0008/0009 and the ESOS 0001-0006 series
is therefore CLOSED on v12 evidence (supersedes the v11 rate-0 caveat: the
placeholder-opacity issue was the 0006 lookup bug, fixed and now proven).

## v12 payload verification addendum — 2026-11-20 (live, firmware-DSDT boot)

Payload: edk2 9ef6a15f (0010 promotion + 0011 audit fixes), ESOS 37533b27
(clk framework rework: clk_get_enabled tri-state, clk_hw_get_ops,
rate-capability APIs). First boot with NO GRUB DSDT override — the
firmware's own DSDT describes everything.

Verified live (serial console):
- Boot health: full RHEL, zero BUG/WARNING/ERROR; SPCR console active.
- RHCT HWCAP (0011 fix PROVEN): /proc/cpuinfo isa now carries the full
  X100 set — zicntr zicond zicsr zifencei zihintpause zihpm zfh zfhmin
  zba zbb zbc zbs zkt zvbb zvbc zve* zvkb..zvkt svinval svnapot — vs the
  v12-pre-0011 RHCT subset. All 8 harts report identically.
- _OSC (0011 fix PROVEN): "platform does not support [PCIeHotplug PME AER
  LTR DPC]" — the real firmware-supported mask (PCIeCapability only) is
  what the OS now sees. PCIe still enumerates (NVMe root on MSI-X).
- RPMI clocks: all real rates (ufs_aclk 491.52 MHz, emac0_bus 307.2 MHz,
  twsi0 31.507692 MHz, gpio 24 MHz, sdh0 204.8 MHz) — ESOS framework
  rework boot-clean.
- Peripherals from the firmware DSDT (no override): 7 tsensor zones
  51-55C, EC registered (fan path), 24c02 EEPROM on i2c-PRP0001:08,
  GMAC DHCP up.
- cpuidle: correctly ABSENT — _LPI is patch 0012 (the v13 cycle); no
  half-state shipped.

Remaining for v13: _LPI states (checklist in docs/v13-boot-checklist.md).
