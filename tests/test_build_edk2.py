import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import build_edk2
import edk2_verify


class Edk2IsolationTests(unittest.TestCase):
    def test_trace_checks_effective_error_level_and_print_enable(self):
        with tempfile.TemporaryDirectory() as directory:
            libs = Path(directory)
            for lib, fields in (
                    ('BaseDebugPrintErrorLevelLib', [('PcdDebugPrintErrorLevel', '0x80000000')]),
                    ('BaseDebugLibSerialPort', [('PcdDebugPropertyMask', '0x21'),
                                                ('PcdFixedDebugPrintErrorLevel', '0xFFFFFFFF')])):
                header = libs / lib / lib / 'DEBUG/AutoGen.h'
                header.parent.mkdir(parents=True)
                header.write_text(''.join(f'#define _PCD_VALUE_{key} {value}\n' for key, value in fields))
            with self.assertRaisesRegex(ValueError, 'PcdDebugPrintErrorLevel'):
                edk2_verify.trace_masks(libs)
            level = libs/'BaseDebugPrintErrorLevelLib/BaseDebugPrintErrorLevelLib/DEBUG/AutoGen.h'
            level.write_text(level.read_text().replace('0x80000000', '0xFFFFFFFF'))
            with self.assertRaisesRegex(ValueError, 'PcdDebugPropertyMask'):
                edk2_verify.trace_masks(libs)
            prop = libs/'BaseDebugLibSerialPort/BaseDebugLibSerialPort/DEBUG/AutoGen.h'
            prop.write_text(prop.read_text().replace('0x21', '0x2f'))
            self.assertEqual(edk2_verify.trace_masks(libs)['PcdDebugPrintErrorLevel'], 0xffffffff)

    def test_isolated_build_never_publishes_malformed_final_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'result'
            def compile_bad_fit(workspace, args, sources, log):
                for relative in build_edk2.ARTIFACTS.values():
                    path = workspace / relative.format(flavor='RELEASE')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'stale packaging output')
                return {'flavor': 'RELEASE'}

            args = SimpleNamespace(destination=dest, incremental=False, recipe=build_edk2.RECIPE,
                                   platform_revision=None, expect_platform_revision=None,
                                   platform_repository=None, sdk_archive=None, keep_workspace=False,
                                   diagnostic=False, expect_bus_limit=None, serial_trace=False)
            with patch.object(build_edk2, 'prepare_sdk'), \
                 patch.object(build_edk2, 'prepare_platform', return_value={}), \
                 patch.object(build_edk2, 'compile_firmware', side_effect=compile_bad_fit):
                with self.assertRaisesRegex(ValueError, 'FIT') as failure:
                    build_edk2.build(args)
            self.assertFalse(dest.exists())
            log, = dest.parent.glob('result.*.build.log')
            self.assertIn(f'ERROR: {failure.exception}', log.read_text())

    def test_platform_input_comes_from_revision_with_ordered_verified_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            subprocess.run(['git', 'init', '--template=', '-q', source], check=True)
            content = source / 'input.txt'
            content.write_text('pinned\n')
            subprocess.run(['git', '-C', source, 'add', 'input.txt'], check=True)
            subprocess.run(['git', '-C', source, '-c', 'user.email=test@localhost',
                            '-c', 'user.name=Test', 'commit', '-qm', 'pin'], check=True)
            revision = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'],
                                               text=True).strip()
            patch = root / 'change.patch'
            patch.write_text('diff --git a/input.txt b/input.txt\n--- a/input.txt\n'
                             '+++ b/input.txt\n@@ -1 +1 @@\n-pinned\n+patched\n')
            patches = [{'file': patch.name, 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()}]
            content.write_text('ambient dirty checkout\n')
            output = root / 'private'
            with self.assertRaisesRegex(ValueError, 'working tree'):
                build_edk2.check_local_source(source, revision, implicit=True)
            with self.assertRaisesRegex(ValueError, 'HEAD'):
                build_edk2.check_local_source(source, 'f' * 40, implicit=True)
            build_edk2.check_local_source(source, revision, implicit=False)
            with (root / 'log').open('w') as log:
                identity = build_edk2.prepare_platform(
                    source, output, revision, patches, root, log)
            self.assertEqual((output / 'input.txt').read_text(), 'patched\n')
            self.assertEqual(content.read_text(), 'ambient dirty checkout\n')
            self.assertEqual(identity['revision'], revision)
            self.assertEqual(identity['commit_epoch'], int(subprocess.check_output(
                ['git', '-C', source, 'show', '-s', '--format=%ct', revision])))
            self.assertEqual(identity['patches'][0]['sha256'], patches[0]['sha256'])
            self.assertEqual(base64.b64decode(identity['patches'][0]['content_base64']),
                             patch.read_bytes())
            self.assertNotEqual(identity['tree'], subprocess.check_output(
                ['git', '-C', source, 'rev-parse', 'HEAD^{tree}'], text=True).strip())

    def test_isolated_source_recipe_pins_sdk_and_platform(self):
        recipe = json.loads(build_edk2.RECIPE.read_text())
        self.assertRegex(recipe['platforms']['revision'], r'^[0-9a-f]{40}$')
        self.assertRegex(recipe['sdk']['sha256'], r'^[0-9a-f]{64}$')

    def test_private_build_uses_pinned_clock_and_timezone(self):
        with tempfile.TemporaryDirectory() as directory:
            env = build_edk2.environment(Path(directory), True, epoch=1234567890)
        self.assertEqual(env['SOURCE_DATE_EPOCH'], '1234567890')
        self.assertEqual(env['TZ'], 'UTC')

    def test_genfw_receives_relative_efi_and_acpi_input_names(self):
        rules = build_edk2.relative_genfw_inputs("""[Dynamic-Library-File]
<Command.GCC>
"$(GENFW)" -e $(MODULE_TYPE) -o ${dst} ${src} $(GENFW_FLAGS)
<Command.XCODE>
[C-Code-File.AcpiTable]
<Command.GCC>
"$(GENFW)" -o ${dst} -c $(OUTPUT_DIR)(+)${s_dir}(+)${s_base}.dll $(GENFW_FLAGS)
<Command.CLANGPDB>
[Acpi-Table-Code-File]
<Command.GCC>
"$(GENFW)" -o ${dst} -c $(OUTPUT_DIR)(+)${s_dir}(+)${s_base}.dll $(GENFW_FLAGS)
<Command.CLANGPDB>
""")
        # Model the SDK's template expansion, then let GNU make evaluate its
        # expressions, including patsubst on paths of different lengths.
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('a', 'second-workspace'):
                ws = Path(tmp) / name
                ws.mkdir()
                commands = [line for line in rules.splitlines() if '$(GENFW)' in line]
                makefile = 'all:\n' + ''.join('\t@' + cmd + '\n' for cmd in commands)
                makefile = makefile.replace('${src}', str(ws / 'Build/DEBUG/Driver.dll'))
                makefile = makefile.replace('${dst}', 'out').replace('(+)', '/')
                makefile = makefile.replace('${s_dir}', '.').replace('${s_base}', 'Fadt')
                result = subprocess.check_output(
                    ['make', '-s', '-f', '-', 'GENFW=echo', f'WORKSPACE={ws}',
                     f'OUTPUT_DIR={ws}/Build/OUTPUT', 'MODULE_TYPE=DXE_DRIVER'],
                    input=makefile, cwd=tmp, text=True)
                inputs = [line.split()[-1] for line in result.splitlines()]
                self.assertEqual(inputs, ['Build/DEBUG/Driver.dll', 'Build/OUTPUT/./Fadt.dll',
                                          'Build/OUTPUT/./Fadt.dll'])

    def test_revision_override_is_replayable_from_embedded_recipe(self):
        original = build_edk2.RECIPE.read_bytes()
        override = 'f' * 40
        recipe_bytes = build_edk2.effective_recipe(original, override)
        self.assertEqual(json.loads(recipe_bytes)['platforms']['revision'], override)
        self.assertEqual(build_edk2.effective_recipe(original, None), original)
        self.assertEqual(build_edk2.effective_recipe(recipe_bytes, None), recipe_bytes)

    def test_revision_expectation_fails_before_sdk_access(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'out-v8'
            for expected in ('f' * 40, ''):
                with self.subTest(expected=expected):
                    result = subprocess.run(
                        ['python3', str(build_edk2.PROJECT / 'build_edk2.py'), '--destination', dest,
                         '--expect-platform-revision', expected, '--sdk-archive', dest / 'missing'],
                        capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('selected platform revision', result.stderr)
                    self.assertIn(json.loads(build_edk2.RECIPE.read_bytes())['platforms']['revision'],
                                  result.stderr)
                    self.assertFalse(dest.exists())

    def test_bad_sdk_never_publishes_or_uses_sibling_build(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            archive = parent / 'damaged.tar.xz'
            archive.write_bytes(b'incomplete local copy')
            dest = parent / 'result'
            result = subprocess.run(
                ['python3', str(build_edk2.PROJECT / 'build_edk2.py'), '--destination', dest,
                 '--recipe', build_edk2.RECIPE, '--sdk-archive', archive], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SDK archive checksum mismatch', result.stderr)
            self.assertFalse(dest.exists())
            self.assertFalse(list(parent.glob('.k3-edk2-*')))
