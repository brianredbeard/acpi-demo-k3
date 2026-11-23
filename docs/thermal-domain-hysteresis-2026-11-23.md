# Thermal domain rebalancing — research + design (2026-11-23)

## Symptom
Occasional thermal cycling on the board under sustained load
(kernel builds). Sensors idle at 61-67°C.

## Measured state (live, gpioy kernel, rhct12 firmware)

7 zones (k3_tsensor_ch0/2-7), all step_wise:
- ONLY zone0 (ch0, idles 63-64°C) has trips: 65/75/85°C
  passive/passive/hot, hysteresis 5°C, cdevs = 8 dead Processor
  (max_state=0 — no cpufreq cooling registered) + pwm-fan
  (EC-PWM, 3 states, the only live actor; observed 1->2 during
  a 60s trace)
- Zones 1-6: EMPTY trips — including ch4, the hottest sensor
  (67°C), which controls nothing
- Trips are READ-ONLY at runtime (zone registered non-writable)
- Cycling mechanism: load crosses 65°C -> fan steps -> temps
  fall inside the band -> fan steps back -> repeat; the coarse
  3-state fan curve oscillates as the lone actor

## Source analysis (why the domain is broken)

- The tsensor driver (BSP patch) registers zones via
  devm_thermal_of_zone_register -> thermal_of_zone_register ->
  of_find_node_by_name(NULL, "thermal-zones") — a GLOBAL
  DEVICE-TREE-ONLY lookup
- Under ACPI boot: the EFI-passed FDT is a 554-byte stub (no
  thermal-zones), and the DSDT has no ThermalZone objects —
  the OF lookup must fail
- Yet zone0 registered WITH trips on the gpioy kernel — its
  hand-spliced driver predates the BSP patch version and
  carries ch0-only hardcoded trips (the running kernel's
  source tree is gone; the behavior fingerprint: one zone
  with 65/75/85, six inert)
- The cycle-3 (BSP-based) tsensor driver has NO trips in code
  and NO ACPI path: under ACPI it will register SEVEN INERT
  ZONES (worse than gpioy's one)

## The ACPI-mode fix (design)

Kernel side (next cycle, tracked):
1. Port the tsensor driver from the DT-global lookup to
   fwnode-based zone parsing (device_property_/fwnode_ APIs),
   which reads _DSD hierarchical data under ACPI
2. Publish per-channel zone definitions in the TSEN _DSD via
   the hierarchical UUID (dbb2e5d5-5e18-11e7-9812-d496f7e63d2c):
   - ch0 (cool control point): 70/80/90°C, hyst 8°C
   - ch4 (hotspot, runs ~4°C hotter): 75/85/95°C, hyst 8°C
   - other channels: 72/82/92°C, hyst 8°C
   - per-zone cooling maps: pwm-fan on first passive; future
     cpufreq/CPPC actors on second passive
3. Staggered trips = the "different hysteresis across the
   domain": the control point becomes max(channels) instead
   of one sensor's noise; the hotspot gets real authority

Firmware side (next DSDT cycle):
- The _DSD zone package above (rides the same rhct13 firmware
  change as the other staged DSDT work)

Actors still missing (separate items):
- cpufreq cooling: the 8 dead Processor cdevs (no cpufreq
  driver) — the RPMI CPPC work (queued) makes passive CPU
  throttling real; until then the fan acts alone
- Fan curve smoothing: EC-side 3-state curve is coarse; an
  intermediate step reduces visible oscillation
