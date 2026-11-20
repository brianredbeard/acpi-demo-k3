#!/usr/bin/env python3
"""Pinned source preparation for acpi-demo-k3 (Python >= 3.9)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def contained(root, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or '..' in path.parts:
        raise ValueError(f'unsafe relative path: {relative!r}')
    target = (root / path).resolve()
    if target == root.resolve() or root.resolve() not in target.parents:
        raise ValueError(f'path escapes root: {relative!r}')
    return target


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(lock, data=None):
    lock = Path(lock).resolve()
    if data is None:
        data = json.loads(lock.read_text())
    if data.get('schema') != 1 or not data.get('components'):
        raise ValueError('expected schema 1 and nonempty components')
    names, paths = set(), set()
    for component in data['components']:
        name = component['name']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or name in names:
            raise ValueError(f'invalid or duplicate component: {name}')
        names.add(name)
        for directory in component.get('sparse_paths', []):
            contained(lock.parent, directory)
            if directory.startswith('-'):
                raise ValueError('invalid sparse directory')
        if not re.fullmatch(r'[0-9a-f]{40}', component['revision']):
            raise ValueError(f'{name}: revision must be a full commit ID')
        repository = component['repository']
        if not isinstance(repository, str) or not repository or repository.startswith('-'):
            raise ValueError(f'{name}: invalid repository')
        path = contained(lock.parent, component['path'])
        if path in paths:
            raise ValueError(f'duplicate destination: {path}')
        # Parents must precede children; preparation never overwrites a child.
        if any(path in previous.parents for previous in paths):
            raise ValueError('parent component must precede nested components')
        paths.add(path)
        for item in component.get('patches', []) + component.get('configs', []):
            source = contained(lock.parent, item['file'])
            if digest(source) != item['sha256']:
                raise ValueError(f'hash mismatch: {item["file"]}')
    return data


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def prepare(lock, destination, repositories=None, select=None):
    lock = Path(lock).resolve()
    manifest_bytes = lock.read_bytes()
    data = validate(lock, json.loads(manifest_bytes))
    if select is None:
        select = {c['name'] for c in data['components']}
    unknown = select - {c['name'] for c in data['components']}
    if unknown:
        raise ValueError(f'unknown component selection: {sorted(unknown)}')
    # A selected component must not depend on an unselected parent:
    # the ESOS pair nests, so selecting esos-lite alone is invalid.
    paths = {c['path'] for c in data['components'] if c['name'] in select}
    for component in data['components']:
        if component['name'] not in select and any(
                Path(component['path']) in Path(p).parents for p in paths):
            raise ValueError(f"selection requires parent component: {component['name']}")
    repositories = repositories or {}
    if set(repositories) - select:
        raise ValueError('unknown repository override')
    for repository in repositories.values():
        if not Path(repository).is_absolute() or not Path(repository).is_dir():
            raise ValueError('repository overrides must be absolute local directories')
    # Snapshot validated inputs before network work: later edits cannot change
    # the patch bytes applied or the identity recorded at completion.
    with tempfile.TemporaryDirectory(prefix='k3-inputs-') as temporary:
        inputs = {}
        for component in data['components']:
            if component['name'] not in select:
                continue
            for item in component.get('patches', []) + component.get('configs', []):
                content = contained(lock.parent, item['file']).read_bytes()
                if hashlib.sha256(content).hexdigest() != item['sha256']:
                    raise ValueError(f'input changed: {item["file"]}')
                snapshot = Path(temporary) / item['sha256']
                snapshot.write_bytes(content)
                inputs[item['file']] = snapshot
        destination = Path(destination).absolute()
        destination.mkdir(parents=True, exist_ok=False)
        for component in data['components']:
            if component['name'] not in select:
                continue
            target = contained(destination, component['path'])
            if target.exists():
                raise FileExistsError(f'refusing existing source destination: {target}')
            target.parent.mkdir(parents=True, exist_ok=True)
            run('git', 'clone', '--no-checkout', '--', repositories.get(component['name'], component['repository']), str(target))
            if component.get('sparse_paths'):
                run('git', 'sparse-checkout', 'set', '--cone', '--', *component['sparse_paths'], cwd=target)
            run('git', 'checkout', '--detach', component['revision'], cwd=target)
            actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=target, text=True).strip()
            if actual != component['revision']:
                raise ValueError(f'{component["name"]}: checkout identity mismatch')
            for patch in component.get('patches', []):
                source = str(inputs[patch['file']])
                run('git', 'apply', '--check', source, cwd=target)
                run('git', 'apply', source, cwd=target)
        # Completion marker only: not a claim of compilation or qualification.
        marker = destination / '.prepared.json.tmp'
        marker.write_text(json.dumps({
            'status': 'sources-prepared',
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'manifest': data,
            'repository_overrides': repositories,
        }, indent=2) + '\n')
        marker.replace(destination / 'prepared.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path,
                        default=Path(__file__).with_name('sources.lock.json'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate')
    commands.add_parser('plan')
    prep = commands.add_parser('prepare')
    prep.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.manifest, args.destination)
        else:
            data = validate(args.manifest)
            if args.command == 'plan':
                for c in data['components']:
                    print(f'{c["name"]}: {c["repository"]}@{c["revision"]} -> {c["path"]} ({len(c.get("patches", []))} patches)')
            else:
                print('Manifest and local input hashes valid.')
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
