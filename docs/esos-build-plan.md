# ESOS build adapter — 2026-11-19

Authorized next increment of the bootstrap roadmap. Implement inline.

- Build only into a new destination, preparing fresh pinned sources first.
- Accept explicit Python (with SCons/Kconfiglib) and ELF compiler directory.
- Permit named local Git caches for offline qualification; preserve locked
  revisions and record transport overrides. Never reuse modified source trees.
- Snapshot and verify both configurations before cloning. Build lite first,
  copy its binary, then main, using each project's own Kconfig converter.
- Capture commands, environments selected by the adapter, tool versions, logs,
  configurations and artifact hashes. Only mark success after nonempty outputs.
- Test ordering, failure reporting, input validation and existing-path refusal.
- Attempt a real cross-build from local pinned Git objects and existing tools.

Scope: rt24/os0_rcpu reference, not whole FIT packaging or COM260 qualification.
Compiler/dependency recording is provenance, not a complete reproducibility lock.

Completed: adapter, 15 host orchestration tests, two successful fresh cross-builds
on this host (lite hashes match; main hashes differ), four reset patch host regression
groups, independent review (no blockers). See esos-build-evidence.json.
