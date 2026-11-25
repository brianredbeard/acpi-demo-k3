# acpi-demo-k3

A distribution-neutral integration project for K3 ACPI firmware. It keeps
upstream projects independently replaceable, pins inputs, and carries local
changes as reviewable patch series. This directory is the future repository
root; a local Git repository is initialized with that origin. The GitHub repository
has not been created or published by this bootstrap.

## Current commands

Source preparation requires Python 3.9+ and Git. The firmware tests also use
the host tools listed in the EDK2 build instructions below. Run from this directory.

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
| ESOS + ESOS-lite | Pinned source preparation and native SCons adapter; fresh local cross-build passed. The ESOS patch series carries the reset-handoff fix and the RPMI CLOCK service + CCU application-core clocks: **hardware-qualified on pico-acpi-v11 (2026-11-20)** — all 13 RPMI clocks enumerable from Linux with real rates (ufs_aclk = 491.52 MHz), plus host regression for the service callbacks |
| OpenSBI | Pending extraction of qualified source pin, local patches and build configuration |
| edk2-platforms | Pinned source with the maintained ACPI patch series exported under `patches/edk2-platforms/` (12 patches: tables incl. SPCR, complete DSDT v12 with all qualified peripherals + MPXY/RCLK, clock bring-up, GMAC/PCIe/reset fixes, ACPI 6.6 conformance, `_LPI`); applied by `meta.py prepare` via `git apply` |
| Linux | Separate optional driver-validation build; experimental patches are not firmware release inputs |
| FSBL / DDR initialization | External input until source, license and exact binary provenance are established |
| FIT / flash packaging | Pico-ITX EDK2-only candidate, guarded single-region installer transaction and hardware evidence workflow |
| Toolchains | Explicit compiler paths initially; archive hashes and dependency locks required for release builds |

The project also builds ESOS reference payloads through the [ESOS adapter](docs/esos-build.md).
The EDK2 candidate flow below targets the three-port Pico-ITX profile. COM260
requires its own profile and hardware qualification.

## Build and check a Pico-ITX EDK2 candidate

Run these commands on the Linux build host with Git, GNU make, host C/C++,
the RISC-V Linux cross-toolchain in `/usr/bin`, ACPICA (`iasl`, `acpiexec`),
device-tree and U-Boot tools installed. Use fresh build and bundle directories.
Set `RECIPE` to the experiment's reviewed build lock and `PLATFORM_COMMIT` to
the intended full Git commit from the test plan.

```sh
python3 build_edk2.py --destination build/pico-candidate \
  --recipe "$RECIPE" --expect-platform-revision "$PLATFORM_COMMIT"
```

The default build creates private BaseTools, Conf, Build and FIT directories.
`edk2-build.lock.json` identifies the vendor SDK by archive SHA-256 and the
platform by Git commit and ordered patch hashes. For an offline build, pass
`--sdk-archive FILE --platform-repository LOCAL_CLONE` containing those inputs.
Use `--recipe FILE` for a reviewed change to the pins or patches. The build
manifest records the inputs, tool binaries and versions, configuration, and
FD and FIT hashes. Keep a clone or Git bundle containing the pinned platform
commit with the release inputs. The initial pin is available in the
maintained sibling checkout. `--incremental` reuses the development workspace and
produces artifacts for local iteration. An isolated build checks the final FIT
against the three-port profile before publishing the output directory.
The per-run `*.build.log` retains the wrapper's final FIT verdict, including
every rejected field. EDK2's own `- Done -` line precedes that check.
Use `--diagnostic` when an experiment intentionally violates this profile.
Diagnostic and incremental builds still check that the FIT contains the FD
just built. Packaging independently verifies the profile for every candidate.
For an existing image, run `python3 edk2_verify.py /path/to/MUSE-Pico.itb`.

When the builder automatically selects the sibling checkout and the default
recipe, a different HEAD or pending edits stop the build before SDK preparation.
Pass the recipe explicitly to reproduce its committed inputs while someone
else works in the checkout. An expected-revision mismatch also prevents
publication of a bundle. The destination name is only
a label. For example, the first local `out-v8` manifest selected `392fc857`
and the resulting FIT still advertised buses 0–0 on both added roots.
To deliberately select a different committed revision, update the recipe
or pass `--platform-revision "$PLATFORM_COMMIT"`. The build embeds the
effective recipe, including the revision override, with its ordered patches.

The isolated builder takes `SOURCE_DATE_EPOCH` from the selected platform
commit. This sets the build-time inputs to the RTC driver, SMBIOS and
`mkimage`. EFI debug records use workspace-relative paths. To check a rebuild
on the same toolchain, compare both `MUSE-PICO.fd` and `MUSE-Pico.itb`
with `cmp`. Each build manifest retains its actual workspace path for diagnosis.

The verifier decodes the DEFAULT PCD database and evaluates the AML in the FIT
selected for boot. The three-port profile requires mask `0x15`, a reachable
secondary bus, and a 1 MiB PCI I/O window starting at zero on each of segments
2 and 4. The CPU bases are `0x1200010000` and `0x12c0010000`, respectively.
The AML must describe the same resources. Only segment 0 belongs in MCFG.
The initial platform pin `392fc857` reproduces the v7 source state. Its
resource definitions fail this profile even after a clean build.

For the v8 bus-range experiment, this command selects the bus-fix commit,
enables full PCI serial tracing, and verifies that both the packaged PCD
and AML describe buses 0–255 on segments 2 and 4.

```sh
v8_commit=b25849e13c47194f763cbe5f094291209011a55c
python3 build_edk2.py --destination build/v8-bus-trace \
  --platform-revision "$v8_commit" --expect-platform-revision "$v8_commit" \
  --serial-trace --diagnostic --expect-bus-limit 0xff
```

`--serial-trace` selects DEBUG, serial output, and all print levels. It
checks the generated logging masks and matches both linked PCI driver
executables to the copies inside the FD. The manifest records the trace
driver hashes and any differences from the release PCIe profile. To check
an already-built experiment, run `python3 edk2_verify.py --diagnostic
--expect-bus-limit 0xff /path/to/MUSE-Pico.itb`.

For packaging, set `BASELINE` to the qualified bundle directory,
`BASELINE_SHA256` to the **manifest digest from its retained qualification or
verified transaction**, and `INSTALLER` to the production `k3-firmware`
executable. Record what the candidate changes.

```sh
python3 edk2_release.py package --build build/pico-candidate \
  --expect-platform-revision "$PLATFORM_COMMIT" \
  --baseline "$BASELINE" --baseline-sha256 "$BASELINE_SHA256" \
  --destination artifacts/pico-candidate --installer "$INSTALLER" \
  --reason "Correct PCI I/O allocation for the two Realtek endpoints"
```

Packaging checks every baseline payload, verifies the packaged FD against
the build manifest, runs the ACPI regression suite against the actual FIT,
and runs the installer's `inspect` before publishing. The JSON result includes
the **candidate manifest SHA-256**. Use that digest to select the candidate
for flash, readback and boot qualification. The operator procedure and
required evidence are in the [EDK2 qualification guide](docs/edk2-qualification.md).

The archived v7 FIT (`b81858ac…`) exercises the stale-PCD failure. Its
packaged segment 2 and 4 I/O sizes are zero. The verified v7b readback
(`e1788860…`) exercises a different failure. Its I/O sizes are 1 MiB but
its bus limits are zero, excluding the secondary bus. Both should fail
`edk2_verify.py`. Host tests with a corrected recipe exercise the successful
packaging path. Hardware qualification requires the readback and boot
evidence for the specific candidate.

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
