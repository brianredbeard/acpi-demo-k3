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
