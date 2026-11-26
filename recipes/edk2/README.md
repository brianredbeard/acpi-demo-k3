# Pico-ITX EDK2 build recipes

For the firmware qualified with the EL10 build 6 kernel, use the **rhct17b** recipe. The other recipes reproduce earlier bring-up steps or separate setup and runtime-flash candidates.

| Recipe | Platform commit | What it builds |
| --- | --- | --- |
| [rhct17-varwrite](rhct17-varwrite/README.md) | `64ba91f0` | Corrected rhct17b firmware with I2C8 and a clean refusal of unsupported runtime variable writes. The guide includes the expected FD and FIT hashes. |
| [rhct16-gpio35](rhct16-gpio35/recipe.json) | `c02a0e90` | Wi-Fi bring-up with the firmware GPIO35 hold. |
| [rhct15-power](rhct15-power/recipe.json) | `209ec532` | Power-rail initialization and the RQTS mailbox channel correction. |
| [runtime-flash](runtime-flash/recipe.json) | `8b171654` | EFI runtime flash driver candidate based on rhct13. [Test setup](../../docs/fwts-17-failures-triage-2026-11-23.md) |
| [f2-platform-config](f2-platform-config/recipe.json) | `8b171654` | F2 Platform Manager setup menu candidate based on rhct13. [Form verification](../../docs/f2-platform-configuration.md) |

From the repository root, pass one `recipe.json` to `build_edk2.py --recipe` and a fresh output directory to `--destination`. Each recipe pins the SDK and full platform commit. Its patch paths resolve relative to that recipe. An isolated build without `--recipe` uses the [default rhct13 build lock](../../edk2-build.lock.json). [Build prerequisites and options](../../README.md#build-and-verify-pico-edk2)
