#!/usr/bin/env python3
"""The kernel spec's patch sequence is load-bearing.

The 2026-11-21:45 incident: the repo's reference spec carried only
3 of the 9 K3 patches while the builder's spec had accumulated the
rest through ad-hoc edits; scp'ing the reference over the builder
silently dropped six patches from a build. This test pins the
complete declared + applied sequence so any divergence between
the repo spec and reality fails loudly at test time, not at boot.
"""
import re
import unittest
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "patches/kernel-rpm/series/el10-284/kernel.spec"

# The complete K3 patch set, in declaration order.
EXPECTED_PATCHES = [
    ("Patch900002", "k3-ufs-acpi-build5.patch"),
    ("Patch900003", "k3-gpio-acpi-v3.patch"),
    ("Patch900004", "k3-espi-acpi-fix.patch"),
    ("Patch900005", "k3-rfkill-gpio-prp0001.patch"),
    ("Patch900006", "k3-8250-xscale-quirk.patch"),
    ("Patch900007", "k3-ecam-segs24.patch"),
    ("Patch900008", "k3-cros-ec-riscv.patch"),
    ("Patch900009", "k3-cros-ec-sizes.patch"),
    ("Patch900010", "k3-tsensor-acpi-zones.patch"),
    ("Patch900011", "k3-pwmfan-acpi-cooling.patch"),
]


class KernelSpecSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = SPEC.read_text()

    def test_all_patches_declared(self):
        for tag, name in EXPECTED_PATCHES:
            self.assertIn(f"{tag}: {name}", self.spec,
                          f"{tag} ({name}) missing from the spec declarations")

    def test_all_patches_applied(self):
        for _, name in EXPECTED_PATCHES:
            self.assertIn(f"ApplyPatch {name}", self.spec,
                          f"ApplyPatch {name} missing from the spec")

    def test_no_stale_patch_names(self):
        """Old/replaced patch names must not linger."""
        for stale in ("k3-gpio-acpi.patch",):
            self.assertNotIn(f"ApplyPatch {stale}", self.spec,
                             f"stale patch name applied: {stale}")
            self.assertNotIn(f"Patch900003: {stale}", self.spec,
                             f"stale patch name declared: {stale}")

    def test_gpio_precedes_ecam(self):
        """The audit team's ordering: Patch900007 applies after GPIO."""
        lines = [l.strip() for l in self.spec.splitlines()]
        applies = [l for l in lines if l.startswith("ApplyPatch k3-")]
        gpio = next(i for i, l in enumerate(applies) if "gpio" in l)
        ecam = next(i for i, l in enumerate(applies) if "ecam" in l)
        self.assertLess(gpio, ecam, "k3-ecam must apply after the GPIO patch")

    def test_patch_files_exist(self):
        base = SPEC.parent
        for _, name in EXPECTED_PATCHES:
            self.assertTrue((base / name).is_file(),
                            f"declared patch file missing: {name}")


if __name__ == "__main__":
    unittest.main()
