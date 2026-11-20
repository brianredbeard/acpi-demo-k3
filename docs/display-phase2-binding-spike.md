# Display Phase 2 (native DRM) — binding spike assessment (2026-11-20)

## What exists

The vendor kernel carries the full stack as modules:
- drivers/gpu/drm/spacemit/: spacemit-drm.ko (DPU: dpu/dpu_saturn.c,
  crtc, planes, cmdlist, dmmu) + spacemit-inno-dp.ko (Inno DisplayPort)
- bridges: inno-hdmi.c (shared), panels via of_ standard bindings

## The binding problem (confirmed in source)

spacemit_drm.c:spacemit_drm_of_component_probe() builds the component
match by walking DT graph endpoints:

  of_graph_get_remote_port_parent(ep) -> drm_of_component_match_add()
  -> component_master_add_with_match()

The DPU/DP drivers use component_add() against nodes in that graph,
plus of_ parsing for their clocks (5-7 named), resets (5), PHY
phandles, and panel/bridge discovery. Under ACPI PRP0001:
- dev->of_node is NULL -> no graph, no component match, no master
- even with _DSD properties, of_graph has no ACPI representation

## Options (per the plan's spike scope)

(a) ACPI glue in spacemit_drm: synthesize the component match from
    _DSD (e.g. a "spacemit,components" string list naming the child
    devices) + convert every of_ parse in the DPU/DP/PHY/panel stack
    to device_property + firmware-provided clocks. This is the full
    port: 5+ drivers, multi-week, and it diverges from upstream DT
    bindings permanently.

(b) Component match by name/device (not graph) — same of_ conversion
    burden as (a) for the leaves.

(c) Phase 2a: firmware-fixed single mode — extend the current
    simpledrm handoff (which works today) with EDK2 ClockDxe pinning
    the display clocks to one mode. No kernel DRM work. Limited
    (no modeset), but it is "a separate limited experiment" per the
    plan and delivers a stable display while (a) is designed.

## Recommendation

Phase 2a first (small firmware-only change, keeps the working
simpledrm console), and treat (a) as a dedicated follow-on series
needing its own binding design (the "spacemit,components" _DSD
convention or an equivalent) reviewed against how other ACPI
display platforms (e.g. qcom windows-era) solved component graphs.
