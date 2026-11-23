#!/usr/bin/env python3
"""Build an inspected K3 EDK2 candidate and bind its flash and boot evidence."""

import argparse
import base64
import codecs
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from edk2_verify import BRIDGES_TOKEN, MASK_TOKEN, verify_fit
from k3_fit import compare_edk2_fits


NOR_SIZE = 0x800000
REGIONS = {"esos": (0xb0000, 0x100000), "opensbi": (0x1b0000, 0x60000),
           "edk2": (0x210000, 0x4f0000)}
BUILD_FD = "MUSE-PICO.fd"
BUILD_FIT = "MUSE-Pico.itb"
CANDIDATE = "candidate; hardware qualification pending"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(obj):
    return (json.dumps(obj, indent=2) + "\n").encode()


def inspect_bundle(installer, bundle):
    subprocess.run([installer.resolve(), "inspect", "--bundle", bundle],
                   check=True, stdout=subprocess.DEVNULL)


def check_packaged_acpi(fit):
    repo = Path(__file__).resolve().parent
    env = {**os.environ, "K3_EDK2_TEST_FIT": str(fit.resolve())}
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                    "-p", "test_acpi_pcie_segments.py"], cwd=repo, env=env, check=True)


def checked_manifest(root, expected):
    raw = (root / "manifest.json").read_bytes()
    if sha(raw) != expected:
        raise ValueError(f"manifest digest mismatch for {root}")
    return raw, json.loads(raw)


def entry_data(root, entry):
    relative = Path(entry["path"])
    if (relative.is_absolute() or ".." in relative.parts
            or not (root / relative).resolve().is_relative_to(root.resolve())):
        raise ValueError(f"path escapes bundle: {relative}")
    data = (root / relative).read_bytes()
    if sha(data) != entry["sha256"] or len(data) != entry.get("size", len(data)):
        raise ValueError(f"size or checksum mismatch: {relative}")
    return data


def put(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as dest:
        dest.write(data)
    return {"path": str(relative), "size": len(data), "sha256": sha(data)}


def verify_build_provenance(built):
    if built.get("build_mode") != "isolated":
        raise ValueError("an isolated EDK2 build manifest is required")
    sources = built["sources"]
    platform = sources["platforms"]
    raw_recipe = base64.b64decode(sources["recipe_base64"], validate=True)
    recipe = json.loads(raw_recipe)
    patches = platform["patches"]
    inputs = [{k: v for k, v in p.items() if k != "content_base64"} for p in patches]
    if (sha(raw_recipe) != sources["recipe_sha256"] or sources["sdk"] != recipe["sdk"]
            or inputs != recipe["platforms"]["patches"]
            or platform["revision"] != recipe["platforms"]["revision"]
            or platform["repository"] != recipe["platforms"]["repository"]):
        raise ValueError("source recipe differs from recorded build metadata")
    for patch in patches:
        if sha(base64.b64decode(patch["content_base64"], validate=True)) != patch["sha256"]:
            raise ValueError("embedded platform patch differs from the recipe")
    if (built["arch"] != "RISCV64" or built["toolchain_tag"] != "GCC5"
            or built["flavor"] not in ("RELEASE", "DEBUG") or built["sku"] not in ("DEFAULT", "ALL")
            or "ACPI_ENABLE=TRUE" not in built["defines"] or built["command"][0] != "build"
            or not all(re.fullmatch(r"[0-9a-f]{40}", platform[k]) for k in ("revision", "tree"))):
        raise ValueError("missing isolated build source revision or target configuration")
    abi = built["pcd_token_abi"]
    headers = abi["headers_sha256"]
    if (abi.get("mask_token") != MASK_TOKEN or abi.get("bridge_array_token") != BRIDGES_TOKEN
            or abi.get("pei_local_tokens") != 0
            or set(headers) != {
                "RISCV64/Silicon/Spacemit/K3/Library/K3PcieHostBridgeLib/K3PcieHostBridgeLib/DEBUG/AutoGen.h",
                "RISCV64/MdeModulePkg/Universal/PCD/Dxe/Pcd/DEBUG/AutoGen.h"}):
        raise ValueError("isolated build must record the verified PCD consumer ABI")
    conf = built["conf_sha256"]
    toolchain = built["toolchain"]
    basetools = built["basetools"]
    if (set(conf) != {"target.txt", "build_rule.txt", "tools_def.txt"}
            or not toolchain["riscv64-linux-gnu-gcc"]["version"]
            or not basetools["command"] or "GenFv" not in basetools["binaries_sha256"]):
        raise ValueError("missing build configuration or compiler and BaseTools provenance")
    hashes = [sources["recipe_sha256"], sources["sdk"]["sha256"], *conf.values(), *headers.values(),
              *basetools["binaries_sha256"].values(), *(v["sha256"] for v in toolchain.values()),
              *(p["sha256"] for p in platform["patches"])]
    if not all(re.fullmatch("[a-f0-9]{64}", value) for value in hashes):
        raise ValueError("invalid SHA-256 in isolated build provenance")


def package(build, baseline, expected_base, destination, installer, reason, expected_revision=None):
    """Copy only authenticated baseline bytes; publish after staged inspection."""
    if any(destination.resolve().is_relative_to(src.resolve()) for src in (build, baseline)):
        raise ValueError("destination must be outside the baseline and build directories")
    if destination.exists() or destination.is_symlink() or not reason.strip():
        raise ValueError("packaging requires a fresh destination and a reason")
    inspect_bundle(installer, baseline)
    base_raw, manifest = checked_manifest(baseline, expected_base)
    sealed = {"manifest.json"} | {
        entry["path"] for group in ("files", "provenance") for entry in manifest.get(group, {}).values()
    }
    stored = {str(item.relative_to(baseline)) for item in baseline.rglob("*") if item.is_file()}
    if stored != sealed:
        raise ValueError("baseline contains missing or unsealed files")
    build_raw = (build / "manifest.json").read_bytes()
    built = json.loads(build_raw)
    verify_build_provenance(built)
    revision = built['sources']['platforms']['revision']
    if expected_revision is not None and revision != expected_revision:
        raise ValueError(f"expected platform revision {expected_revision}, build contains {revision}")
    artifacts = {}
    for name in (BUILD_FD, BUILD_FIT):
        data = (build / name).read_bytes()
        if sha(data) != built[name]["sha256"] or len(data) != built[name]["bytes"]:
            raise ValueError(f"build checksum or size mismatch: {name}")
        artifacts[name] = data

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        files = manifest["files"]
        for name, entry in files.items():
            original = entry_data(baseline, entry)
            if name == "edk2":
                base_fit = Path(temp) / "baseline.itb"
                base_fit.write_bytes(original)
                files[name] = put(stage, entry["path"], artifacts[BUILD_FIT])
            else:
                put(stage, entry["path"], original)
        fit = stage / files["edk2"]["path"]
        inventory = compare_edk2_fits(base_fit, fit, built[BUILD_FD]["sha256"])
        decoded = verify_fit(fit)
        check_packaged_acpi(fit)

        # Old qualification, flash logs and source IDs describe the baseline.
        # Keep their original bytes and manifest together under a separate path.
        provenance = {"baseline-manifest": put(stage, "provenance/baseline/manifest.json", base_raw)}
        for name, entry in manifest.get("provenance", {}).items():
            data = entry_data(baseline, entry)
            relative = Path("provenance/baseline") / entry["path"]
            provenance["baseline/" + name] = put(stage, relative, data)
        provenance["isolated-build"] = put(stage, "provenance/build.json", build_raw)
        provenance["edk2-candidate"] = put(stage, "provenance/candidate.json", json_bytes({
            "status": CANDIDATE, "baseline_manifest_sha256": expected_base, "change": reason,
            "changed_region": "edk2", "changed_fit_image": "uefi",
            "fit_comparison": inventory, "static_checks": decoded,
            "test_plan": ["Verify selected manifest and EDK2-only NOR readback",
                          "Confirm segment 2 and 4 I/O BAR allocation, NVMe EFI Block I/O,"
                          " RHEL GRUB on NVMe, running kernel and mounted NVMe root in one boot"],
            "rollback": "Use k3-firmware restore with this board's retained pre-flash transaction.",
        }))
        manifest.update(release=destination.name, firmware_qualification=CANDIDATE,
                        provenance=provenance)
        put(stage, "manifest.json", json_bytes(manifest))
        inspect_bundle(installer, stage)
        stage.rename(destination)
    return sha((destination / "manifest.json").read_bytes())


def selected(root, expected):
    _, manifest = checked_manifest(root, expected)
    if (manifest.get("firmware_qualification") != CANDIDATE
            or "edk2-candidate" not in manifest.get("provenance", {})):
        raise ValueError("select a candidate generated by the EDK2 release flow")
    for entry in manifest["provenance"].values():
        entry_data(root, entry)
    return manifest


def verify_readback(bundle, expected, transaction):
    manifest = selected(bundle, expected)
    raw = (transaction / "report.json").read_bytes()
    report = json.loads(raw)
    metadata = report["metadata"]
    if (report["schema"] != 1 or report["status"] != "verified" or not report["serial"]
            or report["completed"] != ["edk2"] or metadata["operation"] != "flash"
            or metadata["board_assertion"] != "pico-itx" or metadata["release"] != manifest["release"]
            or metadata["bundle_sha256"] != expected):
        raise ValueError("installer report does not identify a verified flash of the selected candidate")
    before = (transaction / "nor-before.bin").read_bytes()
    after = (transaction / "nor-after.bin").read_bytes()
    for name, image in (("before", before), ("after", after)):
        if len(image) != NOR_SIZE or sha(image) != report[f"{name}_sha256"]:
            raise ValueError(f"{name} NOR size or digest differs from installer report")
    for name, (start, capacity) in REGIONS.items():
        payload = entry_data(bundle, manifest["files"][name])
        length = (len(payload) + 0xfff) & ~0xfff if name == "edk2" else capacity
        if not 0 < len(payload) <= length <= capacity:
            raise ValueError(f"invalid {name} size")
        if after[start:start+length] != payload.ljust(length, b"\xff"):
            raise ValueError(f"NOR {name} region differs from selected candidate")
        if name == "edk2":
            write = {"name": name, "offset": start, "size": len(payload),
                     "erase_size": length, "sha256": sha(payload)}
            if (report["writes"] != [write] or before[:start] != after[:start]
                    or before[start+length:] != after[start+length:] or before == after):
                raise ValueError("NOR changed outside the single recorded EDK2 write or did not change")
    return {"status": "readback verified; boot qualification pending", "bundle_sha256": expected,
            "edk2_sha256": manifest["files"]["edk2"]["sha256"], "serial": report["serial"],
            "report_sha256": sha(raw), "before_sha256": sha(before), "after_sha256": sha(after)}


def flash(args):
    """Operator entry point. Guard the in-memory bundle and live plan before execute."""
    root = Path(__file__).resolve().parent
    if subprocess.check_output(["git", "-c", f"safe.directory={root}", "-C", root, "status",
                                "--porcelain", "--untracked-files=normal"]):
        raise ValueError("commit the repository changes before flashing")
    if args.backup_dir.exists():
        raise ValueError("flash requires a fresh transaction directory")
    installer = args.installer.resolve(strict=True)
    inspect_bundle(installer, args.bundle)
    manifest = selected(args.bundle, args.expect_sha256)
    if installer.name != "k3-firmware" or not (installer.parent / "k3firmware/cli.py").is_file():
        raise ValueError("--installer must identify k3-firmware in its installer checkout")
    sys.path.insert(0, str(installer.parent))
    from k3firmware import __version__
    from k3firmware.bundle import Bundle, Error, plan
    from k3firmware.cli import host_lock, describe
    from k3firmware.engine import execute
    from k3firmware.transport import prepare

    log = []

    def progress(message):
        line = datetime.now(timezone.utc).isoformat(timespec="seconds") + " " + message
        log.append(line)
        print(line, flush=True)

    try:
        with host_lock():
            candidate = Bundle.load(args.bundle)
            if candidate.manifest_sha256 != args.expect_sha256 or candidate.manifest != manifest:
                raise ValueError("selected manifest digest changed before flash")
            backend = prepare(candidate, args.device, progress=progress)
            before = backend.read_nor()
            writes = plan(candidate, before)
            describe(writes)
            if [w.name for w in writes] != ["edk2"]:
                raise ValueError("live installer plan must contain exactly one EDK2 write")
            print(f"Pico-ITX serial {backend.serial}; bundle SHA-256 {args.expect_sha256}")
            if not args.yes:
                prompt = f"FLASH {backend.serial}"
                if input(f"Type {prompt} to authorize this write: ").strip() != prompt:
                    raise ValueError("confirmation did not match")
            execute(backend, writes, before, args.backup_dir, {
                "tool_version": __version__, "release": candidate.manifest["release"],
                "bundle_sha256": args.expect_sha256, "board_assertion": "pico-itx",
                "operation": "flash", "log": log,
            }, progress)
    except Error as exc:
        raise ValueError(f"installer stopped: {exc}; retain transaction {args.backup_dir}") from exc
    return verify_readback(args.bundle, args.expect_sha256, args.backup_dir)


def has_allocation(quote, segment):
    """Accept EDK2 allocator output or an assigned I/O BAR for the endpoint."""
    if re.search(r"unassigned|failed|out of resources?|conflict|disabled", quote, re.I):
        return False
    bridges = re.split(r"RootBridge:\s*PciRoot\(0x([0-9a-f]+)\)", quote, flags=re.I)
    if len(bridges) > 1:
        # Bind this resource row to its preceding bridge header.
        for number, body in zip(bridges[1::2], bridges[2::2]):
            if int(number, 16) != segment:
                continue
            for base, length in re.findall(
                    r"I/O:\s*Base/Length/Alignment\s*=\s*([\da-f]+)/([\da-f]+)/[\da-f]+\s*-\s*Success",
                    body, re.I):
                if 0 < int(base, 16) < 0xffffffffffffffff and int(length, 16) > 0:
                    return True
        return False
    if not re.search(rf"(?:seg(?:ment)?\s*[:=]?\s*0*{segment}\b|000{segment}:01:00\.0)", quote, re.I):
        return False
    match = re.search(r"I/O\s+(?:ports at|BAR assigned)\s+(?:0x)?([0-9a-f]+)\b", quote, re.I)
    return bool(match and 0 < int(match[1], 16) < 0xffffffffffffffff)


def selected_rhel_efi(quote):
    redhat = r"(?:red\s*hat|\brhel\b)"
    if re.search(rf"(?im)^.*BdsDxe:\s*starting Boot[0-9a-f]{{4}}[^\n]*{redhat}", quote):
        return True
    current = re.search(r"(?im)^BootCurrent:\s*([0-9a-f]{4})\s*$", quote)
    return bool(current and re.search(rf"(?im)^Boot{current[1]}\*?\s+[^\n]*{redhat}", quote))


def has_root_ancestry(quote, source, disk):
    if re.fullmatch(rf"/dev/{re.escape(disk)}(?:p\d+)?", source):
        return True
    # lsblk -s walks only ancestors of the supplied root device. Restrict
    # the match to the single-column output immediately following that command.
    match = re.search(rf"(?m)\blsblk -snro KNAME -- {re.escape(source)}[ \t]*$\n"
                      r"((?:^[\w.-]+$(?:\n|\Z))+)", quote)
    return bool(match and disk in match[1].splitlines())


def displayed(text):
    return re.sub(r"\x1b\[[0-9;:]*m", "", re.sub(r"\r+\n", "\n", text))


def scan_capture(path, excerpts, block_bytes=1 << 20):
    """Hash raw serial bytes and search displayed text using bounded overlap."""
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    missing = set(excerpts)
    overlap = max(map(len, missing)) - 1
    tail = ""
    pending = ""
    with path.open("rb") as stream:
        while True:
            block = stream.read(block_bytes)
            digest.update(block)
            if missing:
                text = pending + decoder.decode(block, final=not block)
                # The next chunk may complete a split SGR sequence or CRCRLF.
                partial = re.search(r"(?:\x1b(?:\[[0-9;:]{0,255})?|\r{1,255})\Z", text) if block else None
                pending = text[partial.start():] if partial else ""
                ready = text[:partial.start()] if partial else text
                window = tail + displayed(ready)
                missing = {quote for quote in missing if quote not in window}
                tail = window[-overlap:] if overlap else ""
            if not block:
                break
    if missing:
        raise ValueError(f"submitted excerpt missing from raw capture {path}")
    return digest.hexdigest()


def boot_evidence(receipt, evidence, expected_kernel, expected_root):
    """Validate the operator's same-boot observations against retained raw captures."""
    import uuid

    raw = (evidence / "boot.json").read_bytes()
    observed = json.loads(raw)
    for field in ("bundle_sha256", "report_sha256", "serial"):
        if observed[field] != receipt[field]:
            raise ValueError(f"boot evidence has a different {field}")
    boot_id = str(uuid.UUID(observed["boot_id"]))
    if not observed["operator"].strip() or observed["same_boot"] is not True:
        raise ValueError("named operator must attest all observations identify this one boot")
    required = {"segment2_io", "segment4_io", "nvme_block_io", "rhel_grub", "running_root"}
    if set(observed["milestones"]) != required:
        raise ValueError("boot evidence needs all five qualification milestones")
    quotes = {}
    by_file = {}
    for name, excerpts in observed["milestones"].items():
        pieces = []
        for entry in excerpts if isinstance(excerpts, list) else [excerpts]:
            relative = Path(entry["file"])
            capture = (evidence / relative).resolve()
            if (relative.is_absolute() or not capture.is_relative_to(evidence.resolve())
                    or capture == (evidence / "boot.json").resolve()):
                raise ValueError(f"invalid raw capture path for {name}")
            quote = displayed(entry["quote"])
            if not quote.strip():
                raise ValueError(f"empty excerpt for {name}")
            pieces.append(quote)
            by_file.setdefault(str(relative), set()).add(quote)
        quotes[name] = "\n".join(pieces)

    captures = {relative: scan_capture(evidence / relative, excerpts)
                for relative, excerpts in by_file.items()}
    for segment in (2, 4):
        if not has_allocation(quotes[f"segment{segment}_io"], segment):
            raise ValueError(f"segment {segment} requires a successful I/O allocation excerpt")
    if not re.search(r"nvme", quotes["nvme_block_io"], re.I) or not re.search(
            r"block\s*i/?o|\bblk\d+\b", quotes["nvme_block_io"], re.I):
        raise ValueError("missing NVMe EFI Block I/O evidence")
    grub = quotes["rhel_grub"]
    # A short-form HD() EFI boot entry can be joined to a mapped NVMe BLK/FS
    # handle by partition GUID or EFI Shell alias across the retained excerpts.
    handles = r"\b(?:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|(?:blk|fs)\d+)\b"
    block_ids = set(re.findall(handles, quotes["nvme_block_io"].lower()))
    grub_ids = set(re.findall(handles, grub.lower()))
    if (not selected_rhel_efi(grub) or not re.search("grub", grub, re.I)
            or not (re.search("nvme", grub, re.I) or block_ids & grub_ids)
            or re.search("ubuntu", grub, re.I)):
        raise ValueError("missing selected RHEL GRUB entry on NVMe")
    running = quotes["running_root"]
    kernel = observed["kernel_release"]
    source = observed["root_source"]
    disk = observed["nvme_disk"]
    if (kernel, source) != (expected_kernel, expected_root):
        raise ValueError("observed kernel or root differs from the planned boot target")
    if (not kernel.strip() or not source.startswith("/dev/") or not re.fullmatch(r"nvme\d+n\d+", disk)
            or not re.search(r"""(?im)^ID=["']?rhel["']?\s*$""", running)
            or any(value not in running.splitlines() for value in (boot_id, kernel))
            or not has_root_ancestry(running, source, disk)
            or not (re.search(rf"(?m)^/\s+{re.escape(source)}(?:\s|$)", running)
                    or re.search(rf"(?m)\bfindmnt -nro SOURCE /\s*$\n{re.escape(source)}$", running))):
        raise ValueError("RHEL root evidence must include boot ID, kernel release, mounted source and backing NVMe disk")
    return {"qualification": "operator-attested hardware qualification",
            "expected_kernel": expected_kernel, "expected_root": expected_root,
            "readback": receipt, "observations": observed, "observations_sha256": sha(raw),
            "capture_sha256": captures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("package", help="verify and publish a candidate bundle")
    pack.add_argument("--build", required=True, type=Path)
    pack.add_argument("--expect-platform-revision", help="require the build to contain this platform commit")
    pack.add_argument("--baseline", required=True, type=Path)
    pack.add_argument("--baseline-sha256", required=True, help="qualified baseline manifest SHA-256")
    pack.add_argument("--destination", required=True, type=Path)
    pack.add_argument("--reason", required=True)
    pack.add_argument("--installer", required=True, type=Path)
    write = commands.add_parser("flash", help="operator-only, interactive EDK2 flash")
    read = commands.add_parser("readback", help="verify a completed installer transaction offline")
    qualify = commands.add_parser("qualify", help="bind operator boot evidence to the verified transaction")
    for sub in (write, read, qualify):
        sub.add_argument("--bundle", type=Path, required=True)
        sub.add_argument("--expect-sha256", required=True, help="selected candidate manifest SHA-256")
    write.add_argument("--installer", required=True, type=Path)
    write.add_argument("--backup-dir", required=True, type=Path)
    write.add_argument("--board", required=True, choices=["pico-itx"])
    write.add_argument("--device", required=True)
    write.add_argument("--yes", action="store_true", help="authorize the checked EDK2-only live plan")
    for sub in (read, qualify):
        sub.add_argument("--transaction", required=True, type=Path)
    qualify.add_argument("--evidence", required=True, type=Path)
    qualify.add_argument("--output", required=True, type=Path)
    qualify.add_argument("--expect-kernel", required=True, help="planned running uname -r")
    qualify.add_argument("--expect-root", required=True, help="planned mounted root device")
    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            digest = package(args.build, args.baseline, args.baseline_sha256, args.destination,
                             args.installer, args.reason, args.expect_platform_revision)
            print(json.dumps({"bundle": str(args.destination.resolve()), "bundle_sha256": digest,
                              "status": CANDIDATE}, indent=2))
        elif args.command == "flash":
            print(json.dumps(flash(args), indent=2))
        else:
            receipt = verify_readback(args.bundle, args.expect_sha256, args.transaction)
            if args.command == "readback":
                print(json.dumps(receipt, indent=2))
            else:
                if args.output.resolve().is_relative_to(args.bundle.resolve()):
                    raise ValueError("write qualification evidence outside the immutable candidate bundle")
                result = boot_evidence(receipt, args.evidence, args.expect_kernel, args.expect_root)
                with args.output.open("xb") as out:
                    out.write(json_bytes(result))
                print(args.output.resolve())
    except (OSError, KeyError, ValueError, TypeError, AttributeError, subprocess.CalledProcessError, EOFError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
