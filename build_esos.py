#!/usr/bin/env python3
"""Build the pinned rt24/os0_rcpu ESOS reference in a new workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import meta


def run_step(command, cwd, env, log):
    with log.open('w') as stream:
        subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def save_report(destination, report):
    temporary = destination / '.build.json.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(destination / 'build.json')


def build(lock, destination, python, compiler_dir, jobs, repositories=None):
    if jobs < 1:
        raise ValueError('jobs must be positive')
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(f'refusing existing build destination: {destination}')
    lock = Path(lock).resolve()
    data = meta.validate(lock)
    components = {c['name']: c for c in data['components']}
    # The manifest may carry other components (e.g. edk2-platforms); this
    # adapter prepares and consumes only the ESOS pair regardless of what
    # else the manifest pins.
    missing = {'esos', 'esos-lite'} - set(components)
    if missing:
        raise ValueError(f'ESOS adapter requires components: {sorted(missing)}')
    select = {'esos', 'esos-lite'}
    if components['esos-lite']['path'] != components['esos']['path'] + '/components/esos-lite':
        raise ValueError('ESOS-lite must occupy the native nested dependency path')
    configs = {}
    for config in components['esos'].get('configs', []):
        name = Path(config['file']).name
        content = meta.contained(lock.parent, config['file']).read_bytes()
        if hashlib.sha256(content).hexdigest() != config['sha256']:
            raise ValueError(f'configuration changed: {name}')
        if name in configs:
            raise ValueError(f'duplicate configuration: {name}')
        configs[name] = content
    if set(configs) != {'os0.config', 'lite.config'}:
        raise ValueError('expected os0.config and lite.config')
    # Keep a virtualenv interpreter's path: resolving its symlink loses the venv.
    python = Path(python).absolute()
    compiler_dir = Path(compiler_dir).resolve()
    gcc = compiler_dir / 'riscv64-unknown-elf-gcc'
    for tool in (python, gcc):
        if not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError(f'executable not found: {tool}')
    destination.mkdir(parents=True, exist_ok=False)
    logs = destination / 'logs'
    logs.mkdir()
    report = {'status': 'building', 'profile': 'rt24/os0_rcpu',
              'steps': [], 'artifacts': {}, 'tools': {},
              'recipe_sha256': meta.digest(Path(__file__)),
              'source_preparer_sha256': meta.digest(Path(meta.__file__)),
              'qualification': 'cross-build only; no FIT packaging or hardware test'}
    save_report(destination, report)
    try:
        # Deliberately inherit only basic host context, not caller build knobs.
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'SYSTEMROOT') if k in os.environ}
        env.update(LC_ALL='C', PYTHONHASHSEED='0', PYTHONNOUSERSITE='1')
        for name, command in (
            ('compiler', [str(gcc), '--version']),
            ('python', [str(python), '--version']),
            ('python-packages', [str(python), '-c',
             'import importlib.metadata as m; print("SCons="+m.version("SCons")); print("kconfiglib="+m.version("kconfiglib"))'])):
            report['tools'][name] = subprocess.check_output(command, text=True, env=env).strip()
        report['tools']['compiler_sha256'] = meta.digest(gcc)
        report['tools']['compiler_directory'] = str(compiler_dir)
        report['tools']['python_path'] = str(python)
        sources = destination / 'sources'
        meta.prepare(lock, sources, repositories=repositories, select=select)
        prepared = json.loads((sources / 'prepared.json').read_text())
        # Refuse a manifest changed between configuration snapshot and cloning.
        if prepared['manifest'] != data:
            raise ValueError('manifest changed during build setup')
        report['sources'] = prepared
        source = meta.contained(sources, components['esos']['path'])
        lite = source / 'components/esos-lite/rt-thread'
        epoch = subprocess.check_output(['git', 'show', '-s', '--format=%ct', components['esos']['revision']], cwd=source, text=True).strip()
        env.update(TARGET_CHIP='rt24', TARGET_BOARD='os0_rcpu',
                   TARGET_ENTRY_POINT='0x100200000', RTT_EXEC_PATH=str(compiler_dir),
                   SOURCE_DATE_EPOCH=epoch)
        (destination / 'configs').mkdir()
        for name, content in configs.items():
            (destination / 'configs' / name).write_bytes(content)
        version = 'os0_rcpu:acpi-demo-' + prepared['manifest_sha256'][:20]
        version_source = 'struct version_id __versionid spacemit_verid = { .verid=' + json.dumps(version) + ' };\n'
        (source / 'bsp/spacemit/platform/version_id_gen.cc').write_text(version_source)
        report['generated_version'] = version
        report['generated_version_sha256'] = hashlib.sha256(version_source.encode()).hexdigest()
        artifacts = destination / 'artifacts'
        artifacts.mkdir()
        for name, tree, config, output in (
            ('lite', lite, 'lite.config', 'esos_lite.bin'),
            ('main', source, 'os0.config', 'rtthread.bin')):
            bsp = tree / 'bsp/spacemit'
            (bsp / '.config').write_bytes(configs[config])
            build_env = dict(env, PYTHONPATH=str(tree / 'tools'))
            if name == 'lite':
                build_env.update(TARGET_CHIP_LITE='rt24', TARGET_ENTRY_POINT_LITE='0x0')
            for stage, command in (
                ('header', [str(python), '-c', 'from menuconfig import mk_rtconfig; mk_rtconfig(".config")']),
                ('config', [str(python), '-m', 'SCons', '--useconfig=.config']),
                ('build', [str(python), '-m', 'SCons', f'-j{jobs}'])):
                log = logs / f'{name}-{stage}.log'
                step = {'stage': f'{name}-{stage}', 'command': command,
                        'cwd': str(bsp), 'environment': build_env, 'log': str(log)}
                report['steps'].append(step)
                save_report(destination, report)
                print(f'{name}-{stage}: {log}', flush=True)
                run_step(command, bsp, build_env, log)
                step['status'] = 'passed'
            binary = bsp / output
            if not binary.is_file() or binary.stat().st_size == 0:
                raise ValueError(f'missing or empty output: {binary}')
            shutil.copyfile(binary, artifacts / output)
            report['artifacts'][output] = {'size': binary.stat().st_size, 'sha256': meta.digest(binary)}
            if name == 'lite':
                (source / 'bsp/spacemit/binary').mkdir(exist_ok=True)
                shutil.copyfile(binary, source / 'bsp/spacemit/binary/esos_lite.bin')
        report['status'] = 'built'
    except BaseException as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        save_report(destination, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('sources.lock.json'))
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True, help='Python environment with SCons and kconfiglib')
    parser.add_argument('--compiler-dir', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--repository', action='append', default=[], metavar='NAME=LOCAL_PATH', help='optional local Git cache; locked commit still required')
    args = parser.parse_args()
    try:
        repositories = {}
        for value in args.repository:
            name, path = value.split('=', 1)
            if name in repositories:
                raise ValueError(f'duplicate repository override: {name}')
            repositories[name] = str(Path(path).resolve())
        build(args.manifest, args.destination, args.python, args.compiler_dir, args.jobs, repositories)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
