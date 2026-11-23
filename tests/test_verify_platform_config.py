"""Regression cases for the Platform Manager link in the packaged HII forms."""
import struct
import unittest
from uuid import UUID

import verify_platform_config as checker


def k3_page(with_link=True, target=0x1012, target_form=0x1001, duplicate=False,
            callback_key=0x7f01, callback_flag=0x04, suppressed=True):
    def op(code, data=b'', scope=False):
        return bytes([code, (2 + len(data)) | (0x80 if scope else 0)]) + data

    def guid(value):
        return UUID(value).bytes_le

    identity = guid('cc9c5ba8-aa74-444e-9ea5-d83898308d71')
    manager = guid('2faa29ba-0cf4-4dcf-8669-4a44532a694f')
    bmm = guid('642237c7-35d4-472d-8365-12e0ccf27a22')
    formset = op(0x0e, identity + struct.pack('<HHB', 1, 2, 1) + manager, True)
    form = op(1, struct.pack('<HH', 1, 1), True)
    ref = op(0x0f, bytes(11) + struct.pack('<HH', target_form, target) + bmm)
    action = op(0x0c, struct.pack('<HHHHHBH', 3, 4, callback_key, 0, 0xffff,
                                  callback_flag, 0), True) + op(0x29)
    if suppressed:
        action = op(0x0a, scope=True) + op(0x46) + action + op(0x29)
    body = formset + form + ref * (int(with_link) + int(duplicate)) + action + op(0x29) * 2
    return struct.pack('<I', (2 << 24) | (len(body) + 4)) + body


class PlatformConfigLinkTests(unittest.TestCase):
    def test_mode_specific_native_timeout_link(self):
        checker.check_page(k3_page(), 'acpi')
        checker.check_page(k3_page(False), 'dt')
        for blob, mode in [(k3_page(), 'dt'), (k3_page(False), 'acpi'),
                           (k3_page(target=0x1011), 'acpi'),
                           (k3_page(target_form=0x1012), 'acpi'),
                           (k3_page(duplicate=True), 'acpi')]:
            with self.subTest(mode=mode, blob=blob), self.assertRaises(ValueError):
                checker.check_page(blob, mode)

    def test_malformed_or_duplicate_form_package_is_rejected(self):
        page = k3_page()
        for blob in [page[:-2], page + page]:
            with self.subTest(blob=blob), self.assertRaises(ValueError):
                checker.check_page(blob, 'acpi')

    def test_hidden_form_open_action_must_use_owners_callback_key(self):
        for changes in [dict(callback_key=0x7000), dict(callback_flag=0), dict(suppressed=False)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                checker.check_page(k3_page(**changes), 'acpi')

    def test_only_global_uint16_timeout_backs_the_native_editor(self):
        # DEFAULT DXE PCD database with a single HII variable record.
        db = bytearray(160)
        db[:16] = UUID('3c7d193c-682c-4c14-a68f-552dea4f437e').bytes_le
        struct.pack_into('<II', db, 16, 7, len(db))
        struct.pack_into('<4I', db, 40, 80, 0, 112, 128)
        struct.pack_into('<H', db, 68, 1)
        struct.pack_into('<I', db, 80, 0x82000058)
        struct.pack_into('<IIHH', db, 88, 0, 144, 0, 0)
        db[112:128] = UUID('8be4df61-93ca-11d2-aa0d-00e098032b8c').bytes_le
        db[128:144] = 'Timeout\0'.encode('utf-16-le')
        struct.pack_into('<H', db, 144, 3)
        self.assertEqual(checker.check_timeout_pcd(db), 3)
        for offset, value in [(83, 0x02), (83, 0x81), (98, 1), (112, 0), (128, 0), (144, 0)]:
            broken = db.copy()
            broken[offset] = value
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                checker.check_timeout_pcd(broken)
