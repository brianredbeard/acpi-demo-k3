# Pico protected firmware and EFI variables implementation plan

**Goal** — A cold or warm reset restores authenticated execution and the last authorized Secure Boot policy after an OS compromise.

**Architecture** — A protected owner authenticates and commits variable transactions. EDK2 remains the EFI client. Selection of ESOS as that owner depends on demonstrable silicon isolation and authenticated bootstrap. If exclusive runtime ownership is infeasible, evaluate the design's early-boot-only alternative.

**Stack** — Pico K3, SPI NOR, ROM/FSBL, OpenSBI, ESOS/RPMI, EDK2, ACPI and Linux EFI.

**Spec** — [Approved design](../../secure-firmware.md). Execute in dependency order using the executing-plans or subagent-driven-development workflow.

## Global constraints

Keep the qualified rhct17b runtime refusal until a protected path is qualified. Preserve pre-boot persistence. Use the repository's locked builds, committed patches, one variable per flash, whole-FIT comparison and installer inspection. Use disposable keys and media for security qualification. Production fuse programming is a separate provisioning operation.

## Review focus

Track warm reset and resume before locks return, DMA and pinmux aliases, interrupted authenticated updates, replay of an entire older store, and ordinary-variable exhaustion during a revocation update.

## 1. Decide whether Pico can isolate a flash owner

**Current disposition: open.** Source inspection at integration revision `ee737a0` produced the following starting evidence.

The [Pico isolation assessment](../../pico-firmware-isolation-assessment.md) records the subsequent NOR readback match, flash identification, packaged-table inspection and vendor-documented IOPMP reset behavior.

| Question | Evidence in hand | Evidence needed to close |
|---|---|---|
| Can AP software alter the owner? | Locked OpenSBI revision `51a9d0f99d23aa00ad9d14c84874c4673d9559ac`, `platform/generic/spacemit/spacemit_k3.c`, requests enforced PMP regions for both RCPU runtime areas and the RCPU DT. | Effective per-hart permissions, RCPU reset and vector control ownership, DMA and debug access, and when protection becomes effective after each reset/resume. |
| Who can drive the NOR? | `QspiMmioRemap()` attempts to register the controller and flash aperture. The vendor RT24 pin definitions assign QSPI pins 140–146 GPIO aliases. The locked `patches/esos/os0.config` disables RT-Thread QSPI. | Exact Pico PCB revision, NOR part/WP wiring, mux/GPIO/pad locks, bus masters, controller and aperture permissions, and authority over their locks. |
| What authenticates the first owner? | `build_edk2.py` supplies ACPI_ENABLE and accepts extra defines. `Silicon/Spacemit/Spacemit.dsc.inc` selects AuthVariableLib or AuthVariableLibNull according to SECURE_BOOT_ENABLE. | Product ROM key provisioning and lifecycle evidence, FSBL verification coverage including configuration and recovery/FDL, rollback floor, exact shipped build report, artifact hashes and enrolled public-key identities. |

- [ ] Bind the assessment to a product stepping, board revision and flash part, with the matched programming manual, schematic and non-secret provisioning record. Record the booted image identities separately from repository pins.
- [ ] For each path above, record initiator, target, hardware enforcement, who programs and can unlock it, reset scope and evidence reference. Include PCIe and on-chip DMA, debug/alternate boot, and every OS-callable firmware service that controls pins, clocks, resets or flash. Review the shipped AML and DT for consumers and aliases.
- [ ] Trace the first instruction after each reset to authenticated EDK2 policy evaluation. Record protection establishment relative to releasing harts and DMA. Cover restoration of a previously valid firmware image or whole variable store, including service/recovery modes.
- [ ] Record one decision with evidence for every row. Select a runtime owner only with complete coverage. Select early-boot commits only if hardware can keep firmware and the store write-protected throughout OS execution and restore ownership safely across reset. Otherwise retain rhct17b and record the missing product capability.

## 2. Establish the selected protection boundary

- [ ] For a live owner, put isolation setup in the authenticated stage that first controls each resource. Exercise its failure path and lock readback using documented interfaces. A failure must prevent protected-mode startup. For early-boot commits, verify the lock lifecycle before implementing an authenticated pending-update format and protect against replay across reset.
- [ ] Qualify normal, recovery, suspend and reset paths with disposable images. Require rejection of unauthorized and stale firmware through each update path and independent confirmation of the selected boot image. Record the provisioned state outside the mutable variable store.

## 3. Implement variable policy and durable storage inside the owner

- [ ] Reuse the audited authenticated-variable policy where feasible. Cover PK, KEK, db and dbx creation, update, append and deletion, signature authorization and freshness. Exercise corrupted and blank provisioned stores, replay of an old complete snapshot, and ordinary variables filling their quota before a dbx update. Recover through authenticated policy on corruption.
- [ ] Confine the flash backend to the FDF-defined live, working and spare regions, currently NOR offsets `[0x700000, 0x7c0000)`. Test overflow, erase alignment, reclaim and interruptions at each commit phase. On restart require a complete old or new value with its matching authorization metadata. Distinguish replay resistance from power-loss recovery.
- [ ] For ESOS, ship numbered locked patches and exercise the prepared source. Copy bounded incoming variable requests into private memory, serialize transactions, and support bounded completion/status for slow flash work outside the synchronous RPMI handler. Test changed shared buffers, duplicate requests, timeout after durable commit and concurrent reset. Preserve clock/domain ownership throughout flash activity.

## 4. Integrate EDK2 and qualify the complete product path

- [ ] Route persistent reads at startup and every mutation through the selected owner. Load authoritative security policy before image verification. Preserve pre-boot BootOrder and installer operations. Publish cache updates after durable success. Exercise physical and nonidentity virtual addressing, transport loss, and cold re-enumeration. For the early-boot alternative, expose accurate runtime capability and never report a staged request as a durable EFI write.
- [ ] Inspect the final EFI runtime map and disassembled shipped ACPI tables. Keep QSPI private and resolve any competing OS resource claim. If a firmware reservation is needed, add it to the Pico platform tables and verify its exact range in the built AML. Confirm native EFI variable access on Linux.
- [ ] Run the repository suite with the locked sources and actual retained EDK2 driver workspace selected. Qualify each hardware change separately. With disposable keys, enroll a test signer, boot a signed image, commit its authorized revocation, cold-boot and verify that the same image is refused. Exercise unsigned, stale and interrupted updates, and verify ordinary variable create/update/delete persistence. Record EFI statuses, before/after hashes, boot mode, and idle/UFS/reset outcomes.
