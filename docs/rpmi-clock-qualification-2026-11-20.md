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
