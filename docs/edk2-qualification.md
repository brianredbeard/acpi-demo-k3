# Selecting and qualifying a Pico EDK2 candidate

`python3 edk2_release.py package` prints the candidate's **installer manifest
SHA-256**. Save that literal value alongside the build and test plan. Supply
it independently to each subsequent command, including after copying a bundle.
The manifest covers the installer payloads, isolated build manifest, FIT node
comparison and PCIe artifact checks. The baseline's original manifest and
provenance belong to the baseline and are archived under `provenance/baseline/`.
Choose the baseline SHA-256 from your retained qualified release record and
the full platform commit from the experiment's test plan.

For example, the `pico-acpi-v8-1` transaction verified the EDK2 payload
`055f355a5e720585dfaee0225b5d0030ff0b559197dfc78bcd714143bd3d45b6`.
It matched `out-v8b`, built from `392fc857`. Both the packaged PCD and AML
still described buses 0–0 on segments 2 and 4. The EFI shell showed a bus
allocation on segment 0 and empty resource lists on the two added roots.
The bus-range experiment requires commit `b25849e1` and a packaged bus-limit
check of `0xff`. This distinction matters when interpreting the boot log.

Host verification on 2026-11-22 produced diagnostic FIT
`45668dad2b6f3361628fb77cacf469e3ae2ad5a2c4489ffa89e26c646fb1dd6e`
from `b25849e1`. Its PCD and AML both cover buses 0–255 on segments 2 and 4.
The packaged PCI bus and host bridge drivers passed the full serial trace
checks. The release verifier rejected its I/O windows on both segments.
Hardware evidence of the first failed PCI allocation and subsequent RHEL
boot qualification are still outstanding.

In a separate host test, two clean RELEASE builds of `392fc857` with the
same PCI resource test patch produced byte-identical FDs and FITs in
different workspaces. The FIT SHA-256 was
`f4193fb1d794b3a97b41cff08f8ff8e922ec1051c39e36e7ba8038c4f5255d67`.
Installer inspection passed, and its offline plan against the v4 readback
selected only the EDK2 region.

The subsequent `pico-acpi-v9d-1` transaction verified an EDK2-only write on
Pico serial `HW4MPK3161280211`. The EDK2 slice of the NOR readback matched
FIT `1562130897e2bbe726d1765905e3847a32c4349e0cf9b41aaaf21a0c9bb2a2e1`
from platform commit `70030665`. On reboot, PCIe links 0, 2 and 4 came up.
The first PCI failure was in host bridge initialization on segment 2.
`GetIoSpaceDescriptor` returned `EFI_NOT_FOUND` and `PciHostBridgeDxe`
asserted at `PciHostBridge.c:210`, before endpoint enumeration. The CPU HOB
specifies a 32-bit I/O space. The host I/O windows start at `0x1200010000`
and `0x12c0010000`, outside that map. Both PCI-side windows passed the
existing static profile. The single-variable test is to extend the declared
I/O address width to cover the highest translated byte (37 bits minimum),
then check root registration, allocation, NVMe Block I/O and RHEL boot in
order. The width change has not been hardware-qualified in this transaction.

The next verified flash, `pico-acpi-v10d-1` (platform `4ab33819`, FIT
`94752dbbb0fa10c65d7c1a619b9a28b2863ef530f1535c8661151e2881e40785`),
tested explicit GCD I/O registration with the same 32-bit width. In the
serial capture both `GCD:AddIoSpace` calls, at `0x1200010000` and
`0x12c0010000`, returned `Unsupported`. DXE printed the I/O map as
`NonExist 0000000000000000-00000000FFFFFFFF`. The new registration loop
discarded both return values. Segment 2 then hit the same `Not Found`
assertion. This transaction leaves the address-width test outstanding.

```sh
python3 edk2_release.py package --build "$BUILD" --baseline "$BASE" \
  --expect-platform-revision "$PLATFORM_COMMIT" \
  --baseline-sha256 "$QUALIFIED_BASELINE_SHA256" --destination "$BUNDLE" \
  --installer "$INSTALLER" --reason "$CHANGE"
```

## Operator flash and offline readback

Use the `k3-firmware` executable from the installer checkout for
`$INSTALLER`. Before a boot test, verify board and builder roles, active jobs,
the intended kernel release, mounted root device, modules, initramfs and boot entry as described in
AGENTS.md. Commit the firmware changes before flashing. In FDL mode, with the
Pico-ITX physically identified and a new private transaction path selected,
the operator runs the following command. Supply the literal digest saved at
packaging as `$CANDIDATE_SHA256`.

```sh
sudo python3 edk2_release.py flash --board pico-itx --device usb:3-3.3 \
  --bundle "$BUNDLE" --expect-sha256 "$CANDIDATE_SHA256" \
  --installer "$INSTALLER" --backup-dir "$TRANSACTION"
```

The wrapper runs installer inspection, takes the installer's host lock,
checks the manifest and loaded payloads, and requires exactly one EDK2 write
in the installer's plan for the live NOR. The serial prompt authorizes that
plan. The operator may pass `--yes` for the same digest and device selection.
The installer engine saves the initial NOR, verifies staged RAM, and compares
the full NOR after the write. Preserve the transaction for readback and
rollback. If a test image fails and RPMI is unavailable, reboot can hang and
recovery may require a manual power cycle.

Readback runs at the end of the flash and can also be repeated offline with
permission to read the installer's private transaction files.

```sh
python3 edk2_release.py readback --bundle "$BUNDLE" \
  --expect-sha256 "$CANDIDATE_SHA256" --transaction "$TRANSACTION"
```

The receipt identifies the serial, manifest, EDK2 image, before and after NOR,
and `report.json` by digest. Readback also verifies unchanged bytes outside the
EDK2 write and matches ESOS and OpenSBI to the selected candidate. Retain the
receipt and begin one normal cold boot of this board with boot-time capture
already active.

## Boot evidence

Save the continuous serial capture and any Linux output in an evidence
directory outside the immutable candidate bundle. The operator reviews the
actual boot path, including which EFI entry ran and which NVMe partition it
used. A menu listing or available fallback entry alone cannot establish a
successful RHEL GRUB launch. Preserve entry selection, device paths or
partition GUIDs, the kernel and initramfs loaded, the actual ACPI boot mode,
and the resulting root mount. Record unresolved devices in the handoff.

Create `boot.json` in the evidence directory using this schema. Substitute
values from the readback receipt and from that same boot. Each `quote` is
copied from the named capture. The matching accepts raw text or the displayed
text with ANSI SGR color escapes removed and CRLF/CRCRLF converted to LF.
The record hashes the original capture bytes. A milestone can take one
excerpt object or an ordered list of them, including excerpts from different
captures of the same boot.

```json
{
  "bundle_sha256": "<selected manifest SHA-256>",
  "report_sha256": "<installer report SHA-256>",
  "serial": "<readback serial>",
  "operator": "<name>",
  "same_boot": true,
  "boot_id": "<Linux boot UUID>",
  "kernel_release": "<uname -r>",
  "root_source": "<findmnt -nro SOURCE />",
  "nvme_disk": "<backing whole disk, e.g. nvme0n1>",
  "milestones": {
    "segment2_io": {"file": "console.log", "quote": "<segment 2 I/O allocation>"},
    "segment4_io": {"file": "console.log", "quote": "<segment 4 I/O allocation>"},
    "nvme_block_io": {"file": "console.log", "quote": "<EFI Block I/O handle and NVMe path>"},
    "rhel_grub": [
      {"file": "console.log", "quote": "<actually selected RHEL entry and NVMe path, EFI alias or partition GUID>"},
      {"file": "console.log", "quote": "<RHEL GRUB execution>"}
    ],
    "running_root": {"file": "linux.log", "quote": "<boot UUID, kernel, os-release ID, root mount and NVMe ancestry>"}
  }
}
```

For each PCI segment, retain the EDK2 `RootBridge: PciRoot(0x2)` or
`PciRoot(0x4)` header and its successful `I/O: Base/Length/Alignment` row.
An assigned endpoint I/O BAR listing with its PCI domain can also document
the allocation. Preserve enough surrounding output to distinguish firmware
assignment from later OS reassignment. For Block I/O retain the `BLK` handle
and NVMe path. For the RHEL boot, identify the executing GRUB and link its
path to NVMe directly or by matching the EFI Shell alias or GPT partition GUID
in the Block I/O evidence. For the running root, capture the command
`findmnt -nro SOURCE /` and its output or a mount row containing
`/ <source>`. For a device-mapper root also capture the literal command
`lsblk -snro KNAME -- /dev/mapper/rhel-root` (substituting the observed root
path) and its single-column output through the backing NVMe namespace. Capture
either the EDK2 “BdsDxe: starting Boot…” RHEL line or the actual
`efibootmgr -v` BootCurrent and matching RHEL Boot entry. Capture
`cat /proc/sys/kernel/random/boot_id`, `uname -r`, and `cat /etc/os-release`
in the same session.

```sh
python3 edk2_release.py qualify --bundle "$BUNDLE" --expect-sha256 "$CANDIDATE_SHA256" \
  --transaction "$TRANSACTION" --expect-kernel "$PLANNED_KERNEL" --expect-root "$PLANNED_ROOT" \
  --evidence "$EVIDENCE" --output "$QUALIFICATION_JSON"
```

The fresh output file records operator-attested qualification for those
milestones, the installer receipt, submitted observations, and hashes of
each raw capture. Keep the raw captures with the record. Partial boot logs,
serial output from another boot, or a successful Ubuntu fallback leave RHEL
qualification pending.
