# k3-enter-fastboot: no-button fastboot entry

The vendor's intended path: the ESOS RPMI sysreset handler
(k3-os0_sysreset.c) polls a flag byte at 0xc087c000
(LISTEN_ADDR, the DTB_TABLE shared region) on every reboot.
FLAG_FASTBOOT (0x1) -> the handler writes the nonvolatile
fastboot flag to the PMIC (P1) before resetting -> the next
power-on lands in BootROM USB download mode. No FDL button.

Usage from Linux: /usr/local/bin/k3-enter-fastboot
(write via the k3fb.ko kernel module — /dev/mem is
STRICT_DEVMEM-blocked — then reboot).

Contents:
- k3fb.c + Makefile: the one-shot flag-writer module, built
  against the dbg1 tree (adjust KDIR)
- k3-enter-fastboot: the wrapper script installed on the
  board at /usr/local/bin (module at /usr/local/lib/k3fb.ko)

Verified: module loads + writes the byte on rhct4 firmware
(ESOS patches 0001-0010, reboot functional). The full
power-cycle path (PMIC flag -> BootROM USB -> k3-firmware
flash handshake) is exercised on the next flash cycle.

## QUALIFIED (2026-11-21, end-to-end)

Full cycle proven on hardware: k3-enter-fastboot ->
k3fb.ko writes FLAG_FASTBOOT to LISTEN_ADDR (0xc087c000) ->
reboot -> ESOS sysreset reads the flag, writes the PMIC
nonvolatile fastboot flag -> next power-on lands in BootROM
USB download mode -> the flash tool's version-brom handshake
connects. No FDL button.
