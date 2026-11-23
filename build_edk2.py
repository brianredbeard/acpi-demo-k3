#!/usr/bin/env python3
"""Build K3 MUSE-Pico ACPI firmware from isolated, pinned inputs."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import meta
from edk2_verify import verify_fit, verify_serial_trace, verify_token_abi
from k3_fit import read_edk2_fit

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parent
RECIPE = PROJECT / 'edk2-build.lock.json'
DSC = 'Platform/Spacemit/K3/MUSE-Pico/MUSE-Pico.dsc'
ARTIFACTS = {
    'MUSE-PICO.fd': 'Build/MUSE-Pico/{flavor}_GCC5/FV/MUSE-PICO.fd',
    'MUSE-Pico.itb': 'fitimage/MUSE-Pico/MUSE-Pico.itb',
}
CONFIG_NAMES = ('target', 'build_rule', 'tools_def')
CC_PREFIX = '/usr/bin/riscv64-linux-gnu-'


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(command, log, *, cwd=None, env=None, data=None):
    log.write('$ ' + shlex.join(map(str, command)) + '\n')
    log.flush()
    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                   cwd=cwd, env=env, input=data)


def effective_recipe(original, revision):
    """Return the exact recipe needed to repeat this invocation."""
    if revision is None:
        return original
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('platform revision must be a full 40-character Git commit')
    recipe = json.loads(original)
    if recipe['platforms']['revision'] == revision:
        return original
    recipe['platforms']['revision'] = revision
    return (json.dumps(recipe, indent=2) + '\n').encode()


def check_local_source(source, revision, implicit):
    git = ['git', '--no-optional-locks', '-C', source]
    current = subprocess.run([*git, 'rev-parse', '--is-bare-repository', '--verify', 'HEAD'],
                             text=True, capture_output=True)
    if current.returncode:
        if implicit:
            raise ValueError(f'cannot identify the implicit platform checkout {source}: {current.stderr.strip()}')
        return  # An explicit Git bundle or mirror can supply a pin without a checked-out HEAD.
    bare, head = current.stdout.splitlines()
    if head != revision:
        detail = f'object source {source} has HEAD {head}, selected commit is {revision}'
    elif implicit and bare == 'false' and subprocess.check_output(
            [*git, 'status', '--porcelain', '--untracked-files=normal']):
        detail = f'platform working tree {source} has edits outside selected commit {revision}'
    else:
        return
    if implicit:
        raise ValueError(f'{detail}. Select the intended committed change with --platform-revision, '
                         'or pass --recipe edk2-build.lock.json to reproduce the locked inputs.')
    print(f'{detail}. Building the explicitly selected inputs.', flush=True)


def prepare_platform(source, target, revision, patches, inputs_root, log):
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('platform revision must be a full 40-character Git commit')
    # An independent object store and checkout. No source worktree files,
    # ignored files, hooks or in-progress developer patch state are copied.
    git_env = {'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null'}
    git = ['git', '-c', 'core.autocrlf=false', '-c', 'core.hooksPath=/dev/null']
    run([*git, 'init', '-q', target], log, env=git_env)
    run([*git, 'fetch', '-q', '--no-tags', '--depth=1', '--', source, revision],
        log, cwd=target, env=git_env)
    run([*git, 'checkout', '-q', '--detach', revision], log, cwd=target, env=git_env)
    actual = subprocess.check_output([*git, 'rev-parse', 'HEAD'], cwd=target,
                                     env=git_env, text=True).strip()
    if actual != revision:
        raise ValueError(f'platform pin must identify the checked-out commit: {actual}')
    applied = []
    for patch in patches:
        content = meta.contained(inputs_root, patch['file']).read_bytes()
        if hashlib.sha256(content).hexdigest() != patch['sha256']:
            raise ValueError(f"platform patch hash mismatch: {patch['file']}")
        run([*git, 'apply', '--index', '-'], log, cwd=target, env=git_env, data=content)
        applied.append({**patch, 'content_base64': base64.b64encode(content).decode('ascii')})
    tree = subprocess.check_output([*git, 'write-tree'], cwd=target,
                                   env=git_env, text=True).strip()
    epoch = int(subprocess.check_output([*git, 'show', '-s', '--format=%ct', 'HEAD'],
                                        cwd=target, env=git_env))
    return {'revision': revision, 'tree': tree, 'patches': applied, 'commit_epoch': epoch}


def prepare_sdk(recipe, archive, workspace, log):
    # Verify a private snapshot, then unpack that same immutable input.
    snapshot = workspace / 'sdk-source.tar.xz'
    if archive:
        shutil.copyfile(archive, snapshot)
    else:
        run(['/usr/bin/curl', '-fsSL', recipe['url'], '-o', snapshot], log)
    if sha256(snapshot) != recipe['sha256']:
        raise ValueError(f"SDK archive checksum mismatch: expected {recipe['sha256']}")
    run(['tar', '-xJf', snapshot, '--no-same-owner', '--strip-components=1',
         recipe['subdirectory']], log, cwd=workspace, env={'PATH': '/usr/bin:/bin'})
    conf = workspace / 'Conf'
    conf.mkdir()
    for name in CONFIG_NAMES:
        template = workspace / 'edk2/BaseTools/Conf' / (name + '.template')
        shutil.copyfile(template, conf / (name + '.txt'))
    rules = conf / 'build_rule.txt'
    rules.write_text(relative_genfw_inputs(rules.read_text()))

    # __FILE__ in assertions can otherwise expose the checkout in DEBUG images.
    definitions = conf / 'tools_def.txt'
    updated, count = re.subn(r'^(\*_GCC5_RISCV64_CC_FLAGS\s*=[^\n]+)$',
                             r'\1 -ffile-prefix-map=ENV(WORKSPACE)/=', definitions.read_text(),
                             flags=re.MULTILINE)
    if count != 1:
        raise ValueError('unrecognized SDK RISCV64 compiler flags')
    definitions.write_text(updated)


def relative_genfw_inputs(rules):
    # GenFw includes its ELF input name in both PE debug records and the
    # trailing bytes of C-built ACPI table sections. Keep the module path.
    acpi_dll = '$(OUTPUT_DIR)(+)${s_dir}(+)${s_base}.dll'
    for section, options, source in (
            ('Dynamic-Library-File', '-e $(MODULE_TYPE) -o ${dst}', '${src}'),
            ('C-Code-File.AcpiTable', '-o ${dst} -c', acpi_dll),
            ('Acpi-Table-Code-File', '-o ${dst} -c', acpi_dll)):
        start = rules.index('<Command.GCC>', rules.index('[' + section + ']'))
        end = rules.index('<Command.', start + 1)
        gcc = rules[start:end]
        cmd = '"$(GENFW)" ' + options
        original = f'{cmd} {source} $(GENFW_FLAGS)'
        if gcc.count(original) != 1:
            raise ValueError(f'unrecognized SDK GCC rule for {section}')
        relative = f'cd "$(WORKSPACE)" && {cmd} "$(patsubst $(WORKSPACE)/%,%,{source})" $(GENFW_FLAGS)'
        rules = rules[:start] + gcc.replace(original, relative) + rules[end:]
    return rules


def environment(workspace, private, epoch=None):
    sdk = workspace / 'edk2'
    tools = sdk / 'BaseTools'
    home = workspace / 'home' if private else Path.home()
    if private:
        home.mkdir()
    env = {
        'PATH': f'{tools}/BinWrappers/PosixLike:{tools}/Source/C/bin:/usr/bin:/bin',
        'WORKSPACE': str(workspace),
        'PACKAGES_PATH': f'{sdk}:{workspace}/edk2-platforms',
        'EDK_TOOLS_PATH': str(tools),
        'PYTHON_COMMAND': 'python3',
        'PYTHONPATH': str(tools / 'Source/Python'),
        'GCC5_RISCV64_PREFIX': CC_PREFIX,
        'HOME': str(home),
        'LC_ALL': 'C',
    }
    if epoch is not None:
        env.update(SOURCE_DATE_EPOCH=str(epoch), TZ='UTC')
    return env


def tools_used():
    versions = {}
    for name, flags in {
        'riscv64-linux-gnu-gcc': ['--version'], 'riscv64-linux-gnu-ld': ['--version'],
        'riscv64-linux-gnu-as': ['--version'], 'riscv64-linux-gnu-objcopy': ['--version'],
        'riscv64-linux-gnu-gcc-ar': ['--version'], 'riscv64-linux-gnu-ar': ['--version'], 'gcc': ['--version'], 'g++': ['--version'],
        'python3': ['--version'], 'make': ['--version'], 'iasl': ['-v'],
        'dtc': ['-v'], 'mkimage': ['-V'],
    }.items():
        path = Path('/usr/bin') / name
        version = subprocess.check_output([path, *flags], text=True).strip()
        versions[name] = {'path': str(path), 'sha256': sha256(path),
                          'version': version if name == 'iasl' else version.splitlines()[0]}
    return versions


def compile_firmware(workspace, args, sources, log):
    epoch = None if args.incremental else sources['platforms']['commit_epoch']
    env = environment(workspace, not args.incremental, epoch)
    tools = Path(env['EDK_TOOLS_PATH'])
    basetools_command = ['make', '-C', str(tools / 'Source/C'), '-j', str(args.jobs),
                         'BUILD_OPTFLAGS=-Wno-error=unused-but-set-variable']
    if not args.incremental:
        run(basetools_command, log, cwd=workspace, env=env)
    flavor = 'DEBUG' if args.debug or args.serial_trace else 'RELEASE'
    defines = ['ACPI_ENABLE=TRUE', *args.extra_define]
    if args.serial_trace:
        defines.append('DEBUG_ON_SERIAL_PORT=TRUE')
    command = ['build', '-a', 'RISCV64', '-p', DSC, '-t', 'GCC5', '-b', flavor,
               '-n', str(args.jobs)]
    for define in defines:
        command.extend(['-D', define])
    if args.serial_trace:
        command.extend(['--pcd', 'gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel=0xFFFFFFFF'])
    conf = workspace / 'Conf'
    command.append('--conf=' + str(conf))
    run(command, log, cwd=workspace, env=env)
    platform = workspace / 'edk2-platforms'
    dsc = (platform / DSC).read_text()
    sku = re.search(r'^\s*SKUID_IDENTIFIER\s*=\s*(\w+)', dsc, re.MULTILINE)[1]
    toolchain = tools_used()
    manifest = {
        'build_mode': 'incremental' if args.incremental else 'isolated',
        'sources': sources,
        'command': command, 'env': env, 'flavor': flavor, 'defines': defines,
        'arch': 'RISCV64', 'toolchain_tag': 'GCC5', 'sku': sku,
        'compiler': toolchain['riscv64-linux-gnu-gcc']['version'], 'toolchain': toolchain,
        'conf_sha256': {name + '.txt': sha256(conf / (name + '.txt')) for name in CONFIG_NAMES},
        'basetools': {
            'command': None if args.incremental else basetools_command,
            'binaries_sha256': {p.name: sha256(p) for p in sorted((tools / 'Source/C/bin').iterdir())
                                if p.is_file()},
        },
    }
    if not args.incremental:
        manifest['pcd_token_abi'] = verify_token_abi(workspace / 'Build/MUSE-Pico' /
                                                    (flavor + '_GCC5'))
    return manifest


def build(args):
    destination = args.destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'destination exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Separate log per invocation, even when two jobs request the same output.
    with tempfile.NamedTemporaryFile(mode='w', prefix=destination.name + '.',
                                     suffix='.build.log', dir=destination.parent, delete=False) as log:
        print(f'Build log: {log.name}', flush=True)
        staging = Path(tempfile.mkdtemp(prefix='.k3-edk2-', dir=destination.parent))
        try:
            if args.incremental:
                workspace = ROOT
                sources = {'working_directory': str(ROOT),
                           'platforms_head': subprocess.check_output(
                               ['git', '-C', ROOT / 'edk2-platforms', 'rev-parse', 'HEAD'],
                               text=True).strip()}
            else:
                workspace = staging / 'workspace'
                workspace.mkdir()
                free = shutil.disk_usage(workspace).free
                print(f'Private workspace: {workspace} ({free // (1 << 30)} GiB free)', flush=True)
                recipe_path = args.recipe or RECIPE
                original = recipe_path.read_bytes()
                lock_bytes = effective_recipe(original, args.platform_revision)
                recipe = json.loads(lock_bytes)
                pin = recipe['platforms']
                revision = pin['revision']
                if args.expect_platform_revision is not None and revision != args.expect_platform_revision:
                    raise ValueError(f"selected platform revision {revision}, "
                                     f"expected {args.expect_platform_revision}")
                print(f"Selected platform commit {revision} with {len(pin['patches'])} patch(es) "
                      f"from {recipe_path}", flush=True)
                source = args.platform_repository
                if source is None:
                    local = ROOT / 'edk2-platforms'
                    source = local if local.is_dir() else pin['repository']
                if isinstance(source, Path):
                    implicit = all(value is None for value in (args.recipe, args.platform_repository,
                                   args.platform_revision, args.expect_platform_revision))
                    check_local_source(source, revision, implicit)
                sdk = recipe['sdk']
                archive = args.sdk_archive
                cached = meta.contained(PROJECT / 'build', sdk['package'])
                if not archive and cached.is_file():
                    archive = cached
                prepare_sdk(sdk, archive, workspace, log)
                platform = prepare_platform(source, workspace / 'edk2-platforms',
                                            revision, pin['patches'], recipe_path.resolve().parent, log)
                platform['repository'] = pin['repository']
                platform['object_source'] = str(source)
                sources = {'sdk': sdk, 'platforms': platform,
                           'recipe_sha256': hashlib.sha256(lock_bytes).hexdigest(),
                           'recipe_base64': base64.b64encode(lock_bytes).decode('ascii')}
                if original != lock_bytes:
                    sources['original_recipe_sha256'] = hashlib.sha256(original).hexdigest()
            manifest = compile_firmware(workspace, args, sources, log)
            output = staging / 'output'
            output.mkdir()
            for name, relative in ARTIFACTS.items():
                src = workspace / relative.format(flavor=manifest['flavor'])
                dest = output / name
                shutil.copyfile(src, dest)
                manifest[name] = {'sha256': sha256(dest), 'bytes': dest.stat().st_size}
            fit = output / 'MUSE-Pico.itb'
            print(f'Checking final FIT {fit.name} before publishing to {destination}', file=log, flush=True)
            if args.incremental and args.expect_bus_limit is None:
                _, image_hashes, _ = read_edk2_fit(fit)
                manifest['pcie_profile_check'] = 'deferred'
            else:
                try:
                    report = verify_fit(fit, diagnostic=args.diagnostic or args.incremental,
                                        expected_bus_limit=args.expect_bus_limit)
                except ValueError as exc:
                    if not args.diagnostic or args.expect_bus_limit is not None:
                        raise
                    # Older experiments can have a different table layout.
                    _, image_hashes, _ = read_edk2_fit(fit)
                    manifest['pcie_profile_check'] = 'unverified'
                    manifest['pcie_diagnostic_error'] = str(exc)
                else:
                    image_hashes = report['images']
                    manifest['pcie_profile_check'] = 'failed' if report['profile_violations'] else 'passed'
                    manifest['pcie_report'] = report
            if image_hashes['uefi'] != manifest['MUSE-PICO.fd']['sha256']:
                raise ValueError('UEFI payload in final FIT differs from the compiled FD')
            if args.serial_trace:
                manifest['serial_trace'] = verify_serial_trace(
                    (output / 'MUSE-PICO.fd').read_bytes(), workspace / 'Build/MUSE-Pico/DEBUG_GCC5')
            (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            output.rename(destination)
            verdict = f"Artifacts: {destination} (PCIe profile check {manifest['pcie_profile_check']})"
            print(verdict, file=log, flush=True)
        except Exception as exc:
            print(f'ERROR: {exc}', file=log, flush=True)
            raise
        finally:
            if args.keep_workspace:
                print(f'Retained workspace: {staging}', flush=True)
            else:
                shutil.rmtree(staging)
    print(verdict)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--destination', required=True, type=Path, help='fresh output directory')
    ap.add_argument('--incremental', action='store_true',
                    help='developer build using the mutable sibling workspace')
    ap.add_argument('--diagnostic', action='store_true',
                    help='retain an isolated experiment without enforcing the release PCIe profile')
    ap.add_argument('--recipe', type=Path,
                    help='source lock, including ordered patches relative to the lock')
    ap.add_argument('--sdk-archive', type=Path, help='local copy of the pinned vendor source archive')
    ap.add_argument('--platform-repository', type=Path, help='local Git object source')
    ap.add_argument('--platform-revision', help='override the platform pin with a full reviewed commit ID')
    ap.add_argument('--expect-platform-revision', help='require the selected full commit ID before building')
    ap.add_argument('--expect-bus-limit', type=lambda value: int(value, 0),
                    help='require this secondary bus limit in the packaged PCD and AML on segments 2 and 4')
    ap.add_argument('--keep-workspace', action='store_true', help='retain private intermediate files')
    ap.add_argument('--debug', action='store_true')
    ap.add_argument('--serial-trace', action='store_true',
                    help='build DEBUG with full serial logging and verify packaged PCI driver instrumentation')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--extra-define', action='append', default=[], metavar='KEY=VALUE')
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error('--jobs must be positive')
    if args.incremental and (args.recipe is not None or args.sdk_archive or args.platform_repository or
                             args.platform_revision is not None or args.expect_platform_revision is not None or
                             args.keep_workspace or args.serial_trace):
        ap.error('isolated source and workspace options require the default isolated mode')
    try:
        if args.platform_repository:
            args.platform_repository = args.platform_repository.resolve(strict=True)
        build(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
