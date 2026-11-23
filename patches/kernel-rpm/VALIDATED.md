# Kernel patch validation ledger (el10-284 cycle 2/3)

Single source of truth for each staged patch's verification state.
Update on every state change. "Preflight" = compiled as .o/.ko in
a prepared tree (builder's build-5 tree or the board's kernel-dev
rig). "Rig-module" = built AND loadable .ko via kernel-dev (loads
only on vermagic-matching kernel).

| # | Patch | Content | Verification | Status |
|---|---|---|---|---|
| 1 | k3-ufs-acpi.patch | UFS PRP0001 probe branch + reset guard | SRPM-built (cycle-2/3 EXIT=0); boot test pending espi fix | STAGED |
| 2 | k3-gpio-acpi-v3.patch | authoritative base + extent validation (#1) + semantics (#2: defer propagation, level rejection, bank_lock, IRQ_NONE) | Preflight PASS (fresh .o verified, builder tree); =y so no rig-module possible | STAGED |
| 3 | k3-espi-acpi-fix.patch (v2 content) | has_acpi_companion gate on DT-range path + unified property reads | v1 preflight PASS but HARDWARE-FAILED (np guard bypassed by synthesized of_node); v2 PREFLIGHT-PASS, hardware test = cycle-3 boot | STAGED (v2) |
| 4 | k3-rfkill-gpio-prp0001.patch | ACPI probe accepts property-described devices (GPS legacy preserved) | Preflight PASS (builder tree); =m, rig-module capable | STAGED |
| 5 | k3-tsensor-acpi-zones.patch | ACPI zone builder: register_with_trips, _DSD thermal-trips override, staggered defaults (ch4 +5C), 8C hysteresis, RW sysfs trips | Preflight PASS; RIG-MODULE BUILT (k3_tsensor.ko, 5.3s) — load test on next acpidebug boot | STAGED |

## Rig validation round (2026-11-23, kernel-dev)

All five patches rig-validated in ~30s total (vs hours of mock
cycles). The rig is now the PRIMARY validator; mock/rpmbuild
is the INTEGRATION test (packaging + built-in linking + the
boot), run when a patch set is ready — not per-iteration.

| patch | rig result | binary-level evidence |
|---|---|---|
| tsensor-acpi-zones | k3_tsensor.ko (5.3s) | module linked, vermagic-match |
| rfkill-gpio-prp0001 | rfkill-gpio.ko (5.5s) | module linked, vermagic-match |
| ufs-acpi | ufs-spacemit.ko (rig's own prior build + verified) | module linked |
| espi-v2 | .o (5.4s, =y) | **DISASSEMBLY: parse_dt+0x8e jalr is_acpi_device_node + beqz guard** — the v2 gate is in the object (the v1 lesson: source-level verification was insufficient; the object is the proof) |
| gpio-v3 | .o (5.1s, =y) | **nm: _raw_spin calls present** (bank_lock compiled in) |
| ecam-segs-2/4 series | newfile .o COMPILED CLEAN (rig) | object symbols: dw_pcie_prog_outbound_atu + pci_generic_config_*; mcfg/makefile patches apply roundtrip (mechanically generated) | STAGED — needs the K1 config + hardware test on a cycle-3+ boot |
| 6 | build5-authoritative (tracked, not shipped) | the base gpio patch build 5 actually compiled (data defs relocated) | provenance record — the bad-regeneration discovery | REFERENCE |

## Firmware-side staged (edk2-platforms commits, not flashed)

| Commit | Content | State |
|---|---|---|
| cdfda4a4 | TSEN _DSD thermal-trips (staggered per-channel) | next firmware cycle |
| 2f7e4ef7 + 6afa9ede + ff348957 + 392fc857 + b25849e1 | the rhct12 wifi stack (already flashed + qualified on the board) | SHIPPED |

## Verification legend

- SRPM-built: in a mock/binary that reached EXIT=0
- Preflight PASS: single-file compile in a prepared tree,
  FRESH object verified by mtime+hash (the stale-.o lesson)
- RIG-MODULE: k3_tsensor.ko-style — built in kernel-dev,
  loadable on the vermagic-matching kernel
- Hardware: booted and behaved on the board

## The load-test queue (once cycle-3 boots)

1. espi-v2: the boot itself (no panic past 2.9s)
2. tsensor: insmod the rig-built k3_tsensor.ko → zones with
   staggered trips + RW sysfs → trip tuning without reflash
3. rfkill: rfkill list shows WLEN/BTEN

| 3 | k3-espi-acpi-fix.patch | **v3**: v2's parse gate + the populate gate (devm_of_platform_populate fails -EINVAL on the synthesized node under ACPI; the failure path ran err_assert_resets, resetting the controller out from under the EC child bind — cycle-3 field result: hard hang at 2.73s mid-8250-init, no panic, espi probe failed -22 immediately prior). Under ACPI the DSDT-declared EC0/PWM0 children enumerate via the ACPI bus; the DT populate error is informational. | RIG .o DISASSEMBLY-VERIFIED: .L318 error path calls is_acpi_device_node then branches AWAY from dev_err_probe for ACPI nodes; v3 patch applies clean to the independent 264 pristine base and reproduces the rig-built source exactly | **cycle-3 boot: PANIC GONE (v2 worked), HANG REMAINS (v3 needed)** — v3 rig-built, awaiting cycle-3b |
| 6 | k3-8250-xscale-quirk.patch | The compatible-gated PORT_XSCALE fixed-type quirk (RECONSTRUCTED from the build-5 work; the cycle-3 SRPM chain had dropped it): plain RSCV0003 + UPF_BOOT_AUTOCONF runs bank-switching autoconfig on the K3 XScale-derived DW 16550, wedging the console mid-print — the 2.66-2.73s freeze on cycles 3/3b, reproducible with cpuidle.off=1 (idle hypothesis disproven). Gated on the _DSD compatible intel,xscale-uart (firmware 0008's binding): fixed type, no autoconfig. | Rig .o built (device_property_match_string verified in the object); patch applies clean to the pristine 264 base; cycle-3c carries it | **cycle-3b boot: HANG PERSISTED with espi v3 GOOD + cpuidle.off=1 — the UART quirk was the missing piece (the rpmi-clock doc's 'SPCR + XScale quirk pair is proven' was the prior closure)** |
