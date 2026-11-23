# FlashFvbDxe VA-change regression — bisect post-mortem (2026-11-22)

**November 23 correction.** The handoff bisect below stands. The later Pico
runtime test measured physical flash at `0xb8000000` and its Linux virtual
mapping at `0x20200000`. The callback from `ee82b38f` recovered boot but left
runtime nonvolatile writes broken. The identity-map explanation and no-op
recommendation below are historical. [Measurements and candidate qualification](fwts-17-failures-triage-2026-11-23.md#scratch-variable-persistence-test-on-rhct13)

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

## Update: v2 field result — ECAM ghost multiplication, NVMe lost at BDS

rhct11-wifi-v2 boots (FVB fix holds) and the kernel sees
0002/0004 devices — BUT:

- The FIRMWARE's PciBus shows ghost multiplication on ALL
  segments (NVMe 1DEE:5216 at fn 1B-1F; 10EC:8127 and 10EC:B852
  duplicated across fn 00-1F): the 3-entry MCFG with bus 0-0xFF
  declarations against 0x10000 compact ECAM windows makes the
  firmware misdecode — reads wrap/alias.
- NvmeDxe never binds → no NVMe block device at BDS → Boot0007
  (redhat, HD(NVMe ESP)) unresolvable → BDS falls through to
  Ubuntu (UFS). This is the "grub entries gone" regression —
  the entries are intact; the NVMe vanished from firmware view.
- rhct8 worked because its single-segment MCFG produced the
  same ghosts on seg 0 but PciBus still assigned the root port
  + NVMe (the k3_dw_ecam kernel quirk cleaned up the OS view).

### Fix direction (next firmware cycle)

Segments 2/4 must NOT get standard-MCFG entries against the
compact 0x10000 windows. Options: (a) MCFG EndBus=0 only and
accept bus-1 device access via the DSDT _CRS + kernel quirk
path; (b) enlarge firmware ECAM windows to full 1MB/bus where
the address map allows (seg 4's window region may have room);
(c) drop the seg-2/4 MCFG entries entirely and let the DSDT
_RESOURCES + the kernel's k3_dw_ecam quirk handle config
access (matches how DT boots worked — the quirk IS the DT
pcie-spacemit behavior ported). Option (c) is the lowest-risk:
it restores rhct8's exact seg-0 MCFG and moves ALL multi-
segment handling to the kernel quirk (already queued for the
acpidebug kernel).

## FINAL ROOT CAUSE — I/O-BAR resource conflict (2026-11-22, v6ds2 full trace)

The complete evidence chain from the unfiltered DEBUG trace
(2.98 GB serial capture, /tmp/k3-serial-full.log):

1. Ports C/E enable → links train on all three segments.
2. PciBusDxe discovers exactly the real devices (root ports
   [00|00|00] + endpoints [01|00|00]); the UEFI shell's 32
   device-number aliases were DISPLAY-ONLY (shell scan vs
   allocator scan difference).
3. RTL8127 (seg 2) and RTL8852BE (seg 4) each request a
   256-byte I/O BAR → 4 KiB bridge window needed.
4. Every root bridge defined ZERO I/O aperture (BRS AML_020
   "SHOULD NOT be defined" was followed literally).
5. Both I/O allocations fail "Out Of Resource!" →
   PciHostBridgeResourceConflict ×3 → roots torn down →
   segment 0's successful NVMe memory allocation ROLLED BACK
   → "Connect: PciRoot(0x0): Not Found" → no NVMe at BDS →
   BDS falls through to UFS Ubuntu.
6. Secondary defect observed: after the seg-2 rejection,
   empty (zero-length) MMIO submission → repeated "Invalid
   Parameter" retries — recovery-path noise, distinct from
   the primary failure.

FIX (v7, commit 392fc857): 1 MiB I/O windows on segs 2/4,
PCD + DSDT QWordIo, mirroring the DT's pcie2_rc/pcie4_rc I/O
ranges. AML_020 deviation documented in-source.

This also closes the arc: v3 (3-seg MCFG), v5 (+x2 pinning),
v6 (+bus-0 ranges) all failed identically because none
touched I/O. v4 (ports off) never reached the I/O requests.

## Build defect: stale structured-PCD cache (v7 flash tested nothing)

The first v7 flash failed to Ubuntu — but byte-level inspection of
the flashed NOR's DXE PCD database showed Io.PciSize=0 and
BusLimit=0xFF on segments 2/4: the Nov-20 cached PCD database
(PcdValueInit + GlobalVar blob) survived three builds; the DSC
edits never reached the image. The boot-menu 3s timeout and
absent OOR lines in that boot were the OLD config's behavior
under new code.

DISCIPLINE (added to the loop): after any structured-PCD DSC
change, wipe Build/<flavor> PcdValueInit + GlobalVar* (or the
whole Build dir), rebuild, and VERIFY the values in
DXEPcdDataBase.raw + the decompressed DXEFV before staging a
flash. Never trust an incremental build for structured-PCD
changes.

## RESOLUTION — rhct12-wifi release candidate (2026-11-22)

The wifi/10G boot-blocker arc is CLOSED. Hardware-verified fix
stack (each layer found by its trace, fixed, and confirmed):

1. I/O windows on segments 2/4 (392fc857) — the Realtek
   endpoints' 256-byte I/O BARs need apertures.
2. Full bus ranges restored (b25849e1) — bus-0 limits refuse
   PciBusDxe's bus-1 allocation and kill all enumeration.
3. PCD/DSDT windows aligned, PCI base 0 (2f7e4ef7).
4. GCD I/O pre-registration (4ab33819) — translated host
   addresses need GCD descriptors before AddIoSpace's
   intersection.
5. PcdIoAddressWidthMax 32→40 (6afa9ede) — the platform's GCD
   I/O space was 32-bit; the windows at 0x1200010000+ are
   37-bit. (SV39 note: GCD bookkeeping only; SV39 constrains
   VAs, not PAs.)

v11d (diagnostic) proved: all three endpoints enumerate
(NVMe 1DEE:5216 seg0, RTL8127 10EC:8127 seg2, RTL8852BE
10EC:B852 seg4 — first firmware enumeration of the NIC and
Wi-Fi ever) and RHEL GRUB loads from NVMe.

v12/rhct12-wifi (RELEASE, ff348957, edk2 sha 6bbaf411):
booted, logged in, full regression green — kernel dbg1,
NVMe 3 devices, EC registered, zero -517, 3 LPI states,
fwts 47/0.

Remaining for full wifi/10G function (kernel-side, staged
for the acpidebug RPM): the k3_dw_ecam quirk for segs 2/4
OS enumeration + CONFIG_RFKILL_GPIO for the radio-enable
line.

## cc20c30 validation (2026-11-23, pre-flash)

Built from the recipe (edk2-platforms 8b171654 + 0001-runtime-flash)
with the workspace retained; validated host-side:

- **PCIe profile check passed** (the extended memory-triple checker
  over the built FIT)
- **test_efi_flash_runtime: 3/3 groups pass** against the built
  driver sources (the harness #includes the production
  FlashFvbDxe.c / SpiNorFlashDxe.c / STQspiDxe.c — not twins):
  fvb (nonidentity/identity/high-va/missing-spi/missing-region),
  nor (nonidentity/missing-map/program-timeout/enable-timeout),
  controller (nonidentity/missing-map/sfar-timeout/reset-timeout)
- **Full suite green** with the cc20c30 ITB as the FIT target

Comparison to the flashed rhct13 (13024d13): distinct payload
(1b7aa316) differing by exactly the runtime-flash patch — the FVB
SetVirtualAddressMap pointer conversion (EfiConvertPointer on the
instance + flash ops), the runtime-pool zeroing, the QSPI
status-check fixes, and the VariableRuntimeDxe store-pointer
comparison. Same lower layers; same DSDT content (both from
8b171654).

**Validation state: host-validated. The board qualification
(nonidentity runtime map exercised by a real OS) requires a flash
cycle — the audit's operator-controlled private-variable
persistence test (write/read/delete across reboot) is the
acceptance gate. Not flashed.
