# AGENTS.md — operating rules for this repository and the K3 board

Hard-won rules from the 2026-11-20/21 sessions. Every rule below exists
because violating it cost a flash cycle, a hardware wedge, or an audit
finding. Read before building, flashing, or "just testing" anything.

## The three commandments

1. **ESOS builds go through `build_esos.py` — always.** The hand-build
   path (`./build.sh` from a working tree) produced every dead firmware
   in the v24 series while carrying byte-identical sources to working
   builds. The reproducible flow scrubs the environment, pins the
   toolchain, and is the only path that has ever produced a working
   ESOS image. There is no such thing as a quick hand build.
2. **One variable per flash.** If a flash changes more than one thing
   (two regions, two features, or a feature plus "unrelated cleanup"),
   its result proves nothing and the next debug step is a guess.
3. **Commit before you flash.** The flash that panicked in v21f had its
   fix living in `/tmp`. If work isn't committed, it doesn't exist.

## Build discipline

- `build_esos.py --destination <fresh dir> --python <venv>/bin/python
  --compiler-dir <toolchains>/spacemit-toolchain-elf-newlib-x86_64-v1.0.9/bin
  --jobs 8 --repository esos=<local clone>`. Destination must not exist.
- Patches live in `patches/esos/` and are the ONLY way ESOS source
  changes ship. Edit → regenerate patch → update `sources.lock.json`
  hash → `python3 meta.py validate` → build. Never flash a working-tree
  state that the lock cannot reproduce.
- The toolchain is newlib (`riscv64-unknown-elf-`). The host has
  `riscv64-linux-gnu-` (glibc) in PATH and a `CROSS_COMPILE` env var;
  the reproducible flow's scrubbed env is what protects you from it.
- EDK2: `build -p Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc -a RISCV64
  -t GCC5 -b RELEASE -D ACPI_ENABLE=TRUE` from the edk2 tree with
  `WORKSPACE=<k3-maintained-efi root>`, `PACKAGES_PATH` including
  efi-development's edk2-platforms (Ext4Pkg). Without `-D
  ACPI_ENABLE=TRUE` you get a DT-only image and waste a cycle.
- OpenSBI is pinned as a sources.lock component at the v21g baseline
  (`b4152e0761ac1986`, fw_dynamic `2f14c5c8`). Any OpenSBI change diffs
  against that commit and ships as a numbered patch in
  `patches/opensbi/`, advancing the component revision.

## Firmware packaging (FIT swaps)

- The OpenSBI and ESOS payloads are FIT images. Swap only the relevant
  subimage data (fw_dynamic for OpenSBI; `rt24_os0_rcpu.elf.lzo` +
  the pico dtb for ESOS), recompute the FIT CRC node, keep every other
  payload byte-identical, and verify the changed-payload list before
  packaging. Helper scripts for this exist in the session history;
  re-derive rather than trust memory.
- `dumpimage -T firmware` cannot extract from these FITs; use a struct
  walker. LZOP payloads decompress with `lzop -d -c`.
- Region offsets: esos `0xb0000`/`0x100000`, opensbi `0x1b0000`/`0x60000`,
  edk2 `0x210000`/`0x4f0000`.

## Hardware access — what is and isn't observable

- The board's RPMI **shmem queue lives at `0x100e00000`** (see the DT
  `shmem-base`), NOT `0xcac90xxx` (that is the doorbell controller,
  `mailbox3@cac90c00`).
- **The rcpu (ESOS) console is `uart0` — a physical port that is NOT
  the AP serial console (`ttyS0`).** ESOS `rt_kprintf` output is
  invisible on the serial you can see. Never instrument ESOS via
  console prints.
- **Linux `/dev/mem` segfaults on the rcpu DRAM carve-outs**
  (`0x100200000`+ load region, `0x100e00000` shmem). You cannot read
  rcpu state from Linux through DRAM.
- **Do not write to MMIO registers whose semantics you haven't
  verified.** `0xd4282bf8` looked like scratch; it was live PMU
  hardware, and writing it from Linux was reckless. Read the register
  map (`_register_defination.h`, `k3_hsm.h`, the AP `k3.h`) first.
- The serial console is tmux session `k3-serial`; someone else may be
  driving it — `capture-pane` before `send-keys`. A login prompt is
  not a shell: verify `[root@localhost ~]#` before typing commands.
  Use `tmux pipe-pane` to a file for boot-capture (console history is
  shorter than a full boot).
- Board ssh: `ssh -i /tmp/k3key root@192.168.137.146` (key is volatile).
  Builder: `ssh riscv` (kernel tree
  `/srv/runner/build/linux-6.12.0-284.el10`; the in-tree module dir is
  root-owned in places — `find . -user root -delete` once before make).

## Flash discipline

- Flash: `sudo ./k3-firmware flash --bundle <dir> --device usb:3-3.3
  --board pico-itx --backup-dir <new dir> --yes` from
  `~/Projects/fedora-k3-firmware`. Requires BootROM/FDL mode (hold FDL
  while powering on). You cannot sudo — hand the command to the user.
- Before any flash: the bundle must pass `./k3-firmware inspect`, the
  changed-payload list must match the one intended variable, and the
  current working tree must be committed.
- After a failed experimental flash, the board's reboot will hang if
  the RPMI transport is dead (sysreset needs it). Expect a manual
  power cycle; warn the user before asking them to reboot.
- Known-good rollback ESOS images: the v12 bundle payload, and the
  v20-exact rebuild (lock at repo commit `4fb2e49`, rtthread.bin
  `11206a38…`). One region reflash recovers the board.

## The v24 post-mortem (why the matrix matters)

The failure matrix that finally isolated the v24/v25 breakage:

| patches | v21+ hsm wiring | build path | hardware |
|---|---|---|---|
| yes | no | reproducible (v20) | worked |
| no | yes | hand (v23) | worked |
| yes | no | hand (v24g) | dead |
| yes | yes | reproducible (v25) | dead |

Both known-good halves shared nothing; the union failed on both build
paths. The remaining suspects at time of writing: the v21+ hsm init
wiring (monitor/hw-ops in patch 0007) and/or host build-environment
drift since v20. v25b (the v20-exact rebuild) is staged to discriminate.
**Do not "fix" anything until that flash is read.**

## Prior hardware findings that must not be relearned

- `SBI_ENOTSUPP` from a platform device on a DEFAULT suspend type is
  consumed by generic OpenSBI as "run the generic fallback" — which
  warmboot-simulates and parks the hart (the v14/v15 CPU4/CPU7 wedges).
  Reject default types with `SBI_EFAIL` in the wrapper.
- A grant from the ESOS gate licenses NO per-hart cluster vote — the
  v21f corruption panic. Votes are placed by whole-cluster coordination
  (the M2-enter ISR sequence), never by an individual hart's ecall.
- The ESOS gate's bounded wait must stay under the OpenSBI mailbox RX
  timeout (`RPMI_DEF_RX_TIMEOUT` = 20ms); the prepare runs inside the
  RPMI request.
- `ufs_refclk` is firmware-enabled at boot; the RPMI clock service
  historically returned `RPMI_ERR_ALREADY` for enable-when-enabled
  (fixed by the policy: idempotent state changes are SUCCESS).
- The X100 AP harts (0-7) boot under OpenSBI without RPMI hart_start;
  `k3_hsm_get_hw_state` must report them STARTED or librpmi denies
  every non-zero-hart request before the gate runs.

## Test and verification

- `python3 -m unittest discover -s tests` (17 tests) must pass before
  any commit that touches the lock or patches. The ownership suite
  (`tests/test_k3_domain_ownership.py`) compiles the LOCKED prepared
  source — not the working tree — and runs 64 fault-injection
  assertions; keep it that way.
- First run of the suite may need
  `K3_ESOS_CACHE=<esos-reset-handoff>` or network for the clone.
- Kernel modules (sbi_suspend_test, ufs-spacemit) build out-of-tree on
  the builder; deploy to the board via scp with the k3key.

## Style

- Diagnostics: retained counters, no serial logging in transition
  paths. Bounded waits everywhere; a timeout aborts with no state left
  behind.
- Every flash cycle's provenance JSON records what changed, why, the
  test plan, and the rollback. If a bundle's provenance can't explain
  itself, don't flash it.

## THE FIT payload rule (the v20-v26 post-mortem, 2026-11-21 — READ THIS)

**When packaging an ESOS FIT, EVERY payload except the one you
intend to change must be the byte-identical original — including
the device trees.** The rcpu firmware reads its hardware
configuration (register bases, queue addresses, service
descriptions) from the `rcpu0-dtb-*` payloads. A regenerated
device tree describes different addresses; the firmware boots
but its RPMI transport lands on wrong registers: dead clock
service, dead MPXY, hanging reboot.

This single mistake caused the entire v20+ failure cascade: the
`0x11000000` idle-state work rebuilt `k3_rt240_pico_itx.dtb` from
tree source and overwrote the original in `output/esos/`. Every
FIT built afterward (v20 through fix1 — dozens of flashes,
multiple bisect arcs) packaged the regenerated tree. The firmware
content was equivalent the whole time (proven: same drivers, same
init table, same strings, identical QEMU execution, deterministic
builds, identical FIT properties, identical rcpu1-fw — the rcpu0
dtb was the one payload never compared).

**MANDATORY before every flash:** run the payload-diff check —
the staged FIT must differ from the last-known-good image in
EXACTLY the intended payload(s) and NOTHING else. The comparison
must cover ALL payload nodes (`rcpu0-fw`, `rcpu1-fw`, every
`*-dtb-*`, `rcpu-data-null`), not just the one you changed. A
helper for this exists in the session tooling; re-derive from the
FIT walker if lost.

**The originals:** the known-good dtb payloads live inside the
qualified v12 bundle's `esos.bin` (and in every NOR backup under
`~/k3-backups/*/nor-before.bin`). If `output/esos/*.dtb.lzo` does
not hash-match the originals, EXTRACT them from the bundle before
building a FIT. Tree-source dtbs are NOT drop-in equivalents: the
originals were produced by the vendor build with board-specific
fixups that the tree source alone does not reproduce.

**Secondary lesson (compression):** the compression rule below was
a wrong diagnosis of the same symptom — kept as a caution: prefer
plain `lzop` (default) for rcpu0-fw to match the working images
(rcpu1-fw is a -9-style stream in both working and rebuilt images,
so the FSBL decodes both; but default matches the known-good
rcpu0 pattern). Do not "improve" packaging flags without a
hardware test cycle.

**How this was finally found:** compare EVERY payload of the
failing image against the working one, byte-for-byte, before
theorizing about content. The diagnostic order for "from-source
build behaves differently than the shipped image" is:
1. payload-level byte diff of the ENTIRE image (all nodes)
2. only then: content, determinism, toolchain, compression

## Prior hardware findings that must not be relearned

- `SBI_ENOTSUPP` from a platform device on a DEFAULT suspend type is
  consumed by generic OpenSBI as "run the generic fallback" — which
  warmboot-simulates and parks the hart (the v14/v15 CPU4/CPU7 wedges).
  Reject default types with `SBI_EFAIL` in the wrapper.
- A grant from the ESOS gate licenses NO per-hart cluster vote — the
  v21f corruption panic. Votes are placed by whole-cluster coordination
  (the M2-enter ISR sequence), never by an individual hart's ecall.
- The ESOS gate's bounded wait must stay under the OpenSBI mailbox RX
  timeout (`RPMI_DEF_RX_TIMEOUT` = 20ms); the prepare runs inside the
  RPMI request.
- `ufs_refclk` is firmware-enabled at boot; the RPMI clock service
  historically returned `RPMI_ERR_ALREADY` for enable-when-enabled
  (fixed by the policy: idempotent state changes are SUCCESS).
- The X100 AP harts (0-7) boot under OpenSBI without RPMI hart_start;
  `k3_hsm_get_hw_state` must report them STARTED or librpmi denies
  every non-zero-hart request before the gate runs.

## Test and verification

- `python3 -m unittest discover -s tests` (17 tests) must pass before
  any commit that touches the lock or patches. The ownership suite
  (`tests/test_k3_domain_ownership.py`) compiles the LOCKED prepared
  source — not the working tree — and runs 64 fault-injection
  assertions; keep it that way.
- First run of the suite may need
  `K3_ESOS_CACHE=<esos-reset-handoff>` or network for the clone.
- Kernel modules (sbi_suspend_test, ufs-spacemit) build out-of-tree on
  the builder; deploy to the board via scp with the k3key.

## Style

- Diagnostics: retained counters, no serial logging in transition
  paths. Bounded waits everywhere; a timeout aborts with no state left
  behind.
- Every flash cycle's provenance JSON records what changed, why, the
  test plan, and the rollback. If a bundle's provenance can't explain
  itself, don't flash it.

## THE compression rule (the v20-v26 post-mortem, 2026-11-21)

**ESOS FIT payloads are compressed with plain `lzop` (default
level 1). NEVER `lzop -9`.** The FSBL's lzo decompressor only
handles the default stream format (level 1, flags 0x05). `lzop -9`
produces level 3 / flags 0x09 — the FSBL fails or silently
corrupts the decompression, and the rcpu firmware boots dead:
no clock service, no RPMI transport, hanging reboot.

This single flag caused the entire v20+ failure cascade — every
from-source ESOS image was packaged with -9 ("for better
compression") while the working images used the default. Firmware
content was equivalent the whole time (same drivers, same init
table, same strings — verified by binary analysis); the
compression format was the only loading-relevant difference.

When comparing a working image against a broken one, compare the
LOADING path first: compression headers, FIT properties, entry
points. Content equivalence does not imply loading equivalence.
