#!/usr/bin/env python3
"""Check packaged ACPI tables when K3_EDK2_TEST_FIT selects a candidate.
Local unit-test runs can still use the existing incremental build output.
"""
from functools import lru_cache
import os
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT.parent / "Build" / "MUSE-Pico" / "RELEASE_GCC5"
OUTPUT = BUILD / "RISCV64" / "Platform" / "Spacemit" / "K3" / "AcpiTables" / "K3AcpiTables" / "OUTPUT"
MCFG = OUTPUT / "Mcfg.acpi"
DSDT = OUTPUT / "Dsdt" / "Dsdt.aml"

IASL = "/usr/bin/iasl"

FIT = os.environ.get("K3_EDK2_TEST_FIT")


@lru_cache(maxsize=1)
def tables_from_fit():
    from edk2_verify import packaged_tables
    return packaged_tables(Path(FIT))


def table_bytes(signature, incremental):
    if FIT is not None:
        return tables_from_fit()[signature]
    return incremental.read_bytes()


EXPECTED_SEGMENTS = {
    0: 0x1100000000,
    2: 0x1200000000,
    4: 0x12C0000000,
}

EXPECTED_MCFG_SEGMENTS = {0: 0x1100000000}

# rfkill device -> (pin on \_SB.GPIO, name, type)
EXPECTED_RFKILL = {
    "WLEN": (35, "rfkill-pcie-wlan", "wlan"),
    "BTEN": (30, "rfkill-usb-bt", "bluetooth"),
}


def parse_mcfg(data):
    """Parse an MCFG table into {segment: (base, start_bus, end_bus)}."""
    length = struct.unpack_from("<I", data, 4)[0]
    entries = {}
    off = 44  # ACPI header (36) + MCFG reserved qword (8)
    while off + 16 <= length:
        base, seg, start, end = struct.unpack_from("<QHBB", data, off)
        entries[seg] = (base, start, end)
        off += 16
    return entries


@lru_cache(maxsize=1)
def decompile_dsdt():
    """Decompile the built DSDT AML with iasl; return the DSL text."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "Dsdt.aml"
        dst.write_bytes(table_bytes("DSDT", DSDT))
        subprocess.run([IASL, "-d", str(dst)], check=True, capture_output=True)
        return (Path(tmp) / "Dsdt.dsl").read_text()


@unittest.skipUnless(FIT is not None or MCFG.exists(), f"built MCFG not found: {MCFG}")
class McfgSegmentTests(unittest.TestCase):
    def test_single_entry(self):
        """Only segment 0 in MCFG — the compact-ECAM platform rule."""
        entries = parse_mcfg(table_bytes("MCFG", MCFG))
        self.assertEqual(sorted(entries), [0])

    def test_segments_and_bases(self):
        entries = parse_mcfg(table_bytes("MCFG", MCFG))
        for seg, base in EXPECTED_MCFG_SEGMENTS.items():
            self.assertIn(seg, entries, f"segment {seg} missing from MCFG")
            self.assertEqual(entries[seg][0], base)

    def test_bus_ranges(self):
        for seg, (_, start, end) in parse_mcfg(table_bytes("MCFG", MCFG)).items():
            self.assertEqual((start, end), (0, 0xFF))

@unittest.skipUnless(FIT is not None or (DSDT.exists() and Path(IASL).exists()),
                     f"built DSDT or iasl unavailable ({DSDT})")
class DsdtSegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsl = decompile_dsdt()
    def test_pci2_pci4_root_bridges(self):
        for name in ("PCI2", "PCI4"):
            self.assertRegex(self.dsl, rf"Device \({name}\)")

    def test_seg_values(self):
        self.assertRegex(self.dsl, r"Device \(PCI2\)[\s\S]{0,600}?_SEG, 0x02")
        self.assertRegex(self.dsl, r"Device \(PCI4\)[\s\S]{0,600}?_SEG, 0x04")

    def test_ecam_consumers(self):
        # RES2/RES4 reserve the MCFG ECAM regions as consumers
        self.assertRegex(self.dsl, r"Device \(RES2\)[\s\S]{0,800}?0x0*1200000000")
        self.assertRegex(self.dsl, r"Device \(RES4\)[\s\S]{0,800}?0x0*12C0000000")


    def test_dbi_reservations(self):
        for dev, base in (("DBI2", "0x0*80800000"), ("DBI4", "0x0*81000000")):
            self.assertRegex(self.dsl, rf"Device \({dev}\)[\s\S]{{0,600}}?{base}")


@unittest.skipUnless(FIT is not None or (DSDT.exists() and Path(IASL).exists()),
                     f"built DSDT or iasl unavailable ({DSDT})")
class DsdtRfkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsl = decompile_dsdt()

    def test_rfkill_devices_present(self):
        for name in EXPECTED_RFKILL:
            self.assertRegex(self.dsl, rf"Device \({name}\)")

    def test_rfkill_compatible(self):
        # both devices bind rfkill-gpio via PRP0001 + compatible
        self.assertEqual(self.dsl.count('"rfkill-gpio"'), 2)

    def test_rfkill_gpio_pins(self):
        for name, (pin, _, _) in EXPECTED_RFKILL.items():
            block = re.search(rf"Device \({name}\)[\s\S]*?(?=\n        Device|\n    \}})", self.dsl)
            self.assertIsNotNone(block, f"{name} device block not found")
            text = block.group(0)
            self.assertIn('"\\\\_SB.GPIO"', text)
            self.assertRegex(text, rf"0x{pin:04X}")

    def test_rfkill_dsd_properties(self):
        for name, (_, rf_name, rf_type) in EXPECTED_RFKILL.items():
            self.assertIn(f'"{rf_name}"', self.dsl)
            self.assertIn(f'"{rf_type}"', self.dsl)
        self.assertEqual(self.dsl.count('"shutdown-gpios"'), 2)


class IaslAvailabilityTests(unittest.TestCase):
    def test_iasl_available(self):
        self.assertTrue(Path(IASL).exists(), "iasl required for AML verification")


if __name__ == "__main__":
    unittest.main()
