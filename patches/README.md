# Find the patches for a build

| Task | Where the build gets its inputs |
| --- | --- |
| Change ESOS | Edit the numbered patch in `patches/esos/`, update its SHA-256 in the ESOS component, and run `python3 meta.py validate`. The lock gives the application order. [Source lock](../sources.lock.json) · [ESOS build instructions](../docs/esos-build.md) |
| Prepare the early EDK2 bring-up series | `meta.py prepare` applies the numbered edk2-platforms patches in source-lock order. [EDK2 patch ledger](edk2-platforms/README.md) |
| Reproduce the qualified rhct17b firmware | Pass the rhct17b recipe to `build_edk2.py`. Its pinned platform commit includes the runtime-flash changes. [Reproduction command](../recipes/edk2/rhct17-varwrite/README.md) · [Other recipes](../recipes/edk2/README.md) |
| Locate the qualified OpenSBI source | The lock pins a workstation-local snapshot with an empty patch list. The file in `opensbi/` records the commit history and suspend fix. [OpenSBI manifest](opensbi/0001-k3_corepm-retentive-default-suspend.patch) |
| Build the EL10-284 kernel or a module RPM | The full kernel spec's `ApplyPatch` entries define the order. Each module job selects its driver patch from that same directory. [Kernel guide](kernel/README.md) · [Kernel spec](kernel/el10-284/kernel.spec) |

The original ESOS P1 source snapshot, early kernel bring-up patches, and their review notes live under `docs/history/`. The ESOS ownership tests exercise the source prepared from the lock. [ESOS P1 history](../docs/history/esos-p1/README.md) · [Kernel history](../docs/history/kernel/README.md)
