# Which build inputs do I need?

- **Change ESOS.** Edit the numbered patch in `patches/esos/`, update its hash in the lock, and run `python3 meta.py validate`. The ESOS component lists the patches in application order. [Source lock](../sources.lock.json) · [ESOS build instructions](../docs/esos-build.md)
- **Reproduce the qualified Pico-ITX rhct17b firmware.** Select the rhct17b recipe with `build_edk2.py --recipe`. Its platform revision already includes the runtime-flash changes. [rhct17b recipe](../recipes/edk2/rhct17-varwrite/recipe.json) · [Reproduction command](../recipes/edk2/rhct17-varwrite/README.md)
- **Build the EL10-284 kernel RPM.** Stage the spec and its sources together. The spec's `ApplyPatch` entries select the K3 patches and define their order. [Kernel spec](kernel-rpm/series/el10-284/kernel.spec) · [Config staging instructions](kernel-rpm/series/el10-284/README.md)

For EDK2, `meta.py prepare` applies the numbered [edk2-platforms series](edk2-platforms/README.md) from the source lock. To reproduce a particular EDK2 build, choose one of the [firmware recipes](../recipes/edk2/README.md). OpenSBI is pinned by commit with an empty patch list. Its [manifest](opensbi/0001-k3_corepm-retentive-default-suspend.patch) documents that revision.

The original ESOS shared-domain ownership notes and source snapshot are in the [P1 history](../docs/history/esos-p1/README.md). The ownership tests exercise the source prepared from the lock.
