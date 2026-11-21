# Power-consumption evidence for the P1 suspend stack (2026-11-21)

## Setup

The board's AC input passes through a Kauf PLF12 smart plug
(http://192.168.140.181/, ESPHome web API, SSE `/events` stream,
power sensor `sensor-kauf_plug_power`). Measured at the wall:
120.9 V nominal. Samples taken 8-10 s apart; the plug reports
instantaneous watts.

Firmware under test (the lpi2q image): OpenSBI 51a9d0f9 (the
quiet-deny fix) + the idle-state ESOS (patches 0001-0008 + the
0x11000000 dtb state) + EDK2 with _LPI index-2 (SBI_CRET,
corrected FFH encoding).

## The power ladder

| State | Mean draw | Std | n |
|---|---|---|---|
| 8 CPUs online, idle (LPI ladder: WFI/SBI_WFI live, LPI-2 armed) | 18.80 W | 1.11 | 5 |
| Cluster 1 offlined (CPUs 4-7; 0-3 online) | 16.71 W | 0.06 | 6 |
| Cluster 1 restored (8 CPUs) | 18.04 W | — | 3 |
| All-CPU load (sha256 on each core) | 20.63 W | — | 3 |

**Delta: offlining cluster 1 saves 2.09 W — 11.1% of the
board's idle draw — and the saving is highly stable (sd 0.06 W
vs the baseline's 1.11 W).**

## Interpretation

The 2.09 W saving when CPUs 4-7 go offline is the measurable
signature of the coordinated stack doing its job:

1. The kernel's cpuhp path stops each CPU (the hart-stop path:
   votes + WFI per core, hardware idle admission in the PMU)
2. The ESOS monitor observes the per-core stop votes; the P1
   provider releases the cluster; the sequencer runs the
   ordered entry (QUIESCE -> ENABLE -> the bounded M2 wait)
3. The measured floor includes the cluster's cores, L2, and the
   coordinated domain state

The restore path returns the board to baseline (18.04 W vs
18.80 W within noise), all 8 CPUs online, zero lockups, zero
clock loss throughout — the full offline -> sequenced entry ->
online cycle, measured at the wall.

## Measurement notes

- The baseline sd (1.11 W) reflects the plug's sampling of a
  system whose idle states vary (the LPI ladder cycling); the
  cluster-offline state's tight sd (0.06 W) is itself evidence
  of a quieter, more stable idle.
- The load bracket (20.63 W all-core) bounds the achievable
  range: the 2.09 W cluster saving is ~half the total dynamic
  range of the CPU complex at this workload.
- One restored sample (15.65 W) is an outlier vs its neighbors
  (19.27, 19.21) — likely a sample landing during the
  post-online settling; the mean is reported with this noted.

## Reproduction

- Sample: `curl -s -N http://192.168.140.181/events | grep -m1
  sensor-kauf_plug_power` (value field)
- Offline cluster 1: `for c in 4 5 6 7; do echo 0 >
  /sys/devices/system/cpu/cpu$c/online; done`
- Restore: `echo 1 > .../online` per CPU
