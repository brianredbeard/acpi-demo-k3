After reset, the board boots authenticated firmware and enforces the last
authorized Secure Boot policy, even if the previous kernel controlled every EFI
call and every DMA device Linux could program. A compromised kernel can falsify
what GetVariable() reports to applications during its own boot. The guarantee
that matters is what trusted firmware reads and enforces on the next boot.

K3 has a promising starting point. Its OpenSBI platform code installs physical
memory protection (PMP) rules over both RCPU runtime regions and the RCPU
device-tree region. That makes an ESOS-hosted variable service worth
investigating. The evidence I found establishes the intended CPU-side
protection. Coverage of QSPI, DMA masters, RCPU reset and boot-vector controls,
and the production ROM authentication chain remains unverified. The repository
also records Secure Boot enforcement as an open qualification item. K3 OpenSBI
protection setup · Secure Boot qualification record

### Recommended design

| Component | Responsibility |
|---|---|
| ROM, early firmware, and OpenSBI | Authenticate every stage that can change firmware, configure isolation, or supply boot policy, including its security-relevant configuration. Establish exclusive flash ownership before untrusted code or DMA runs. Keep it effective across secondary-hart startup, suspend, and reset. Firmware updates and recovery need authenticated images and rollback protection so an older signed image cannot restore unrestricted flash access. |
| Protected variable service | Give one isolated component exclusive authority over the persistent variable store. ESOS is a candidate if its isolation and QSPI access can be demonstrated. Expose variable operations by GUID, name, attributes, and value. Keep raw flash commands private. Copy each untrusted request into bounded private storage before validation, serialize commits, and enforce the range of the live store and both fault-tolerant-write regions on every erase and program. |
| Secure Boot policy | Inside that protected component, enforce the UEFI rules for PK, KEK, db, and dbx, including authenticated deletion and replay checks. Preserve authentication metadata atomically with each update. Derive SetupMode and SecureBoot from trusted state. A damaged or erased store on a provisioned product must enter authenticated recovery rather than silently reopen enrollment. Reserve enough storage for revocations even if ordinary variables fill their quota. UEFI Secure Boot policy |
| EDK2 | Route pre-boot and runtime persistent operations through the same service. This preserves ordinary BootOrder and installer writes while closing a second path to NOR. On boot, obtain authoritative policy from the service before authenticating executable images. Keep the runtime cache for reads and update it only after durable commit. The EFI runtime map needs only the resources required by the chosen transport. The QSPI register page stays outside the OS runtime interface. |
| ACPI and ESOS power management | Audit the shipped AML for competing QSPI resources or control methods. Reserve firmware-owned resources where needed and avoid exposing a native QSPI/MTD writer. If the transport uses SBI, the OS-facing variable interface remains standard EFI and requires no new ACPI device. Have the flash owner coordinate clocks and resets for the whole transaction, with bounded waits. Keep NOR erase and reclaim out of the synchronous RPMI handler that also serves power and reset requests. |

The first implementation milestone should be an isolation decision, before
changing SetVariable(). For the exact Pico silicon and production boot
configuration, establish who can reach the QSPI registers and flash aliases,
reconfigure pinmux or issue flash commands through another path, DMA into
service memory, or reset and replace the RCPU. Identify the lock or
access-control mechanism for each path, who programs it, and which reset clears
it. Verify the authenticated boot and recovery paths as part of the same
decision. An ACPI reservation and AP PMP entries alone cannot establish those
properties.

If those checks pass, I’d implement the protected backend and qualify it with
disposable keys and a disposable variable store. Acceptance should include an
authorized dbx update that survives cold boot and actually rejects a revoked
image, rejection of unsigned and replayed updates, interrupted commits that
recover the old or new policy, and ordinary boot-variable writes before and
after ExitBootServices(). If K3 lacks enforceable isolation for a live writer,
I’d choose hardware write protection through OS runtime, with policy changes
committed during authenticated early boot if the board supports that lock
lifecycle. That fallback sacrifices immediate persistent runtime writes while
preserving the more important product property.
