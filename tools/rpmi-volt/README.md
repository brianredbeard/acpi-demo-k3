# RPMI voltage rail qualification client

`rpmi-volt` is an out-of-tree diagnostic kernel module for querying and
changing one K3 voltage rail at a time. The rhct15 DSDT exposes the `RQTS`
platform device (`k3,rpmi-qual-test`) and assigns it mailbox channel 7, the
RPMI voltage service group.

## Build and load

From `tools/rpmi-volt/` on the builder, set `KDIR` to the configured build
tree for the board's running kernel. The native qualification rig used
`$HOME/kernel-dev/tree`. [Kernel development rig](../../docs/kernel-dev-rig.md)

```sh
make -C "$KDIR" M="$PWD" modules
```

Copy `rpmi-volt.ko` to the target. As root on the board, load it with
`insmod ./rpmi-volt.ko`. Check the probe messages in `dmesg` for voltage
service group 7 and the domain count. The driver can expose its sysfs files
even when the service-group check issues a warning.

## Inspect a rail

On the rhct15 ACPI boot, `RQTS` enumerated as `PRP0001:07`. The following
commands select `aldo3` and query it without changing rail power or voltage.
Run them in a root shell on the board.

```sh
D=/sys/devices/platform/PRP0001:07
printf '%s\n' 13 > "$D/domain"
cat "$D/query"
```

| Attribute | Access | Effect |
| --- | --- | --- |
| `domain` | Write | Select the domain for subsequent operations. The driver starts at ID 8. |
| `query` | Read | Report configuration, level in microvolts, rail name, level count and transition latency. |
| `enable` | Write | Send `SET_CONFIG` for the selected domain (`1` enables, `0` disables). |
| `level` | Write | Send `SET_LEVEL` for the selected domain, in microvolts. |

For a qualification test that changes a rail, check the `SET_CONFIG` or
`SET_LEVEL` transport return value (`ret`) and firmware `status` in `dmesg`,
then read `query` to confirm the rail state. Both write handlers report a
successful sysfs write even when the RPMI request fails.

## Domain IDs observed on rhct15

On 2026-11-24 the firmware reported 24 domains. The table lists rail names
in ascending ID order for each range. ID 13 (`aldo3`) accepted an enable
request and a level of 3,300,000 µV. [Hardware qualification record](../../docs/rhct12-firmware-acpi-audit-2026-11-22.md#rhct15-booted-the-aldo3-test-result--the-gpio9-mechanism-2026-11-24-night)

| Domain IDs | Type | Rail names in ID order |
| --- | --- | --- |
| 0–5 | Fixed | `pvin`, `pwr_ext`, `p1v8`, `p3v3`, `pwr_x100`, `pwr_a100` |
| 6–10 | Dynamic | `adcdc1`, `dcdc3`, `dcdc4`, `dcdc5`, `dcdc6` |
| 11–14 | Dynamic | `aldo1`, `aldo2`, `aldo3`, `aldo4` |
| 15–21 | Dynamic | `dldo1` through `dldo7` |
| 22 | Dynamic | `adcdc2` |
| 23 | Dynamic | Name unrecorded |

The v6 client added the sysfs interface and releases the mailbox channel
when the module is removed. The earlier v5 client used module parameters
and could leave the channel busy (`EBUSY`) on reload.
