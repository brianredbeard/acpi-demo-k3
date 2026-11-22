# FlashFvbDxe VA-change regression — bisect post-mortem (2026-11-22)

## Symptom

rhct10 (and rhct10-nobrs) hang at the GRUB→kernel handoff: no
kernel output at all (not even the EFI stub line), no ssh, power
steady at ~15W (hard hang, not a crash loop). The BdsDee ERROR
C40000002 line seen alongside is PRE-EXISTING platform noise
(Nov 12 logs show it with healthy boots — vendor default boot
option absent; benign).

## Bisect (each variant = rhct8 base + one rhct10 commit,
single-variable edk2.bin flashes via the BROM-window catcher)

| variant | commit | boot |
|---|---|---|
| rhct8 (control) | — | OK |
| rhct8+PCI-03/04 | fa761952 | OK |
| rhct8+_OSC | 5880d429 | OK |
| rhct8+FVB | 38070cc6 | HANG (reproduces rhct10 exactly) |
| rhct10-nobrs (BRS disabled) | all but BRS | HANG |

Exonerated: K3BrsCheckDxe (disabled variant still hung), PCI-03/04,
_OSC. CONVICTED: 38070cc6 (FlashFvbDxe VA-change).

## Mechanism

The FVB driver services the UEFI variable store (FW_ENV_REGION).
The board boots via GRUB's LEGACY path (bare `linux` command —
no EFI stub): GRUB calls ExitBootServices + runtime GetVariable
around the handoff; the kernel's early EFI-runtime bring-up then
hits FVB after SetVirtualAddressMap. The reworked callback
(38070cc6) converts mFlash and the instance table — but the
platform's virtual map makes those converted pointers (or the
member-conversion order) wrong at runtime access = hang before
the first kernel print.

The ORIGINAL defect the patch tried to fix (converting MMIO
scalars DeviceBaseAddress/RegionBaseAddress) was REAL but
BENIGN on this platform: the K3 virtual map is (near-)identity,
so "garbage" converted scalars land on the same physical
addresses. The "fix" traded a latent defect for a live one.

## Fix direction (next firmware cycle)

The VA-change callback should be a NO-OP on this platform
(identity virtual map): runtime FVB access keeps working on the
physical addresses captured at init. The scalar-conversion
defect gets fixed by NOT converting them (already true in the
patch) WITH also not converting the protocol pointers (revert
to the vendor callback's semantics), OR by gating the whole
callback on a non-identity map check. Patch 0012 in the next
series; rhct11-wifi must be REBASED off rhct8 + BRS + _OSC +
PCI-03/04 WITHOUT the FVB commit until the callback is reworked
and runtime-qualified (a non-identity virtual-map write test
was the audit's open gap — this hang is exactly that gap
arriving).

## Operational notes

- Bisect rig: BROM-window catcher (fastboot poll + flash +
  `fastboot reboot`), ~4 min per cycle incl. boot verdict.
- Fastboot flag consumption: a successful `fastboot reboot`
  CLEARS the PMIC flag — later re-entries need k3-enter-fastboot
  from a running system or FDL-hold power-on.
- The `sg k3flash` group trick (session lacks the group after
  the k3flash group add — use /usr/bin/sg k3flash -c "...").
