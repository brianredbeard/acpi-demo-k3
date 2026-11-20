# acpi-demo-k3

Canonical project URL: https://github.com/riseproject-dev/acpi-demo-k3

A distribution-neutral integration project for K3 ACPI firmware. It keeps
upstream projects independently replaceable, pins inputs, and carries local
changes as reviewable patch series. This directory is the future repository
root; a local Git repository is initialized with that origin. The GitHub repository
has not been created or published by this bootstrap.

## Current commands

Requires Python 3.9+ and Git. No Python packages or distribution package manager
are needed for source preparation. Run from this directory:

```sh
python3 meta.py validate
python3 meta.py plan
python3 -m unittest discover -s tests
python3 meta.py prepare --destination /path/to/new-source-workspace
```

`validate` checks manifest pins and local patch/configuration hashes. `plan` is
read-only. `prepare` clones ESOS and its explicitly pinned ESOS-lite dependency,
checks out detached commits and applies the ordered patch series. It requires
network access unless a custom manifest names local repositories. It does not
update existing checkouts. Failure leaves the new workspace for inspection;
choose a new destination after correcting the problem. `prepared.json` appears
only after all source preparation succeeds. It records inputs, not build results.

Manifests and patch files are trusted build inputs, not a sandbox. Review them
before use. Commit IDs and hashes establish identity; they are not signatures.
Upstream submodules are not recursively fetched: each required dependency must
become an explicit locked input. Configurations are hash-verified but are not
installed into the source trees until a build adapter defines that operation.

## Component boundaries

| Component | Integration status / intended responsibility |
| --- | --- |
| ESOS + ESOS-lite | Pinned source preparation and native SCons adapter; fresh local cross-build passed |
| OpenSBI | Pending extraction of qualified source pin, local patches and build configuration |
| edk2-platforms | Pinned source with the maintained ACPI patch series exported under `patches/edk2-platforms/` (tables, clock bring-up, GMAC/PCIe/reset fixes, quiet console); applied by `meta.py prepare` via `git apply` |
| Linux | Separate optional driver-validation build; experimental patches are not firmware release inputs |
| FSBL / DDR initialization | External input until source, license and exact binary provenance are established |
| FIT / flash packaging | Separate adapter with explicit payload contracts, board layouts and durable-state exclusions |
| Toolchains | Explicit compiler paths initially; archive hashes and dependency locks required for release builds |

The project builds the ESOS reference payloads. It does not yet package an image,
flash hardware, provide A/B recovery or assert reproducible binaries. Pico and COM260 require
separate qualified profiles; neither is implicitly selected by source preparation.
The current fat firmware layout must not be replaced with a hypothetical compact
layout. Durable configuration and recovery storage need explicit ownership and
must not be covered by generic whole-flash update commands.

## Next build increment

1. ESOS adapter implemented: see [build instructions](docs/esos-build.md).
   Build workspaces are disposable and must be new for each invocation.
2. Pin compiler and SCons/Kconfig dependencies, plus every additional binary input.
3. EDK2-platforms patch series exported with provenance (see
   [docs/edk2-platforms-export.md](docs/edk2-platforms-export.md)); the EDK2
   core / SDK pin and native build adapter remain. OpenSBI pending.
4. Add board profiles and packaging checks against documented flash regions.

A clean machine must eventually reproduce all declared artifacts from the
manifest. Current evidence covers offline orchestration tests and a local ESOS cross-build;
clean-machine provisioning and binary equivalence remain unproven.

## Contributions and licenses

See [provenance](docs/provenance.md). Preserve upstream notices and contributor
attribution. The ACPI integration work is user-authored work derived from DT
research and hardware testing; vendor hardware definitions do not make those
changes vendor-authored. Record actual authorship when exporting those patches.
Do not invent sign-offs or treat upstream acceptance as established.

No blanket license is assigned to this bootstrap or the aggregate firmware yet.
Before publication, the owner must choose a license for new orchestration code;
imported components retain their own licenses and unresolved redistribution
questions must be closed. The project URL is an identity assumption, not proof
that a remote or release exists.
