# Reproduce Pico-ITX rhct17b EDK2 firmware

The `rhct17-varwrite` directory contains the **corrected rhct17b** recipe. On the qualified Pico boot, Linux enumerated I2C8 and returned `EPERM` for the tested runtime variable write. The earlier rhct17 image panicked on that operation. [Boot and qualification record](../../../docs/rhct12-firmware-acpi-audit-2026-11-22.md#rhct17b-qualified-2026-11-25)

## Build and compare the firmware

Run from the repository root with the [EDK2 build prerequisites](../../../README.md#build-and-verify-pico-edk2) and a fresh destination.

```sh
python3 build_edk2.py --destination build/rhct17 \
  --recipe recipes/edk2/rhct17-varwrite/recipe.json \
  --expect-platform-revision 64ba91f04452f17e8e4defd011a580e1311102aa
sha256sum build/rhct17/MUSE-PICO.fd build/rhct17/MUSE-Pico.itb
```

The fresh-checkout reproduction recorded on 2026-11-25 matched both artifacts.

| Output | Expected SHA-256 |
| --- | --- |
| `MUSE-PICO.fd` (firmware device image) | `55a8a5ca3c3f5176240b1bba59361736156aa38125582ebf631811cac252d86e` |
| `MUSE-Pico.itb` (packaged FIT) | `31c003f31fd8cf9570ab7ad6ebbe96aaa659bba61e1eec01cb9ab1958e13235e` |

## Pinned inputs

The [recipe](recipe.json) selects platform commit `64ba91f04452f17e8e4defd011a580e1311102aa`, available on `k3-acpi-raw`. The commit contains the runtime-flash changes. The recipe's patch list is empty. For the branch rename and consolidation history, see its dated `branch_note`.

The SDK archive is `edk2-spacemit_0.0.9.tar.xz`, SHA-256 `9b14187818a2938578298ca24fd9e0038adbaada839988d1daf2b50f49c1f01a`. The builder uses a cached archive in `build/` or downloads it from the recipe URL. For an offline build, pass `--sdk-archive` with the archive path and `--platform-repository` with a local Git clone containing the commit.

## Installer bundle

To package a candidate from this build, use `edk2_release.py package` with the qualified rhct16 baseline. Its manifest SHA-256 was `048a14735c8ace49e7ca8b4daa2e1333ec49f0e0f7df4aa5c6f5973d6a14ff0e`. The **original** rhct17b bundle manifest SHA-256 was `8ef21a8bae873cb74b087c6a99f98c073c8bdb50ad3e0e2891760074c00356da`. Packaging seals the local build provenance and release name as well as the payloads, so retain the digest printed for each newly packaged bundle. [Packaging procedure](../../../README.md#package-an-edk2-only-candidate)
