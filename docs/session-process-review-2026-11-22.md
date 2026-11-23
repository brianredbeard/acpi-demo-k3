# Session process review — 2026-11-22

This is a targeted review of project session records, not an exhaustive
reconstruction of every session. Line numbers refer to local JSONL records;
user corrections establish what was reported, not independent proof of the
underlying hardware state.

- Console state and boot evidence: the Pi session records corrections about
  commands at the wrong prompt (lines 4693–4704) and boot/AML claims (5175–5183).
  OMP records distinguish fallback boots and unreachable boot stages (17986,
  18031, 18205). Capture the prompt, verify each transition and state exactly
  what was tested.
- Test preparation and shared machines: OMP lines 6648–6687 and 11428–11441
  describe missing module/initramfs or boot preparation and a manifest gate;
  line 16935 warns about the active builder. Verify dependencies and machine
  roles before a test. Pi lines 3843–3861 record builder disk exhaustion.
- Context and provenance: OMP lines 9520–9584 record corrections about the
  objective and known-good state; Pi lines 6752–6981 show the need to check
  concurrent work and source provenance. Maintain an evidence-based handoff.
- Existing AGENTS guidance contradicted itself on DTB replacement and LZOP,
  and retained a superseded v25b instruction. The later
  `audit-2026-11-20/RECOVERY-AMENDMENT.md` and
  `per-clock-rate-policy-2026-11-20.md` qualify the earlier diagnoses. The
  updated rules preserve all unintended FIT payloads and distinguish build,
  bundle inspection, flashed state and hardware qualification.

Sources:

- Pi: `/home/bharring/.pi/agent/sessions/--home-bharring-Projects-K3-Ubuntu-Images-workdir-k3-maintained-efi--/2026-11-13T21-04-27-779Z_01a1d6b9-de81-7652-829e-135c33d33f6d.jsonl`
- OMP: `/home/bharring/.omp/agent/sessions/-Projects-K3-Ubuntu-Images-workdir-k3-maintained-efi-acpi-demo-k3/2026-11-20T00-44-10-755Z_01a1f669-2e83-7307-acf4-b1e219358662.jsonl`
