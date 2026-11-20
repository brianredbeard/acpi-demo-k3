# UFS (with the real clock) and Display — next-step plan

Live-board ground truth (v12 boot, 2026-11-20):
- UFS: absent from the DSDT (0 mentions); no dmesg; root is NVMe. The RPMI
  clock service now serves ufs_aclk = 491.52 MHz (truth; kernel fallback
  constant is 409.6 MHz — 20% off).
- Display: NO framebuffer reaches the kernel (no simpledrm/efifb/sysfb;
  /sys/class/graphics has only fbcon). The firmware HAS a GOP
  (LcdGraphicsOutputDxe + LcdDpDxe in the DSC) but nothing hands it to the
  kernel under ACPI. Native DRM needs the full DT-of_ component stack.

## UFS (Task 7) — the clock is ready; the bridge is platform data

The kernel driver stack: ufs-spacemit.c -> ufshcd_pltfrm_init ->
ufshcd-pltfrm.c. The pltfrm layer reads EVERYTHING via of_ (clock-names,
freq-table-hz, lanes-per-direction, operating-points-v2, regulators) and
the spacemit vops additionally takes an exclusive reset control. Under
ACPI: dev->of_node is NULL, so clock list is empty -> sys1clk_1us falls
back to UFS_AXI_CLK_LOW_FREQ_HZ (409.6 MHz) while the hardware runs
491.52 MHz -> 20% timing skew in PA_LINK_STARTUP_TIMER programming.

Order of work (kernel side, one patch series):
1. ufs-spacemit ACPI platform-data path (mirrors the proven dwmac-spacemit
   pattern): fwnode/device_property for lanes-per-direction, clocks via
   the clkdev aliases (clk_get(dev, "axi") / "ref" -> ufs_aclk/ufs_refclk,
   the RPMI service), _DSD spacemit,apmu-style absolute regs for the
   reset assert (RESET_APMU_UFS_ACLK lives in the same CLK_RES_CTRL the
   CCU already owns), or assert via the RPMI set_state on ufs_aclk.
2. DSDT: UFSHC device — PRP0001 "spacemit,k3-ufshc", _CRS MMIO
   0xc0e00000/0x40000 + GSI 135, _DSD lanes-per-direction 2, freq-table
   (491.52 MHz / 19.2 MHz — the OPP truth), clock references by name.
3. Firmware clock side: NOTHING more needed — ufs_aclk/ufs_refclk are
   already in the RPMI consumer set with the corrected field values
   (the 0005 transposition fix). The ESOS gate state is real now.
4. Guard the sys1clk fallback: if the "axi" clock resolves, the value is
   the truth; log loudly when falling back so a future ACPI regression
   cannot reintroduce the 20% skew silently.

Verification: link startup at gear with correct sys1clk, repeated reads
(keep NVMe root; UFS is a data test target), IRQ 135 delivery.

## Display (Task 8) — split: firmware-GOP handoff first, native DRM later

Phase 1 (small, high value): give the kernel the firmware framebuffer.
- The firmware GOP already sets a mode at boot (HDMI via Inno DP).
- Under ACPI the standard mechanism is the simpledrm + sysfb path fed by
  the EFI framebuffer: the kernel needs CONFIG_SYSFB / efifb-style
  handoff. On this DT-less ACPI boot the EFI GOP memory is described by
  the EFI memory map (BOOT_SERVICES_CODE/DATA, or an EfiLoaderData
  region); simpledrm's EFI path expects a "simple-framebuffer" DT node OR
  the sysfb EFI firmware node. Verify what 6.12 riscv supports:
  check efi_init -> memory map QEMU-style fb detection; if absent, the
  DSDT can declare a display device with _DSM/simplefb-style _DSD
  (width/height/stride/format + reg) for simpledrm's platform-data path.
- Deliverable: console on HDMI before native DRM. Low risk (no clock or
  reset programming - the firmware already powered the pipeline).

Phase 2 (large, separate): native DRM (spacemit DPU + Inno DP).
- Driver stack is component-based with of_ graph endpoints (remote
  endpoint wiring), 5-7 named clocks, 5 resets, PHY, panel/bridge
  discovery. Porting plan Task 8 exists and is honest about size.
- Clocks: NONE of the display clocks (LCD pxclk/mclk/aclk/escclk/dscclk,
  EDP0/1 pxclk, DSI4LN2 variants) are in the RPMI consumer set. That set
  was deliberately consumer-relevant-only; display needs its own decision:
  firmware-fixed single mode (Phase 2a: firmware programs rates via
  EDK2 ClockDxe before handoff; kernel does no rate changes) vs. adding
  display clocks to the RPMI ABI (Phase 2b: append-only new ids).
  Phase 2a first - matches the porting plan's "single fixed firmware
  mode can be a separate limited experiment".
- The DSDT graph representation problem (drm_of_crtc_port_mask etc.)
  needs the binding-spike design work the plan already scoped.

Sequencing recommendation: UFS first (the clock truth is already live and
the dwmac pattern is proven), display Phase 1 alongside it (independent,
different subsystem), display Phase 2 only after the binding spike.
