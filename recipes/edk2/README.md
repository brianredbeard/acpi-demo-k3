# Pico-ITX EDK2 build recipes

Select one recipe with `python3 build_edk2.py --destination <fresh-dir> --recipe <recipe.json>` from the repository root. Each pins the SDK, platform commit, and any patches applied to that commit. Patch filenames resolve relative to the recipe. Running the builder without `--recipe` selects the [default build lock](../../edk2-build.lock.json).

| Recipe | What it reproduces |
| --- | --- |
| [rhct17-varwrite](rhct17-varwrite/README.md) | Qualified rhct17b firmware with I2C8 and a clean refusal of unsupported runtime variable writes. Use this for the rhct17b rebuild. |
| [rhct16-gpio35](rhct16-gpio35/recipe.json) | Wi-Fi bring-up with the firmware GPIO35 hold. |
| [rhct15-power](rhct15-power/recipe.json) | The earlier power-rail and RPMI request-channel changes. |
| [runtime-flash](runtime-flash/recipe.json) | The EFI runtime flash driver candidate based on rhct13. |
| [f2-platform-config](f2-platform-config/recipe.json) | The F2 Platform Manager setup menu candidate based on rhct13. |
