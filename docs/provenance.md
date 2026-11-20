# Imported reference provenance

The ESOS patch and two configurations were copied byte-for-byte from
`patches/esos-reference/` in the K3 maintained EFI workspace on 2026-11-19.
`sources.lock.json` carries their original SHA-256 values and upstream pins.

Patch: `0001-k3-reset-restore-owned-i2c-pins.patch` preserves the historical
reset-handoff-v1 local implementation and bundled host regression harness.
It restores owned I2C pin state before terminal PMIC reset/shutdown traffic.
It is not the separate experimental ACPI clocks series.

ESOS main: e0b8d955bdc84957da3b7bba8c89e35ee0d27c2b
ESOS-lite: 1e166dbeaa55ea6a572c2dc9b567a16b29b3ea38

The reference previously passed patch reconstruction and four host regression
groups. Those historical results do not qualify a new build or COM260 deployment.
The bootstrap tests exercise orchestration with temporary Git fixtures, not the
complete ESOS cross-build. Full historical hardware artifacts remain in the
original workspace; they have not been copied into this standalone project.

Upstream top-level Apache-2.0 metadata does not resolve all third-party notices.
The earlier audit identified an FDT package license inconsistency requiring
review before redistribution. No vendor binaries or toolchain archives are
included here. Source retrieval availability and all transitive input pins still
need validation on a clean machine.
