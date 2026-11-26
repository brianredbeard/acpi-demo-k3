# acpi-demo-k3

This repository builds and checks ACPI firmware for the SpacemiT K3 MUSE-Pico (Pico-ITX) and carries the Linux patches used with it. The **rhct17b** EDK2 recipe reproduces the firmware tested on the board. The **Pico EL10 kernel build 6** record covers the packaged kernel boot, including GMAC, Wi-Fi, I2C, and the thermal governor. COM260 has a separate hardware profile. [Pico qualification log](docs/rhct12-firmware-acpi-audit-2026-11-22.md) · [COM260 notes](docs/com260-contribution-plan-2026-11-24.md)

| What do you want to do? | Start here |
| --- | --- |
| Rebuild the qualified Pico EDK2 image and compare its hashes | [rhct17b build instructions](recipes/edk2/rhct17-varwrite/README.md) |
| Choose another EDK2 build, such as the F2 setup candidate | [Recipe index](recipes/edk2/README.md) |
| Build ESOS or change a firmware patch | [ESOS build instructions](docs/esos-build.md) · [Patch guide](patches/README.md) |
| Build the full EL10 kernel or one driver RPM | [Kernel guide](patches/kernel/README.md) |
| Package a candidate and collect board evidence | [Qualification procedure](docs/edk2-qualification.md) · [Board operating rules](AGENTS.md) |

## Check a checkout

Run from the repository root. Python 3.9+ and Git are sufficient for source preparation.

```sh
python3 meta.py validate
python3 meta.py plan
```

`validate` checks the structure of the source lock and the SHA-256 of local patches and configs. `plan` also prints each repository, revision, destination, and patch count. Neither command fetches sources.

To run the host tests, install a C compiler, ACPICA (`iasl`, `acpiexec`), device-tree tools (`dtc`, `fdtget`), and U-Boot's `mkimage`. The ESOS fixture uses the network on first preparation unless `K3_ESOS_CACHE` points to a local Git checkout containing the locked commit.

```sh
python3 -m unittest discover -s tests
```

Firmware-dependent checks use `K3_EDK2_TEST_FIT` for a built Pico FIT and `K3_EDK2_RUNTIME_WORKSPACE` for the retained runtime-flash build workspace. Two ECAM source checks also use a sibling `../edk2-platforms` checkout. Check the suite's skip count when comparing results. [Runtime test setup](docs/fwts-17-failures-triage-2026-11-23.md)

## Prepare the locked sources

| Component in `sources.lock.json` | What preparation supplies |
| --- | --- |
| ESOS and ESOS-lite | The main tree with 12 patches and its nested lite dependency. The ESOS build adapter installs the two locked configs and builds both payloads. |
| edk2-platforms | The ACPI bring-up series applied to its original platform baseline. For rhct17b, the EDK2 builder uses the platform revision in the selected recipe. |
| OpenSBI | The vendored tree at `51a9d0f9`, with its changes already in the commit. The lock's Git URL points to a workstation-local repository. [Snapshot provenance](patches/opensbi/0001-k3_corepm-retentive-default-suspend.patch) |

To prepare **all four components**, the host must have access to each repository, including the OpenSBI snapshot. Use a fresh destination. A portable mirror can be selected in a copy of the manifest alongside the original, preserving the relative patch paths. The global `--manifest FILE` option goes before `prepare`.

```sh
python3 meta.py prepare --destination sources/k3
```

Preparation checks out detached commits and applies patches in lock order. `prepared.json` appears after the last component succeeds. A failed preparation leaves the partial directory for inspection. Submodule dependencies must have their own lock entries. The EDK2 SDK, FSBL/DDR binaries, and toolchains have separate provenance from this source workspace.

## Build and verify Pico EDK2

Use a Linux host with Git, GNU make, host C/C++, `/usr/bin/riscv64-linux-gnu-*`, ACPICA, device-tree tools, and U-Boot tools. The builder also uses `tar` with xz support and `curl` to download an uncached SDK. Check space on the build filesystem before starting and choose a new output directory.

```sh
RECIPE=recipes/edk2/rhct17-varwrite/recipe.json
PLATFORM_COMMIT=64ba91f04452f17e8e4defd011a580e1311102aa
python3 build_edk2.py --destination build/pico-candidate \
  --recipe "$RECIPE" --expect-platform-revision "$PLATFORM_COMMIT"
python3 edk2_verify.py build/pico-candidate/MUSE-Pico.itb
```

The default build mode creates a private workspace and builds RELEASE firmware with ACPI enabled. The output directory contains `MUSE-PICO.fd`, the packaged `MUSE-Pico.itb`, and `manifest.json` with the recipe, tool versions, and artifact hashes. The adjacent `*.build.log` records the final verification result. For a repeat build, compare both the FD and FIT on the same toolchain. The builder sets `SOURCE_DATE_EPOCH` from the platform commit and makes EFI debug paths workspace-relative.

| Option | When to use it |
| --- | --- |
| `--sdk-archive FILE --platform-repository LOCAL_CLONE` | Build offline with the pinned archive and a Git repository containing the selected platform commit. |
| `--recipe FILE` | Select the intended build. Without this flag, an isolated build uses the [default rhct13 lock](edk2-build.lock.json). An automatically selected sibling checkout must match the pin and be clean when all source options are implicit. |
| `--platform-revision COMMIT` | Override the recipe for a reviewed experiment. The build records the effective recipe. `--expect-platform-revision` checks the selection before SDK preparation. |
| `--keep-workspace` | Retain the private workspace for inspecting compiled drivers or running the runtime harness. |
| `--incremental` | Iterate in a prepared sibling development workspace. Packaging requires an isolated build manifest. |

The verifier reads the default platform configuration database (PCD) and evaluates the AML in the final FIT. The three-port profile requires enable mask `0x15`, segment 0 in MCFG, and reachable secondary buses on segments 2 and 4. Each of those segments needs a 1 MiB PCI I/O window starting at zero, translated to CPU addresses `0x1200010000` and `0x12c0010000`, respectively.

### Diagnostic builds and the archived v8 experiment

For a diagnostic build, `--serial-trace` selects DEBUG and checks the packaged PCI drivers. `--diagnostic` retains output with release-profile differences. For supported PCD layouts, `--expect-bus-limit 0xff` also requires buses 0–255 on segments 2 and 4 in both the PCD and AML.

The archived v8 bus-range FIT (`45668dad…`, platform `b25849e1`) uses an older PCD layout. The current verifier stops at `unexpected PCIe bridge array shape` even in diagnostic mode. Use the retained v8 report for the original measurements. [Qualification record](docs/edk2-qualification.md) · [Decoder compatibility finding](docs/project-audit-33daace.md)

## Package an EDK2-only candidate

Set `BASELINE` to the qualified bundle, `BASELINE_SHA256` to the manifest digest from its qualification or verified transaction, and `INSTALLER` to the production `k3-firmware` executable. Set `CHANGE` to the single intended change. Use the platform commit selected at build time.

```sh
python3 edk2_release.py package --build build/pico-candidate \
  --expect-platform-revision "$PLATFORM_COMMIT" \
  --baseline "$BASELINE" --baseline-sha256 "$BASELINE_SHA256" \
  --destination artifacts/pico-candidate --installer "$INSTALLER" \
  --reason "$CHANGE"
```

Packaging verifies the baseline, checks that only the EDK2 FIT's `uefi` payload changed, runs the ACPI tests on the packaged FIT, and requires installer inspection before publishing the candidate. Save the returned `bundle_sha256` for readback and boot qualification. [Operator procedure and required evidence](docs/edk2-qualification.md)

## Audit history and attribution

The November 20 audit records the release decision at `d3daf37` and a manifest failure at `9b95f32`. The original results and checksum inventory describe those snapshots. Commit `8a0d609` later updated the paths in `clocks-drivers.md`, so that file differs from its recorded digest. The later FIT investigation identified the regenerated RCPU device tree as the cause of the clock-service regression. [Sealed audit](docs/audit-2026-11-20/README.md) · [Recovery amendment](docs/audit-2026-11-20/RECOVERY-AMENDMENT.md) · [FIT post-mortem](docs/per-clock-rate-policy-2026-11-20.md#the-actual-root-cause-supersedes-everything-above-the-regenerated-rcpu0-dtb)

Preserve upstream notices and actual contributor attribution when exporting patches. The ACPI integration work derives from device-tree research and hardware testing. Imported components retain their own licenses. The repository has no aggregate firmware license, and redistribution questions remain open. [Provenance and licensing notes](docs/provenance.md)
