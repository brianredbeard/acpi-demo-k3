# Enter K3 BootROM USB download mode from Linux

`k3-enter-fastboot` reboots a running K3 into BootROM USB download mode
without holding the FDL button. It requires a working ESOS RPMI sysreset
handler. If the RPMI transport is down, reboot can hang and the board may
need a manual power cycle with FDL held. [Board operating rules](../../AGENTS.md)

## Build and install

On the builder, run `make` from `tools/k3-fastboot/`. The Makefile uses
`/srv/runner/build/linux-6.12.0-284.el10` by default. If the target runs a
different kernel, point `KDIR` at its configured build tree, for example
`make KDIR=/path/to/kernel-build`.

Place these two files on the **target board**. The wrapper uses the module
path shown below.

| File | Target path |
| --- | --- |
| Built module `k3fb.ko` | `/usr/local/lib/k3fb.ko` |
| Executable script `k3-enter-fastboot` | `/usr/local/bin/k3-enter-fastboot` |

## Reboot the target

When ready to reboot the board, run this command on its Linux console.

```sh
/usr/local/bin/k3-enter-fastboot
```

The wrapper uses `sudo` when needed and loads `k3fb.ko`. The module writes
`FLAG_FASTBOOT` (`0x01`) to `LISTEN_ADDR` (`0xc087c000`) in the `DTB_TABLE`
shared region. The board's kernel restricts `/dev/mem` access to this region.
The wrapper waits three seconds and calls `reboot`. During reset, ESOS reads
the byte and sets the nonvolatile fastboot flag on the P1 PMIC. BootROM then
enters USB download mode on the next power-on.

## Hardware qualification

The initial rhct4 test verified the flag write with ESOS patches 0001–0010.
On 2026-11-21 the full test reached the flash tool's `version-brom` handshake
without the FDL button. A later test observed that a successful
`fastboot reboot` clears the PMIC flag, so another entry requires the wrapper
or a power-on with FDL held. [Initial test](../../docs/efi-brs-check-design-2026-11-21.md) · [Flag consumption](../../docs/fvb-va-bisect-2026-11-22.md#operational-notes)
