import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import edk2_release as release


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "baseline"
        self.build = self.root / "build"
        self.out = self.root / "candidate"
        self.base.mkdir()
        self.build.mkdir()
        self.files = {}
        for name in ("agent", "fsbl", "edk2", "opensbi", "esos"):
            payload = name.encode()
            (self.base / name).write_bytes(payload)
            self.files[name] = {"path": name, "sha256": digest(payload), "size": len(payload)}
        write_json(self.base / "manifest.json", {
            "schema": 1, "board": "pico-itx", "release": "baseline",
            "boot_prefix_sha256": ["1" * 64], "files": self.files, "provenance": {},
        })
        self.base_hash = digest((self.base / "manifest.json").read_bytes())
        file_hash = "5" * 64
        self.manifest = {
            "build_mode": "isolated", "sources": {"recipe_sha256": file_hash,
                "sdk": {"sha256": file_hash}, "platforms": {"revision": "6" * 40,
                "tree": "7" * 40, "patches": []}},
            "arch": "RISCV64", "flavor": "RELEASE", "sku": "ALL", "toolchain_tag": "GCC5",
            "defines": ["ACPI_ENABLE=TRUE"], "command": ["build", "-a", "RISCV64"],
            "conf_sha256": {s + ".txt": file_hash for s in ("target", "build_rule", "tools_def")},
            "toolchain": {"riscv64-linux-gnu-gcc": {"sha256": file_hash, "version": "gcc 1"}},
            "basetools": {"command": ["make"], "binaries_sha256": {"GenFv": file_hash}},
            "pcd_token_abi": {"pei_local_tokens": 0, "mask_token": 20, "bridge_array_token": 25,
                              "headers_sha256": {
                                  "RISCV64/Silicon/Spacemit/K3/Library/K3PcieHostBridgeLib/K3PcieHostBridgeLib/DEBUG/AutoGen.h": file_hash,
                                  "RISCV64/MdeModulePkg/Universal/PCD/Dxe/Pcd/DEBUG/AutoGen.h": file_hash}},
        }
        sources = self.manifest["sources"]
        sources["platforms"]["repository"] = "test-git-remote"
        recipe = {"sdk": sources["sdk"], "platforms": {
            "repository": "test-git-remote", "revision": "6" * 40, "patches": []}}
        recipe_data = json.dumps(recipe).encode()
        sources.update(recipe_sha256=digest(recipe_data), recipe_base64=base64.b64encode(recipe_data).decode())
        for name in ("MUSE-PICO.fd", "MUSE-Pico.itb"):
            data = ("new-" + name).encode()
            (self.build / name).write_bytes(data)
            self.manifest[name] = {"sha256": digest(data), "bytes": len(data)}
        write_json(self.build / "manifest.json", self.manifest)
        self.inspect = patch.object(release, "inspect_bundle").start()
        self.addCleanup(patch.stopall)
        self.compare = patch.object(release, "compare_edk2_fits", return_value={"uefi": "verified"}).start()
        self.acpi = patch.object(release, "check_packaged_acpi").start()
        self.decode = patch.object(release, "verify_fit", return_value={"status": "verified"}).start()

    def package(self):
        return release.package(self.build, self.base, self.base_hash, self.out,
                               Path("/installer"), "test PCI bridge apertures")

    def test_candidate_staged_only_after_inspection(self):
        self.package()
        candidate = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(self.inspect.call_count, 2)
        self.assertEqual(self.compare.call_count, 1)
        self.assertEqual(self.decode.call_count, 1)
        self.assertEqual(self.acpi.call_count, 1)
        self.assertEqual(candidate["firmware_qualification"], "candidate; hardware qualification pending")
        for name in ("agent", "fsbl", "opensbi", "esos"):
            self.assertEqual((self.base / name).read_bytes(), (self.out / name).read_bytes())

    def test_baseline_and_build_are_read_only_inputs(self):
        for root in (self.base, self.build):
            self.out = root / "nested-candidate"
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, "outside"):
                self.package()
            self.assertFalse(self.out.exists())

    def test_bad_inputs_never_publish(self):
        (self.build / "MUSE-PICO.fd").write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError, "MUSE-PICO.fd"):
            self.package()
        self.assertFalse(self.out.exists())

    def test_recorded_platform_commit_must_match_embedded_recipe(self):
        self.manifest['sources']['platforms']['revision'] = 'f' * 40
        write_json(self.build / "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "source recipe differs"):
            self.package()
        self.assertFalse(self.out.exists())

    def test_package_checks_operator_selected_platform_revision(self):
        with self.assertRaisesRegex(ValueError, "expected platform revision"):
            release.package(self.build, self.base, self.base_hash, self.out,
                            Path("/installer"), "test", expected_revision='f' * 40)
        self.assertFalse(self.out.exists())

    def test_template_mutation_never_resealed(self):
        (self.base / "opensbi").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "opensbi"):
            self.package()

    def test_inspection_failure_does_not_publish(self):
        self.inspect.side_effect = [None, ValueError("inspection failed")]
        with self.assertRaisesRegex(ValueError, "inspection"):
            self.package()
        self.assertFalse(self.out.exists())

    def test_legacy_build_rejected(self):
        del self.manifest["build_mode"]
        write_json(self.build / "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "isolated"):
            self.package()

    def test_source_recipe_bytes_must_match_build_metadata(self):
        self.manifest["sources"]["sdk"]["sha256"] = "4" * 64
        write_json(self.build / "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "recipe"):
            self.package()

    def test_missing_pcd_consumer_abi_rejected(self):
        self.manifest["pcd_token_abi"]["mask_token"] = 22
        write_json(self.build / "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "ABI"):
            self.package()

    def test_readback_binds_installer_report_and_full_image(self):
        self.package()
        candidate_hash = digest((self.out / "manifest.json").read_bytes())
        run = self.root / "transaction"
        run.mkdir()
        before = bytearray(b"\xff" * 0x800000)
        for name, start in (("esos", 0xb0000), ("opensbi", 0x1b0000), ("edk2", 0x210000)):
            data = (self.base / name).read_bytes()
            before[start:start+len(data)] = data
        after = before[:]
        data = (self.out / "edk2").read_bytes()
        after[0x210000:0x210000+len(data)] = data
        (run / "nor-before.bin").write_bytes(before)
        (run / "nor-after.bin").write_bytes(after)
        report = {"schema": 1, "status": "verified", "serial": "K3", "completed": ["edk2"],
                  "before_sha256": digest(before), "after_sha256": digest(after),
                  "writes": [{"name": "edk2", "offset": 0x210000, "erase_size": 4096,
                              "size": len(data), "sha256": digest(data)}],
                  "metadata": {"release": "candidate", "board_assertion": "pico-itx",
                               "operation": "flash", "bundle_sha256": candidate_hash}}
        write_json(run / "report.json", report)
        result = release.verify_readback(self.out, candidate_hash, run)
        self.assertEqual(result["bundle_sha256"], candidate_hash)
        with self.assertRaisesRegex(ValueError, "digest"):
            release.verify_readback(self.out, self.base_hash, run)
        after[0] ^= 1
        (run / "nor-after.bin").write_bytes(after)
        report["after_sha256"] = digest(after)
        write_json(run / "report.json", report)
        with self.assertRaisesRegex(ValueError, "outside|NOR"):
            release.verify_readback(self.out, candidate_hash, run)



class BootEvidenceTests(unittest.TestCase):
    def test_preboot_resource_allocation_matches_bridge_and_successful_io_row(self):
        entry = "RootBridge: PciRoot(0x2)\n Mem: Base/Length/Alignment = 1000/1000/FFF - Success\n"
        row = " I/O: Base/Length/Alignment = 1200010000/1000/FFF - Success"
        self.assertTrue(release.has_allocation(entry + row, 2))
        self.assertFalse(release.has_allocation(entry + row, 4))
        self.assertFalse(release.has_allocation(entry + row.replace("Success", "Out Of Resource!"), 2))
        self.assertFalse(release.has_allocation(entry + row.replace("1200010000", "0"), 2))
        self.assertFalse(release.has_allocation(entry + "RootBridge: PciRoot(0x4)\n" + row, 2))

    def test_capture_digest_and_display_excerpts_cross_chunk_boundaries(self):
        data = "µEFI\x1b[1;37m BLK4\x1b[0m:\r\r\nNVMe(1)\r\n".encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "serial"
            path.write_bytes(data)
            for size in (1, 3, 8):
                self.assertEqual(release.scan_capture(path, {"µEFI BLK4:\nNVMe(1)", "NVMe(1)\n"}, size),
                                 digest(data))
            with self.assertRaisesRegex(ValueError, "excerpt"):
                release.scan_capture(path, {"missing"}, 3)

    def test_nvme_ancestry_and_selected_entry(self):
        self.assertFalse(release.has_root_ancestry("sda nvme0n1", "/dev/mapper/rhel-root", "nvme0n1"))
        self.assertFalse(release.selected_rhel_efi("BootCurrent: 0001\nBoot0002* Red Hat Enterprise Linux"))
        self.assertTrue(release.selected_rhel_efi('BdsDxe: starting Boot0007 "Red Hat Enterprise Linux" from PciRoot(0)'))

    def test_operator_evidence_is_bound_to_trace_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = {"bundle_sha256": "1" * 64, "report_sha256": "2" * 64, "serial": "board"}
            boot = "8ab9ce5c-cd21-41b7-a321-473564900ced"
            quotes = {
                "segment2_io": "Seg 2 RTL8127 I/O BAR assigned 0x1000 size 0x100",
                "segment4_io": "Seg 4 RTL8852BE I/O BAR assigned 0x2000 size 0x100",
                "nvme_block_io": "BLK4: PciRoot(0)/NVMe(1)",
                "rhel_grub": "BootCurrent: 0007\nBoot0007* Red Hat Enterprise Linux NVMe(1)/EFI/redhat/grubriscv64.efi",
                "running_root": f'{boot}\n6.12.0-284.el10\nID="rhel"\n/ /dev/mapper/rhel-root\n# lsblk -snro KNAME -- /dev/mapper/rhel-root\ndm-0\nnvme0n1p3\nnvme0n1',
            }
            raw_console = ("\r\r\n".join(quotes.values()) + "\n").replace(
                "BLK4:", "\x1b[1;37mBLK4\x1b[0m:")
            (root / "console.log").write_bytes(raw_console.encode())
            observation = {**receipt, "operator": "Tester", "same_boot": True, "boot_id": boot,
                           "kernel_release": "6.12.0-284.el10", "root_source": "/dev/mapper/rhel-root",
                           "nvme_disk": "nvme0n1",
                           "milestones": {k: {"file": "console.log", "quote": v} for k, v in quotes.items()}}
            write_json(root / "boot.json", observation)
            result = release.boot_evidence(receipt, root, "6.12.0-284.el10", "/dev/mapper/rhel-root")
            self.assertIn("operator", result["qualification"])
            self.assertEqual(result["capture_sha256"]["console.log"], digest(raw_console.encode()))
            with self.assertRaisesRegex(ValueError, "kernel or root"):
                release.boot_evidence(receipt, root, "6.12.0-new.el10", "/dev/mapper/rhel-root")
            observation["milestones"]["rhel_grub"]["quote"] = "Ubuntu (fallback)"
            (root / "console.log").write_text((root / "console.log").read_text() + "Ubuntu (fallback)\n")
            write_json(root / "boot.json", observation)
            with self.assertRaisesRegex(ValueError, "GRUB"):
                release.boot_evidence(receipt, root, "6.12.0-284.el10", "/dev/mapper/rhel-root")
            observation["report_sha256"] = "3" * 64
            write_json(root / "boot.json", observation)
            with self.assertRaisesRegex(ValueError, "report_sha256"):
                release.boot_evidence(receipt, root, "6.12.0-284.el10", "/dev/mapper/rhel-root")


if __name__ == "__main__":
    unittest.main()
