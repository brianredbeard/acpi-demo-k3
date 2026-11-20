# Meta-build bootstrap: 2026-11-19

Goal: start the standalone project at https://github.com/riseproject-dev/acpi-demo-k3.
Prior decisions: upstream projects retain their native build systems and licenses;
local hardware fixes are ordered, pinned patch series; no distribution-specific
package manager is required by orchestration.

Implementation choice: Python 3 standard library plus Git, JSON source lock,
independent source trees. A manifest expresses nested ESOS-lite explicitly rather
than relying on upstream's ignored directory or recursive submodule discovery.
This first increment prepares sources; it does not build a complete firmware.
A full build must later pin toolchains, Python dependencies and binary inputs.

- [x] Test immutable revision validation, local file hashes, path containment,
  source preparation and refusal to reuse an existing destination.
- [x] Implement validate/plan/prepare commands. Prepare in a fresh destination,
  apply patches in order, record input manifest. On failure retain diagnostic
  workspace but never produce the completion record.
- [x] Import the preserved ESOS reference without changing patch bytes.
- [x] Document component boundaries, licensing/provenance gaps and build roadmap.
- [x] Run offline tests and validate the shipped manifest.

Isolation: this new directory is the future repository root. Existing component
checkouts, board state and the parent repository are not modified. No publication.

Validation: eight offline tests pass; shipped manifest and hashes validate.
Independent review identified mutable-input races; fixed by snapshotting inputs
and recording the original manifest bytes. Completion marker uses atomic rename.
No complete firmware build, network fetch, hardware change or publication done.
