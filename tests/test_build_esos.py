import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import build_esos

class BuildTests(unittest.TestCase):
    def test_invalid_jobs(self):
        with self.assertRaises(ValueError):
            build_esos.build(Path('missing'), Path('unused'), Path('python'), Path('cc'), 0)

    def test_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                build_esos.build(Path('missing'), Path(directory), Path('python'), Path('cc'), 1)

    def exercise(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = Path(__file__).resolve().parents[1] / 'sources.lock.json'
            tools = root / 'tools'
            tools.mkdir()
            for name in ('python', 'riscv64-unknown-elf-gcc'):
                (tools / name).write_text('fixture')
                (tools / name).chmod(0o755)
            steps = []
            def prepare(lock, destination, repositories=None, select=None):
                for project in ('esos', 'esos/components/esos-lite/rt-thread'):
                    (destination / project / 'bsp/spacemit/platform').mkdir(parents=True)
                (destination / 'prepared.json').write_text(json.dumps({'manifest': json.loads(lock.read_text()), 'manifest_sha256': build_esos.meta.digest(lock)}))
            def run_step(command, cwd, env, log):
                steps.append((log.name, env.copy()))
                log.write_text('fixture output')
                if fail and log.name == 'lite-build.log':
                    raise subprocess.CalledProcessError(1, command)
                if log.name.endswith('-build.log'):
                    name = 'esos_lite.bin' if log.name.startswith('lite') else 'rtthread.bin'
                    if name == 'rtthread.bin':
                        self.assertEqual((cwd / 'binary/esos_lite.bin').read_bytes(), b'firmware')
                    (cwd / name).write_bytes(b'firmware')
            with patch.object(build_esos.meta, 'prepare', prepare), patch.object(build_esos, 'run_step', run_step), patch.object(build_esos.subprocess, 'check_output', return_value='123\n'):
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError):
                        build_esos.build(lock, root / 'out', tools / 'python', tools, 2)
                else:
                    build_esos.build(lock, root / 'out', tools / 'python', tools, 2)
            report = json.loads((root / 'out/build.json').read_text())
            self.assertEqual(report['status'], 'failed' if fail else 'built')
            if fail:
                self.assertFalse((root / 'out/artifacts/rtthread.bin').exists())
            else:
                stages = [s for s, _ in steps if s in ('lite-build.log', 'main-build.log')]
                self.assertEqual(stages, ['lite-build.log', 'main-build.log'])
                self.assertEqual(report['artifacts']['rtthread.bin']['size'], 8)
                environments = dict(steps)
                self.assertIn('TARGET_CHIP_LITE', environments['lite-build.log'])
                self.assertNotIn('TARGET_CHIP_LITE', environments['main-build.log'])

    def test_build_order_and_evidence(self):
        self.exercise()

    def test_build_failure_record(self):
        self.exercise(fail=True)
