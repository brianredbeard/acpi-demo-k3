"""Execute the flash drivers from an isolated RELEASE build on a mock runtime map."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WORKSPACE = os.environ.get("K3_EDK2_RUNTIME_WORKSPACE")
HARNESS = Path(__file__).parent / "efi-runtime"


@unittest.skipUnless(WORKSPACE, "select a retained EDK2 workspace with K3_EDK2_RUNTIME_WORKSPACE")
class FlashRuntimeTests(unittest.TestCase):
    def run_driver(self, harness, module, scenarios):
        workspace = Path(WORKSPACE).resolve()
        silicon = Path("Silicon/Spacemit")
        platform = workspace / "edk2-platforms" / silicon
        source = Path("Drivers") / module
        generated = workspace / "Build/MUSE-Pico/RELEASE_GCC5/RISCV64" / silicon / source
        header, = generated.glob("*/DEBUG/AutoGen.h")
        sdk = workspace / "edk2"
        arch = os.uname().machine
        bind = {"x86_64": "X64", "riscv64": "RiscV64", "aarch64": "AArch64"}[arch]
        abi = ["-DEFIAPI=__attribute__((ms_abi))"] if arch == "x86_64" else []
        includes = [platform / source, platform / "Include", sdk / "MdePkg/Include" / bind]
        includes += [sdk / pkg / "Include" for pkg in ("MdePkg", "MdeModulePkg", "EmbeddedPkg")]
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "test"
            flags = ["cc", "-fshort-wchar", "-ffunction-sections", "-fdata-sections",
                     "-DMDEPKG_NDEBUG", *abi, *[f"-I{path}" for path in includes]]
            objects = []
            if harness == "fvb.c":
                variable = Path("MdeModulePkg/Universal/Variable/RuntimeDxe")
                generated_root = workspace / "Build/MUSE-Pico/RELEASE_GCC5/RISCV64"
                var_header = generated_root / variable / "VariableRuntimeDxe/DEBUG/AutoGen.h"
                obj = Path(tmp) / "variable.o"
                subprocess.run([*flags, "-include", var_header, f"-I{sdk / variable}",
                                "-c", HARNESS / "variable.c", "-o", obj], check=True)
                objects.append(obj)
            subprocess.run([*flags, "-include", header, HARNESS / harness, *objects,
                            "-Wl,--gc-sections", "-o", exe], check=True)
            for scenario in scenarios:
                with self.subTest(scenario=scenario):
                    subprocess.run([exe, scenario], check=True, cwd=tmp, timeout=10)

    def test_fvb(self):
        self.run_driver("fvb.c", "FlashFvbDxe", ["nonidentity", "identity", "high-va", "missing-spi", "missing-region"])

    def test_nor(self):
        self.run_driver("nor.c", "Spi/SpiNorFlashDxe", ["nonidentity", "missing-map", "program-timeout", "enable-timeout"])

    def test_controller(self):
        self.run_driver("qspi.c", "Spi/STQspiDxe", ["nonidentity", "missing-map", "sfar-timeout", "reset-timeout"])
