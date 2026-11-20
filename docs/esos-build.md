# Native ESOS reference build

From the project root:

```sh
python3 build_esos.py \
  --destination build/esos-01 \
  --python /absolute/path/to/build-venv/bin/python \
  --compiler-dir /absolute/path/to/elf-toolchain/bin \
  --jobs 8
```

The Python environment must contain SCons and Kconfiglib. The tested versions
are Python 3.14.10, SCons 4.11.1 and Kconfiglib 14.1.0. The tested compiler is
Spacemit ELF/newlib GCC 14.2.1 (20250123). This is a known working toolchain,
not a requirement for a vendor operating system. Compatibility with other ELF
compilers is not yet established. No package installation is performed.

Optional offline Git caches:

```sh
  --repository esos=/absolute/path/to/esos-cache \
  --repository esos-lite=/absolute/path/to/esos-lite-cache
```

These change only the transport. Revisions and patch hashes remain locked;
modified working files in the cache are not copied. Complete caches are preferred.
The ESOS manifest declares a sparse checkout of the source directories needed
by this adapter; root files are included by Git cone mode. Incomplete promisor
caches may emit missing-object diagnostics for unrelated directories even when
Git returns success. They are not evidence of a fully available upstream mirror.

The destination must not exist. The adapter prepares sources, writes the two
verified configurations, generates the required `version_id_gen.cc`, builds
lite, installs its binary into the main source BSP, then builds main. Each tree
uses its own native Kconfig converter. Version text identifies the input manifest;
`build.json` additionally identifies the adapter scripts and build tools.

Outputs:

- `artifacts/esos_lite.bin` and `artifacts/rtthread.bin`.
- `configs/`: exact configuration inputs.
- `logs/`: header conversion, configuration and build output per component.
- `sources/prepared.json`: source pins, input hashes and cache overrides.
- `build.json`: success/failure, commands, selected environment, tool versions,
  recipe hashes, generated version and artifact hashes/sizes.

Failures retain logs and report `failed`; partial artifacts may remain and must
not be treated as a successful build. No existing checkout or firmware device
is modified. The code trusts reviewed source repositories and their build scripts.

## Qualification on 2026-11-19

A fresh build from the local Git caches passed using the versions above.
Initial clean-build testing found the historical workspace had supplied an
untracked version header; the adapter now generates it explicitly. The local
partial ESOS cache emitted two missing `.gitee` object diagnostics during checkout;
these remain a cache-completeness limitation, not suppressed build errors.

This is the rt24/os0_rcpu reset reference, not a COM260 qualification or full FIT.
No packaging, flashing, hardware testing, clean-machine download test or
bit-for-bit comparison with historical firmware was performed. Two fresh local
builds produced identical lite binaries but different main hashes: string
comparison found an embedded absolute source path from `dtb_base.c`. Compiler
prefix mapping is a follow-on reproducibility task. See
[recorded evidence](esos-build-evidence.json). Compiler archive,
full toolchain contents, Python wheels and transitive native host tools still
need immutable locks before a reproducible-release claim is warranted.
