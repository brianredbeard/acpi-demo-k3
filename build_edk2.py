#!/usr/bin/env python3
"""Reproducible EDK2 build for the K3 MUSE-Pico firmware.

The canonical build recipe, extracted from the qualified invocation
recorded in tools/build-com260-efi-edge.py (env baked into a script,
which is why it never drifted). This tool exists so the recipe is
executable and conspicuous — AGENTS.md prose had drifted (a
nonexistent efi-development path) and cost a rebuild cycle on
2026-11-20.

Environment contract (all enforced here, none left to the caller):
  WORKSPACE            = k3-maintained-efi root
  PACKAGES_PATH        = $WORKSPACE/edk2:$WORKSPACE/edk2-platforms
                        (SDK FIRST — the DSC resolves MdePkg & friends
                        from the SDK tree; the maintained edk2-platforms
                        provides Silicon/Spacemit + Platform + Ext4Pkg)
  EDK_TOOLS_PATH       = $WORKSPACE/edk2/BaseTools
  GCC5_RISCV64_PREFIX  = /usr/bin/riscv64-linux-gnu-
  --conf               = $WORKSPACE/Conf   (NOT edk2/Conf — that one
                        carries stock EmulatorPkg/VS2022 defaults)
  cwd                  = $WORKSPACE        (no edksetup.sh sourcing;
                        the wrapper path on PATH is what matters)
  toolchain            = system riscv64-linux-gnu-gcc (GCC5 tag).
                        EDK2 is freestanding: no libc is linked, so the
                        vendor newlib toolchain (mandatory for ESOS via
                        build_esos.py) is NOT required here. Provenance
                        of every qualified bundle records this compiler.

Usage:
  build_edk2.py [--destination DIR] [--debug] [--jobs N]
                [--extra-define KEY=VALUE ...]

Output: MUSE-PICO.fd + MUSE-Pico.itb copied into --destination.
Exit non-zero on any build failure; destination is only populated on
success.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # k3-maintained-efi
SDK = ROOT / "edk2"
PLATFORMS = ROOT / "edk2-platforms"
CONF = ROOT / "Conf"

ARTIFACTS = [
    ("Build/MUSE-Pico/{flavor}_GCC5/FV/MUSE-PICO.fd", "MUSE-PICO.fd"),
    ("fitimage/MUSE-Pico/MUSE-Pico.itb", "MUSE-Pico.itb"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--destination", type=Path, required=True,
                    help="fresh output directory (must not exist)")
    ap.add_argument("--debug", action="store_true",
                    help="DEBUG build instead of RELEASE")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--extra-define", action="append", default=[],
                    metavar="KEY=VALUE",
                    help="additional -D defines (repeatable)")
    args = ap.parse_args()

    for req in (SDK / "MdePkg", PLATFORMS / "Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc",
                CONF / "tools_def.txt"):
        if not req.exists():
            print(f"ERROR: required tree component missing: {req}", file=sys.stderr)
            return 2

    if args.destination.exists():
        print(f"ERROR: destination exists: {args.destination}", file=sys.stderr)
        return 2

    flavor = "DEBUG" if args.debug else "RELEASE"
    defines = ["ACPI_ENABLE=TRUE"] + args.extra_define

    env_base = {
        "WORKSPACE": str(ROOT),
        "PACKAGES_PATH": f"{SDK}:{PLATFORMS}",
        "EDK_TOOLS_PATH": str(SDK / "BaseTools"),
        "PYTHON_COMMAND": "python3",
        "PYTHONPATH": str(SDK / "BaseTools/Source/Python"),
        "GCC5_RISCV64_PREFIX": "/usr/bin/riscv64-linux-gnu-",
        "HOME": str(Path.home()),
    }
    import os
    env = env_base.copy()
    env["PATH"] = (
        f"{SDK}/BaseTools/BinWrappers/PosixLike:"
        f"{SDK}/BaseTools/Source/C/bin:"
        "/usr/bin:/bin"
    )

    command = [
        "build", "-a", "RISCV64",
        "-p", "Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc",
        "-t", "GCC5", "-b", flavor, "-n", str(args.jobs),
    ]
    for d in defines:
        command += ["-D", d]
    command += ["--conf=" + str(CONF)]

    print("== build_edk2.py: canonical K3 EDK2 build")
    print(f"   WORKSPACE     = {ROOT}")
    print(f"   PACKAGES_PATH = {env['PACKAGES_PATH']}")
    print(f"   flavor        = {flavor}  defines = {defines}")
    log_path = args.destination.parent / (args.destination.name + ".build.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        log.write("# command: " + " ".join(command) + "\n")
        log.write("# env: " + repr(env_base) + "\n")
        log.flush()
        rc = subprocess.run(command, cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        print(f"FAILED (rc={rc}); log: {log_path}", file=sys.stderr)
        return rc

    args.destination.mkdir(parents=True)
    import hashlib
    manifest = {"command": command, "env": env_base,
                "flavor": flavor, "defines": defines}
    for src, name in ARTIFACTS:
        s = ROOT / src.format(flavor=flavor)
        if not s.exists():
            print(f"ERROR: expected artifact missing: {s}", file=sys.stderr)
            return 3
        d = args.destination / name
        shutil.copyfile(s, d)
        manifest[name] = {
            "sha256": hashlib.sha256(d.read_bytes()).hexdigest(),
            "bytes": d.stat().st_size,
        }
    compiler = subprocess.run(
        ["/usr/bin/riscv64-linux-gnu-gcc", "--version"],
        capture_output=True, text=True).stdout.splitlines()[0]
    manifest["compiler"] = compiler
    (args.destination / "manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2) + "\n")
    print(f"OK -> {args.destination} (log: {log_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
