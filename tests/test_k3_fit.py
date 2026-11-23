"""Exercise the production external-data FIT reader with images built by mkimage."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from k3_fit import compare_edk2_fits, read_edk2_fit


class FitTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def build(self, name, firmware=b'firmware-v1', other_model='Other board'):
        for key, model in [('pico', 'SpacemiT K3 Pico ITX'), ('other', other_model)]:
            subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(self.directory / key)],
                           input=f'/dts-v1/; / {{ model = "{model}"; }};', text=True, check=True)
        (self.directory / 'firmware').write_bytes(firmware)
        (self.directory / 'src.its').write_text('''/dts-v1/;
        / { description = "K3"; #address-cells = <2>;
          images {
            uefi { type = "standalone"; os = "u-boot"; arch = "riscv"; compression = "none";
                   load = <1 0x02000000>; data = /incbin/("firmware"); };
            fdt_1 { description = "k3-pico-itx"; type = "flat_dt"; compression = "none";
                    data = /incbin/("pico"); hash-1 { algo = "crc32"; }; };
            fdt_2 { type = "flat_dt"; compression = "none"; data = /incbin/("other");
                    hash-1 { algo = "crc32"; }; };
          };
          configurations { default = "conf_1"; conf_1 { description = "k3-pico-itx";
                            loadables = "uefi"; fdt = "fdt_1"; }; };
        };''')
        subprocess.run(['mkimage', '-E', '-B', '0x1000', '-f', 'src.its', name],
                       cwd=self.directory, check=True, stdout=subprocess.DEVNULL)
        return self.directory / name

    def test_only_firmware_can_change(self):
        baseline = self.build('baseline')
        candidate = self.build('candidate', b'firmware-v2')
        expected = hashlib.sha256(b'firmware-v2').hexdigest()
        self.assertEqual(compare_edk2_fits(baseline, candidate, expected)['uefi'], expected)
        changed = self.build('changed', b'firmware-v2', 'Unintended board')
        with self.assertRaisesRegex(ValueError, 'fdt_2'):
            compare_edk2_fits(baseline, changed, expected)

    def test_reject_corrupt_dtb_even_when_not_selected(self):
        candidate = self.build('candidate')
        data = bytearray(candidate.read_bytes())
        data[data.index(b'Other board')] ^= 1
        candidate.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'fdt_2'):
            read_edk2_fit(candidate)
