# Pico-ITX F2 platform configuration

The first setup candidate builds on the flashed rhct13 EDK2 revision
`8b17165463eff040bb8f486be0b08416daff9f2b`. The release lock continues
to identify the recovery baseline. This change has its own candidate recipe.

## Implementation and qualification plan

1. Add a native HII formset under F2 → Platform Manager. Take a snapshot
   after SKU selection, distinguish configured resources from observations,
   and display unknown values when firmware lacks evidence.
2. Link the ACPI page to the existing Boot Maintenance Manager timeout
   editor. Its Save and Discard actions operate on the standard EFI
   `Timeout` variable. BDS consumes that value through
   `PcdPlatformBootTimeOut`. Using the existing owner avoids conflicting
   copies, migration logic and writes caused simply by visiting the page.
3. Check the linked formset and its navigation target in the packaged Pico
   firmware. Verify all FIT payloads against the original rhct13 transaction.
   Exercise the page on serial, then cold-boot once with a distinguishable
   timeout and again after restoring the original value.
4. Qualify USB speed and generic PCI configuration access independently.
   They have independent hardware prerequisites and can change boot device
   availability.

The ACPI DSDT extracted from rhct13 hashes to
`915e8d9d86dbd9031b50c466b26f886dfdf3ccd5a94dc4ec08a470e8a9688367`.
Its USB2 controller at `0xc0a00000` publishes a high-speed ceiling.
The Pico board description gives USB3D at `0x81a00000` a SuperSpeed PHY,
and the EFI host driver consumes the per-controller speed mask. The active
AML has no USB3D device. Before offering its speed setting, establish the
physical connector and independent recovery route, qualify an ACPI description
and driver for USB3D, and measure both speeds with the same device and cable.
The speed switch in the BootROM recovery flow exercises a different path.

## Reproduce the ACPI candidate

Run these commands from the integration repository with the pinned SDK archive
and platform checkout available to the existing build wrapper. The destination
must be fresh.

```sh
python3 build_edk2.py --destination build/f2-platform-config-release \
  --recipe recipes/edk2/f2-platform-config/recipe.json \
  --expect-platform-revision 8b17165463eff040bb8f486be0b08416daff9f2b
python3 verify_platform_config.py build/f2-platform-config-release/MUSE-Pico.itb
```

The build checks the compiled PCIe configuration as usual. The form checker
examines the firmware volume inside the selected FIT payload, verifies the
Platform Manager form class and native timeout destination, and reads the
factory timeout from the packaged PCD database. The target board's saved
timeout can differ from this default.

## Host results

| Artifact | SHA-256 |
| --- | --- |
| Original rhct13 installer manifest from the flash receipt | `87e609556895821fa855b899c4b61bc686386c0b01a2716e61f291cbacb07560` |
| F2 candidate installer manifest | `5b267371c60a6285623f82c6cf25fe4b639decbc4c00920e42b98a6b16ca1dc1` |
| F2 candidate ACPI FIT | `f739821539ac999c7e0e61384268202081487bd9bafbf04719204f2283214c91` |
| Firmware-owned DT regression FIT | `eea16a5e247d766ceaa4ff8f7b202512ca27a69dda458cff748196aa13d4f26a` |

The isolated ACPI build passed its PCIe profile. The form checker found the
timeout link in the ACPI FIT and its deliberate omission in the DT FIT. Both
images retain the three-second factory default. The integration suite passed
71 tests against the ACPI candidate. The platform source suite passed 24 tests.

The working rhct13 bundle acquired qualification metadata after its flash. For
comparison we reconstructed its original sealed manifest and provenance in a
private directory, matched the full digest to the installer transaction on
`HW4MPK3161280211`, and compared its ESOS, OpenSBI and EDK2 bytes with the
verified NOR readback. The F2 candidate changes only the `uefi` FIT image.
All three FIT device trees and the packaged ACPI tables match rhct13 byte for
byte. Installer inspection passed. Its offline plan against that NOR readback
calls for a single 3,248,128-byte EDK2 write at `0x210000`. The F2 candidate
still needs its first hardware boot.

## Board acceptance

Use the known-good gpioy kernel and matching initramfs for the firmware
cycle. Record the firmware readback and the RHEL-on-NVMe boot from the same
transaction. Capture the F2 page on the AP serial console. Check that it
appears once, navigation and return work, and its reported mode, SKU and
configured resources agree with the selected image. Opening the page and
discarding edits should preserve the existing timeout.

Record the original timeout before changing it. Save a different finite,
nonzero value in the native editor. On cold boot, record the actual countdown
and check the saved value in setup. Restore the original value and confirm
it on the following boot. Record EC registration, UFS attach and the NVMe
root. Keep the PCIe quirk-removal kernel experiment in its own boot cycle.
The [segment 0 evidence and qualification procedure](segment0-generic-ecam.md)
includes the existing unfiltered scan and its NVMe aliases.
