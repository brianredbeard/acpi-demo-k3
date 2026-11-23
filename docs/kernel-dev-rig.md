# The kernel-dev iteration rig (board, non-privileged)

redhat@192.168.137.146:~/kernel-dev — the fast path for kernel
patch development. Editable source+object tree (the prepared
284 acpidebug build, headers/symbols included), native compiler
+ ccache, no mock, no full rebuilds, no root needed for builds.

## Validated workflow (2026-11-23, thermal patch as first user)

    # on the workstation: develop the patch, verify vs pristine
    # ship one file to the rig:
    scp k3_tsensor.c redhat@192.168.137.146:~/kernel-dev/tree/drivers/thermal/spacemit/
    # on the rig (as redhat):
    cd ~/kernel-dev
    ./kbuild drivers/thermal/spacemit/k3_tsensor.ko   # 5.3s edit->ko
    modinfo -F vermagic tree/.../k3_tsensor.ko

Result: k3_tsensor.ko (vermagic 6.12.0-284.acpidebug.1.el10)
in ~5 seconds. The mock cycle (~2h) is only needed for
kernel-image changes (built-in drivers, Kconfig) and RPM
packaging.

## Rules (from the rig's README + validation)

- MODULES (=m): build the .ko, copy into the matching kernel's
  /lib/modules/.../ tree (as root), depmod, modprobe. Loads
  only on the vermagic-matching kernel (284-acpidebug — NOT
  gpioy dbg1; their ABIs differ).
- BUILT-IN (=y, e.g. GPIO): ./kbuild file.o checks COMPILATION
  only; hardware behavior needs a kernel image containing the
  change (full mock cycle).
- Keep the tree dirty (no clean/mrproper); ccache is separate
  (30G, ~64% hits observed); baseline/ holds the origin
  hashes + Module.symvers for ABI checking.
- External modules: source + Kbuild in a home dir, ./kbuild
  external <dir>.
- build.lock serializes; JOBS=N adjusts parallelism.

## Where it fits

- Patch iteration: rig (seconds) — compile + load-test modules
- Preflight: rig (the .o/.ko check before any SRPM work)
- SRPM/mock: kernel-image changes + RPM packaging (hours)
- The staged kernel patches (espi-v2, gpio-v3, rfkill,
  tsensor-acpi-zones) can each be rig-validated as modules
  where =m allows: tsensor (m) ✓ done; rfkill-gpio (m) ✓;
  espi controller (m? — check); gpio (=y, object-only).
