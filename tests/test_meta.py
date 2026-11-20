import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import meta

class MetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'upstream'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.repo / 'input').write_text('before\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        rev = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'input').write_text('after\n')
        patch = self.git('diff')
        (self.root / 'fix.patch').write_text(patch)
        self.manifest = {'schema': 1, 'project': 'test', 'components': [
            {'name': 'main', 'repository': str(self.repo), 'revision': rev,
             'path': 'main', 'patches': [{'file': 'fix.patch',
                 'sha256': hashlib.sha256(patch.encode()).hexdigest()}]}]}
        self.lock = self.root / 'sources.lock.json'
        self.save()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True)

    def save(self):
        self.lock.write_text(json.dumps(self.manifest))

    def test_prepare_exact_commit_and_patch(self):
        out = self.root / 'prepared'
        meta.prepare(self.lock, out)
        self.assertEqual((out / 'main/input').read_text(), 'after\n')
        self.assertTrue((out / 'prepared.json').exists())
        with self.assertRaises(FileExistsError):
            meta.prepare(self.lock, out)

    def test_inputs_cannot_change_during_clone(self):
        original = meta.run
        expected_hash = meta.digest(self.lock)
        def changing_run(*args, **kwargs):
            if args[:2] == ('git', 'clone'):
                (self.root / 'fix.patch').write_text('changed during clone')
                self.lock.write_text('{}')
            return original(*args, **kwargs)
        out = self.root / 'snapshot'
        with patch.object(meta, 'run', changing_run):
            meta.prepare(self.lock, out)
        self.assertEqual((out / 'main/input').read_text(), 'after\n')
        self.assertEqual(json.loads((out / 'prepared.json').read_text())['manifest_sha256'], expected_hash)

    def test_nested_component(self):
        parent = self.manifest['components'][0]
        self.manifest['components'].append({
            'name': 'lite', 'path': 'main/components/lite',
            'repository': str(self.repo), 'revision': parent['revision']})
        self.save()
        out = self.root / 'nested'
        meta.prepare(self.lock, out)
        self.assertEqual((out / 'main/components/lite/input').read_text(), 'before\n')

    def test_symlink_input_escape(self):
        (self.root / 'escape').symlink_to(self.root.parent, target_is_directory=True)
        self.manifest['components'][0]['patches'][0]['file'] = 'escape/file.patch'
        self.save()
        with self.assertRaises(ValueError):
            meta.validate(self.lock)

    def test_local_cache_override_keeps_pin(self):
        self.manifest['components'][0]['repository'] = 'https://example.invalid/upstream'
        self.save()
        out = self.root / 'cached'
        meta.prepare(self.lock, out, repositories={'main': str(self.repo)})
        recorded = json.loads((out / 'prepared.json').read_text())
        self.assertEqual(recorded['manifest'], self.manifest)
        self.assertEqual(recorded['repository_overrides'], {'main': str(self.repo)})
        self.assertEqual((out / 'main/input').read_text(), 'after\n')

    def test_unknown_cache_rejected_before_creation(self):
        out = self.root / 'bad-cache'
        with self.assertRaises(ValueError):
            meta.prepare(self.lock, out, repositories={'typo': str(self.repo)})
        self.assertFalse(out.exists())

    def test_sparse_path_escape_rejected(self):
        self.manifest['components'][0]['sparse_paths'] = ['../escape']
        self.save()
        with self.assertRaises(ValueError):
            meta.validate(self.lock)

    def test_reject_moving_revision(self):
        self.manifest['components'][0]['revision'] = 'main'
        self.save()
        with self.assertRaises(ValueError):
            meta.validate(self.lock)

    def test_reject_hash_mismatch(self):
        (self.root / 'fix.patch').write_text('tampered')
        with self.assertRaises(ValueError):
            meta.validate(self.lock)

    def test_reject_path_escape(self):
        self.manifest['components'][0]['path'] = '../escape'
        self.save()
        with self.assertRaises(ValueError):
            meta.validate(self.lock)

    def test_failed_patch_has_no_completion_record(self):
        patch = self.root / 'fix.patch'
        patch.write_text('not a patch\n')
        self.manifest['components'][0]['patches'][0]['sha256'] = hashlib.sha256(patch.read_bytes()).hexdigest()
        self.save()
        out = self.root / 'failed'
        with self.assertRaises(subprocess.CalledProcessError):
            meta.prepare(self.lock, out)
        self.assertFalse((out / 'prepared.json').exists())

if __name__ == '__main__':
    unittest.main()
