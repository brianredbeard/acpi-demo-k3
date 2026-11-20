# Linux master audit vs our 6.12 carry set — 2026-11-19

`/home/bharring/Projects/linux` master = `v7.4-rc3-178-g20eef29b7c84`.
Board/builder baseline: RHEL 6.12.0-284.el10 + linux-kernel-test.patch + our
local patches. This audit lists upstream changes that touch our firmware
contracts or carried patches, and which are worth backporting to the RHEL 6.12
tree. Backports are assumed feasible for RHEL as long as they're called out
here and picked deliberately.

## Findings that affect what we ship

| # | Upstream change (master) | Impact on us | Backport-worthy for RHEL 6.12? |
|---|---|---|---|
| 1 | `ACPI_DBG2_RISCV_SBI_CON` (0x15, "sbi" console) present in spcr.c + actbl1.h (landed post-6.12) | Our `Spcr.aslc` has a ready `SPCR_TABLE_TYPE 2` (RISC-V SBI console) variant that is a no-op (-ENOENT) on 6.12. Firmware patch 0008 stays on type 1 (16550-with-GAS), which 6.12 handles | **Yes if we want SBI-console fallback**: backport spcr.c's `case ACPI_DBG2_RISCV_SBI_CON: uart = "sbi"` + the actbl1.h define. Small, self-contained. Only useful for kernels that use the SBI console; our RHEL target has `HVC_RISCV_SBI` disabled, so low priority |
| 2 | `dwmac-spacemit.c` upstream fixes (Inochi Amaoto, Jun 2026): correct MII/RMII interface FIELD_PREP model (`d1e3a4c3b24d`) and LPI/WAKE IRQ bits (`bf5cd5d4ca42`: BIT(9)=LPI, BIT(12)=WAKE) | **Our ACPI patch already carries both** — `dwmac-spacemit-acpi.c` has GENMASK(4,3) interface model and CTRL_LPI_IRQ_EN BIT(9)/CTRL_WAKE_IRQ_EN BIT(12). No action | Already aligned |
| 3 | clk: spacemit k3 fixes: USB2 bus clock enable bit BIT(1) (`51ed53630915`), UFS aclk parents corrected (`7a588b62679c`: pll1_d5/pll1_d6/pll2_d6/pll2_d5), UFS refclk added (`8abba78dc0ee`), i2s topology/divider fixes, CPU PLL rate tables | **Validates the ESOS CCU port committed today**: patch 0003 was written from master's post-fix state (usb2 BIT(1), corrected UFS parents, ufs_refclk pll1_d64_38p4/2). Upstream i2s/CPU-PLL changes are not in our RPMI consumer set; no action | No backport needed (RHEL 6.12's own ccu-k3.c is the consumer side under DT; ACPI consumers use our RPMI service) |
| 4 | riscv: dts: spacemit k3: `riscv,num-guest-ids = <63>` fix (`f6cdb40f4b2f`, upstream 69f95409f005) | Our vendored OS DT and MADT both already use 63 guest IDs / guest-index-bits 6 — matches the corrected upstream. KVM live evidence: "AIA available with 7 guest external interrupts" (63 guest IDs ⇒ GEILEN 7). No action | No |
| 5 | `ARCH_HAS_ACPI_TABLE_UPGRADE` enabled on RISC-V (`6a48dea3449c`) | initramfs `acpi_table_upgrade` overrides become possible on RHEL rebases; today we rely on GRUB `acpi` overrides. Documented behavior change for our experiment flow | **Yes on next RHEL rebase**: no action needed in our patches; just stop saying "table upgrade unavailable on riscv64" |
| 6 | drivers/acpi/riscv/cppc.c — SBI CPPC extension (SBI_EXT_CPPC, FFH types SBI/CSR) and cpuidle.c `_LPI` FFH validation (bits[63:60]=1, [59:32]=0, [31:0]=SBI power_state; `riscv_sbi_suspend_state_is_valid`) | This is the kernel-side contract for our Task 9 `_LPI` and future CPPC work. **Confirms the DSDT Cpu.asl `CPPC_ENABLE` scaffolding approach is right**: FFixedHW registers with `(1ULL<<60)|SBI_state` encodings. The plan's `_LPI` encoding note matches this code exactly | **No backport needed — verified**: RHEL 6.12 target config has `RISCV_SBI_CPUIDLE=y`, `ACPI_PROCESSOR_IDLE=y`, `CPPC_LIB=y`; the riscv ACPI cpuidle backend is part of `drivers/acpi/riscv/`. Kernel side is ready for Task 9 `_LPI` AML |
| 7 | No upstream MCFG ghost-filter quirk for SPMT/K3 exists on master | Our kernel-side MCFG ghost filter (type-0 TLP filtering on bus 0) remains a local patch; no upstream resolution to adopt | Keep carrying; revisit upstreaming via `mcfg_quirks[]` with OEM ID matching once stable |
| 8 | 8250_platform RSCV0003 remains the plain 16550A binding on master (no XScale quirk upstream) | Our compatible-gated XScale fixed-type quirk remains local. The firmware DSDT now declares the compatible (patch 0008), so a future upstream submission of the quirk + binding is coherent | **Upstream submission candidate**: quirk is clean (gated on _DSD compatible, mirrors the vendor DT binding `intel,xscale-uart`). Not a backport — a 6.12→upstream direction |
| 9 | dts: spacemit k3: CLINT→ACLINT replacement, USB3 B/C, rfkill, COM260 USB additions on master | DT-mode only; our ACPI path describes these via DSDT when they're enabled. COM260 USB nodes matter when we extend the COM260 profile | No (DT-side) |

## RHEL backport shortlist (in priority order)

1. **`drivers/acpi/spcr.c` + `include/acpi/actbl1.h`**: RISC-V SBI console
   (type 0x15) support — only if we adopt SPCR_TABLE_TYPE 2 as a fallback
   console for SBI-console kernels. Tiny patch; call out when picked.
2. **`drivers/acpi/riscv/cpuidle.c` presence check on the RHEL 6.12 tree** —
   gates Task 9 (`_LPI`). If missing, backport the riscv ACPI cpuidle backend
   (Ventana) before any DSDT `_LPI` work, per the plan's Task 9 checklist.
3. Not needed: dwmac-spacemit fixes (already carried), clk fixes (consumer is
   our ESOS RPMI service, aligned to master), IMSIC DT fix (already correct).

## Upstreaming candidates from our side

- MCFG ghost-filter quirk (`drivers/acpi/pci_mcfg.c`, OEM-matched).
- 8250 XScale compatible-gated fixed-type quirk
  (`drivers/tty/serial/8250/8250_platform.c`) + the `intel,xscale-uart` _DSD
  binding (now declared in firmware, patch 0008).
- dwmac-spacemit ACPI platform-data path (fwnode APIs, optional clocks,
  _DSD APMU regs) — extends the upstream driver Inochi maintains.

Sources verified on master v7.4-rc3: spcr.c, actbl1.h, 8250_platform.c,
pci_mcfg.c, dwmac-spacemit.c (log), drivers/clk/spacemit/ccu-k3.c (log),
drivers/acpi/riscv/{cppc,cpuidle}.c, arch/riscv/boot/dts/spacemit/k3.dtsi.
