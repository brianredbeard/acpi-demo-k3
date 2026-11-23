"""Check the fields used by DXE and AML, including the v7 failure mode."""

import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

import edk2_verify as verify


def pcd_fixture():
    # EDK II version 7 DEFAULT DB, two ordinary dynamic tokens (others scalars).
    db = bytearray(1120)
    db[:16] = UUID("3c7d193c-682c-4c14-a68f-552dea4f437e").bytes_le
    struct.pack_into("<IIQI", db, 16, 7, len(db), 0, len(db))
    struct.pack_into("<7IH", db, 40, 80, 0, 0, 256, 1040, 0, 0, 25)
    for i in range(25):
        struct.pack_into("<I", db, 80 + 4*i, 0x01000000 | 181)
    struct.pack_into("<I", db, 80 + 4*24, 0x10000000 | 184)
    struct.pack_into("<I", db, 184, 3)
    db[181] = 0x15
    struct.pack_into("<HH", db, 1040, 777, 777)
    struct.pack_into("<H", db, 259, 5)
    for i in range(5):
        struct.pack_into("<H4Q", db, 261 + 155*i, i, 0, 0x10000, 0, 1)
    struct.pack_into("<H4Q", db, 261, 0, 0x1100000000, 0x10000000, 0, 255)
    for i, config in [(2, 0x1200000000), (4, 0x12c0000000)]:
        struct.pack_into("<Q", db, 261 + 155*i + 2, config)
        struct.pack_into("<3Q", db, 261 + 155*i + 34, 0, 0x100000, config + 0x10000)
    return db


def crs(cpu, limit=1):
    bus = struct.pack("<BHBBB5H", 0x88, 13, 2, 12, 0, 0, 0, limit, 0, limit+1)
    io = struct.pack("<BHBBB5Q", 0x8a, 43, 1, 12, 3, 0, 0, 0xfffff, cpu, 0x100000)
    return bus + io + b"\x79\x00"


class PcieProfileTests(unittest.TestCase):
    def setUp(self):
        self.db = pcd_fixture()
        self.aml = {
            str(seg): {"hid": "PNP0A08", "seg": seg, "bbn": 0,
                       "resources": verify.decode_crs(crs(cpu))}
            for seg, cpu in [(2, 0x1200010000), (4, 0x12c0010000)]
        }

    def check(self):
        verify.check_pcie_profile(verify.decode_pcd(bytes(self.db)), self.aml)

    def test_valid(self):
        self.check()

    def test_expected_bus_limit_checks_pcd_and_aml_independently(self):
        pcd = verify.decode_pcd(bytes(self.db))
        verify.check_bus_limit(pcd, self.aml, 1)
        pcd['segments']['4']['bus'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'segment 4'):
            verify.check_bus_limit(pcd, self.aml, 1)
        pcd['segments']['4']['bus'] = [0, 1]
        self.aml['2']['resources'] = verify.decode_crs(crs(0x1200010000, 0))
        with self.assertRaisesRegex(ValueError, 'segment 2'):
            verify.check_bus_limit(pcd, self.aml, 1)
        self.aml['2']['resources'] = verify.decode_crs(crs(0x1200010000, 1))
        self.aml['2']['seg'] = 4
        with self.assertRaisesRegex(ValueError, 'segment 2'):
            verify.check_bus_limit(pcd, self.aml, 1)

    def test_v7_both_io_windows_zero(self):
        for seg in (2, 4):
            start = 261 + 155*seg + 34
            self.db[start:start+24] = bytes(24)
        with self.assertRaisesRegex(ValueError, r"PCD segment 2 I/O.*size=0x0[\s\S]+PCD segment 4 I/O.*size=0x0"):
            self.check()

    def test_bus_one_required_in_both(self):
        self.aml["2"]["resources"] = verify.decode_crs(crs(0x1200010000, 0))
        with self.assertRaisesRegex(ValueError, "PCI2.*bus"):
            self.check()

    def test_only_active_token_value_counts(self):
        self.db[182] = 0x03
        struct.pack_into("<I", self.db, 80 + 4*19, 0x01000000 | 182)
        with self.assertRaisesRegex(ValueError, "mask"):
            self.check()

    def test_wrong_segment_and_consumer(self):
        self.aml["4"]["seg"] = 2
        # Same numeric window, now describing consumed resources.
        blob = bytearray(crs(0x12c0010000))
        blob[20] |= 1
        self.aml["4"]["resources"] = verify.decode_crs(blob)
        with self.assertRaisesRegex(ValueError, r"PCI4.*_SEG[\s\S]+PCI4.*I/O"):
            self.check()

    def test_boot_drive_ecam_still_covers_segment_zero(self):
        struct.pack_into("<Q", self.db, 261+10, 0x10000)
        with self.assertRaisesRegex(ValueError, "segment 0.*MCFG"):
            self.check()

    def test_wrong_translation(self):
        self.aml["2"]["resources"] = verify.decode_crs(crs(0x1200000000))
        with self.assertRaisesRegex(ValueError, "PCI2.*I/O"):
            self.check()

    def test_out_of_bounds_pointer(self):
        struct.pack_into("<I", self.db, 184, 0xffffffff)
        with self.assertRaises(ValueError):
            self.check()


class CompiledDsdtTests(unittest.TestCase):
    def test_bridge_owns_its_resources(self):
        # Each nested device has a convincing, correct-looking _CRS. The
        # parent PCI4 template describes the wrong CPU window.
        def template(cpu):
            return f"""ResourceTemplate () {{
                WordBusNumber (ResourceProducer, MinFixed, MaxFixed, PosDecode,
                               0, 0, 1, 0, 2)
                QWordIO (ResourceProducer, MinFixed, MaxFixed, PosDecode, EntireRange,
                         0, 0, 0xfffff, {cpu:#x}, 0x100000)
            }}"""

        def bridge(seg, parent, child):
            return f"""Device (PCI{seg}) {{
                Name (_HID, "PNP0A08")
                Name (_BBN, Zero)
                Name (_SEG, {seg})
                Name (_CRS, {template(parent)})
                Device (RES{seg}) {{
                    Name (_HID, "PNP0C02")
                    Name (_CRS, {template(child)})
                }}
            }}"""

        cpu2, cpu4 = 0x1200010000, 0x12c0010000
        asl = ('DefinitionBlock ("", "DSDT", 2, "SPMT", "K3", 1) { Scope (_SB) {'
               + bridge(2, cpu2, cpu2) + bridge(4, cpu2, cpu4) + "}}")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "roots.asl"
            source.write_text(asl)
            subprocess.run(["iasl", str(source)], check=True, cwd=tmp, capture_output=True)
            aml = verify.decode_dsdt(source.with_suffix(".aml").read_bytes())
        with self.assertRaisesRegex(ValueError, "PCI4.*I/O"):
            verify.check_pcie_profile(verify.decode_pcd(bytes(pcd_fixture())), aml)
        self.assertEqual(aml["4"]["resources"][1]["translation"], cpu2)


class ArchivedRegression(unittest.TestCase):
    def test_v7_when_available(self):
        fit = Path.home() / "bundles/pico-acpi-rhct11-wifi-v7/payloads/edk2.bin"
        if not fit.is_file():
            self.skipTest("archived full-image regression fixture unavailable")
        # 2026-11-23: the bridge-array token moved 24 -> 25 (the SKU
        # geometry PCD); archived pre-2026-11-23 bundles carry the old
        # layout, so their first failure is now the array-shape check
        # (wrong pointer) rather than the I/O-size profile error.
        with self.assertRaisesRegex(ValueError, "unexpected PCIe bridge array shape|"
                                    r"PCD segment 2 I/O.*size=0x0[\s\S]+PCD segment 4 I/O.*size=0x0"):
            verify.verify_fit(fit)
