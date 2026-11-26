# rhct17-varwrite reproduction

The qualified firmware (manifest sha 8ef21a8b...) rebuilds
byte-identically (FD 55a8a5ca, FIT 31c003f3 — verified
2026-11-25) from a fresh checkout:

```sh
git clone <this repo> && cd acpi-demo-k3
python3 build_edk2.py \
  --destination build/rhct17 \
  --recipe patches/edk2-platforms/rhct17-varwrite/recipe.json \
  --sdk-archive build/edk2-spacemit_0.0.9.tar.xz \
  --platform-repository /home/bharring/Projects/software/edk2-platforms
```

Inputs:
- platform revision 64ba91f04452f17e8e4defd011a580e1311102aa
  (patchless — the runtime-flash content is in-tree), carried
  on github branch `k3-acpi-raw`. Branch topology (2026-11-25):
  the raw 66-commit development line was renamed `k3-acpi` ->
  `k3-acpi-raw`; the consolidated patch set (one commit per
  topic: ACPI tables, AcpiClockInitDxe, AcpiPowerInitDxe,
  runtime-safe flash, PCIe segments, ...) is being assembled
  as the new `k3-acpi` (intermediate state: the
  `k3-acpi-validation` branch). The recipe pins the exact
  hash — the branch names are context, not resolution.
  The local mirror /home/bharring/Projects/software/edk2-platforms
  also carries the revision (the worktree's origin).
- SDK archive edk2-spacemit_0.0.9.tar.xz, sha256
  9b14187818a2938578298ca24fd9e0038adbaada839988d1daf2b50f49c1f01a
  (downloadable from the recipe's URL; the local copy lives in
  build/).

Then package with edk2_release.py against the rhct16 baseline
(manifest 048a1473...) to reproduce the bundle.
