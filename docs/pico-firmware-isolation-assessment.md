# Pico firmware isolation assessment

**Decision for the recorded Pico configuration** — Retain rhct17b's refusal of runtime flash writes. Both proposed write paths depend on reset and provisioning properties that remain open. K3 documents hardware that makes a protected owner plausible. The trust claim applies to the next boot, so choosing an owner requires evidence from the first authenticated stage through recovery and reset.

## Artifact and board evidence

The installer report in `~/k3-backups/pico-acpi-rhct17b-pre/report.json` records a verified EDK2 write. I checked the SHA-256 of the complete after-image against that report and compared its EDK2 slice at 0x210000 byte-for-byte with `build/rhct17-varwrite-build/MUSE-Pico.itb`. This ties the audit to that flash transaction. The [qualification log](rhct12-firmware-acpi-audit-2026-11-22.md#rhct17b-qualified-2026-11-25) records the subsequent runtime refusal.

| Retained artifact | SHA-256 or revision |
|---|---|
| Full NOR after installer readback | `cac7155f0636ec8df99348af0447829a227fcfbba2b3b15a5dfd86d67c7347bf` |
| EDK2 FIT, 3,248,128 bytes | `31c003f31fd8cf9570ab7ad6ebbe96aaa659bba61e1eec01cb9ab1958e13235e` |
| EDK2 platform commit in matched build manifest | `64ba91f04452f17e8e4defd011a580e1311102aa` |
| Packaged DSDT, 8,570 bytes | `3ecf545ba4cef4d6e4daee3941c1de63290f0ebb2bc894ce1a02958fb85640cb` |

The manifest records `ACPI_ENABLE=TRUE` as its sole extra build define. Secure Boot enrollment, production lifecycle and ROM verification require their own evidence. The recorded Pico serial log reports “Detected w25q64dw SPI NOR flash with page size 256 B, erase size 4 KB, total 8 MB”. This is a driver identification. Production BOM, board revision and WP#/IO2 wiring remain unconfirmed. The retained log was `/tmp/k3-serial-full.log`, SHA-256 `55a26058ad6461885522a144b4d7a885b70f4e5f316c2bb1c4eeb75154158ebd`.

## Isolation findings

| Surface | Evidence and consequence |
|---|---|
| QSPI address decode | The vendor address map gives the controller **0x3000 bytes** from 0xd420c000 and the aperture **128 MiB** from 0xb8000000. Include both full ranges in the ownership assessment. The driver's 4 KiB register mapping covers only the page it uses. [K3 address map](https://github.com/spacemit-com/docs-chip/blob/4879ed5dfb5415212099dd898906cd893b3fa286/en/key_stone/k3/k3_docs/k3_usermanual/06_address_map.md) |
| AP and DMA | Locked OpenSBI requests PMP regions for RCPU runtime and DT. K3 separately documents nine IOPMP instances. CPU and PCIe appear on F2M, PCIe also appears on INT2, and secure/nonsecure DMA share an identity at the DMA instance. Several identities are configurable in SEC_CIU. For each protected target, establish the actual route, address as seen at that instance, SID assignment, and which trusted stage controls that assignment. [K3 security manual §§15.4.3–15.4.5](https://github.com/spacemit-com/docs-chip/blob/4879ed5dfb5415212099dd898906cd893b3fa286/en/key_stone/k3/k3_docs/k3_usermanual/15_security.md) |
| Reset and resume | The manual specifies bypass at power-on, secure-domain configuration, and enable-until-reset. Overlapping grants for one SID are additive. Qualification needs the effective permissions including overlaps, the reset tree for each instance, and sequencing that holds initiators until protection is active. Check retained external bus masters on warm reset and access to RCPU reset/vector, clock, pinmux, GPIO and security configuration. [K3 security manual §15.4.5.1–2](https://github.com/spacemit-com/docs-chip/blob/4879ed5dfb5415212099dd898906cd893b3fa286/en/key_stone/k3/k3_docs/k3_usermanual/15_security.md) |
| Boot and recovery | The vendor documents eFuse-based secure boot and USB/UART download. The lab installer exercised USB recovery. A production provisioning record must identify the trusted key by public identifier, boot/download policy and rollback policy. Trace signature coverage of FSBL, ESOS, OpenSBI, EDK2 and their board configuration for each enabled boot source. Verify recovery enforces the same policy. [K3 datasheet](https://github.com/spacemit-com/docs-chip/blob/4879ed5dfb5415212099dd898906cd893b3fa286/en/key_stone/k3/k3_docs/k3_ds.md) |
| ACPI and DT | Extracted the packaged DSDT using `edk2_verify.packaged_data`, disassembled it with `iasl -d`, and decoded the external `fdt_1` Pico payload with `dtc`. A literal search found no QSPI controller declaration or matching register-base literal in either. This does not resolve computed addresses, broad resource windows, other installed tables, or an OS-supplied DT. Mainline Linux explicitly describes Pico SPI NOR. Treat hardware access control as necessary in both boot modes. [Linux Pico DTS](https://github.com/torvalds/linux/blob/master/arch/riscv/boot/dts/spacemit/k3-pico-itx.dts) |

## Evidence needed to select the implementation

1. Obtain the production Pico PCB revision, SoC stepping, matching schematic/BOM and non-secret provisioning profile. Trace WP#/IO2, CS, mux, reset and NOR power control to their owners. The vendor's minimum-system schematic describes a separate reference design.
2. Obtain the product's authenticated first-stage configuration or vendor security integration record. Trace each protected target through its fabric instance and provide the enforced initiator policy, lock readback semantics, release order and reset retention. Include USB/UART recovery and the rollback anchor for firmware and policy snapshots.
3. If those records establish a protected live owner, qualify it using disposable media. If only a reset-latched write lock is established, qualify authenticated early-boot commits. If either record is missing, continue using the qualified runtime refusal and keep the product security claim open.
