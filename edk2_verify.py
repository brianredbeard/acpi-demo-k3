#!/usr/bin/env python3
"""Verify the packaged MUSE-Pico DEFAULT SKU PCIe configuration (host only)."""

import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from uuid import UUID

from k3_fit import read_edk2_fit


def guid(text):
    return UUID(text).bytes_le


# MUSE-Pico.fdf -> DXEFV -> PcdDxe/RAW and K3AcpiTables/RAW
FFS2 = guid("8c8ce578-8a3d-4f1c-9935-896185c32dd3")
DXE_IMAGE = guid("91da8a5d-2469-49c0-8e37-ca55b92f03e6")
LZMA_SECTION = guid("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
PCD_DXE = guid("80cf7257-87ab-47f9-a3fe-d50b76d89541")
ACPI_TABLES = guid("7e374e25-8e01-4fee-87f2-390c23c606cd")
PCD_SIGNATURE = guid("3c7d193c-682c-4c14-a68f-552dea4f437e")
# The version 7 RELEASE DB omits token names. Bind these to the generated
# consuming library via verify_token_abi in every new build.
MASK_TOKEN = 20
# 2026-11-23: PcdPciePortAGeometryWhenBDisabled (0x30010007) was added
# between the mask and the bridge table in K3.dec, shifting the bridge
# table's dynamic token 24 -> 25. Reviewed: the SKU-gated Port A lane
# geometry (edk2-platforms e0a11126 + token fix ed2506ec + INF 96a276aa).
BRIDGES_TOKEN = 25
# Pico DT /soc/pcie@80800000 and /soc/pcie@81000000, first ranges tuple.
CPU_IO_BASE = {2: 0x1200010000, 4: 0x12c0010000}
IO_SIZE = 0x100000


def verify_token_abi(build_dir):
    """Check the generated library accessors and numbering against this decoder."""
    riscv = Path(build_dir) / "RISCV64"
    lib = riscv / "Silicon/Spacemit/K3/Library/K3PcieHostBridgeLib/K3PcieHostBridgeLib/DEBUG/AutoGen.h"
    dxe = riscv / "MdeModulePkg/Universal/PCD/Dxe/Pcd/DEBUG/AutoGen.h"
    patterns = {dxe: {"PEI_LOCAL_TOKEN_NUMBER": "0U"}, lib: {}}
    for name, number, width, getter in [
        ("PcdPcieHostEnableMask", MASK_TOKEN, "8", "LibPcdGet8"),
        ("PcdBoardPciRootBridgeResourceConfigTable", BRIDGES_TOKEN, "PTR", "LibPcdGetPtr"),
    ]:
        token = "_PCD_TOKEN_" + name
        patterns[lib][token] = f"{number}U"
        patterns[lib][f"_PCD_GET_MODE_{width}_{name}"] = f"{getter}({token})"
    hashes = {}
    for path, macros in patterns.items():
        data = path.read_bytes()
        for macro, value in macros.items():
            bindings = re.findall(r"^#define[ \t]+" + macro + r"[ \t]+([^\r\n]+)", data.decode(), re.M)
            if [v.strip() for v in bindings] != [value]:
                raise ValueError(f"unreviewed PCD ABI in {path}: {macro} = {bindings!r}")
        hashes[str(path.relative_to(build_dir))] = hashlib.sha256(data).hexdigest()
    return {"headers_sha256": hashes, "pei_local_tokens": 0,
            "mask_token": MASK_TOKEN, "bridge_array_token": BRIDGES_TOKEN}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def only(items, label):
    items = list(items)
    require(len(items) == 1, f"expected one {label}, found {len(items)}")
    return items[0]


def span(data, start, size, label):
    require(0 <= start <= len(data) and 0 <= size <= len(data) - start,
            f"invalid {label} bounds")
    return data[start:start + size]


def read_int(data, start, size):
    return int.from_bytes(span(data, start, size, "integer"), "little")


def files(volume, targets):
    """Enumerate direct FFS2 children of a K3 FV with erase polarity one."""
    require(volume[16:32] == FFS2 and volume[40:44] == b"_FVH" and
            read_int(volume, 32, 8) == len(volume) and read_int(volume, 44, 4) & 0x800,
            "invalid K3 FFS2 volume")
    header_size = read_int(volume, 48, 2)
    header = span(volume, 0, header_size, "FV header")
    require(header_size >= 56 and header_size % 2 == 0 and
            sum(word for word, in struct.iter_unpack("<H", header)) % 65536 == 0,
            "invalid FV header checksum or length")
    pos = (header_size + 7) & ~7
    found = {}
    while pos < len(volume):
        hdr = volume[pos:pos+24]
        if hdr == b"\xff" * len(hdr):
            require(volume.count(b"\xff", pos) == len(volume) - pos, "non-erased FV tail")
            break
        size = read_int(hdr, 20, 3)
        require(len(hdr) == 24 and 24 <= size < 0xffffff and not (hdr[19] & 1),
                "invalid K3 FFS file length or format")
        require((sum(hdr) - hdr[17] - hdr[23]) % 256 == 0, "invalid FFS header checksum")
        body = span(volume, pos+24, size-24, "FFS body")
        name = hdr[:16]
        if name in targets:
            require(name not in found and hdr[18] == targets[name] and hdr[23] == 0xf8,
                    f"inactive, duplicate, or incorrectly typed FFS file {UUID(bytes_le=name)}")
            if hdr[19] & 0x40:
                require((sum(body) + hdr[17]) % 256 == 0, "invalid FFS data checksum")
            found[name] = body
        pos = (pos + size + 7) & ~7
    for name in targets:
        require(name in found, f"missing FFS file {UUID(bytes_le=name)}")
    return found


def sections(body, kind):
    pos = 0
    while pos < len(body):
        size = read_int(body, pos, 3)
        require(4 <= size < 0xffffff, "invalid PI section length")
        section = span(body, pos, size, "PI section")
        if section[3] == kind:
            yield section[4:]
        pos = (pos + size + 3) & ~3


def dxe_volume(fd):
    container = files(fd, {DXE_IMAGE: 0x0b})[DXE_IMAGE]
    guided = only(sections(container, 2), "DXE GUID-defined section")
    require(guided[:16] == LZMA_SECTION and guided[16:20] == b"\x18\0\x01\0",
            "unsupported DXE guided section")
    # EDK II LzmaCompress records the known output size in an LZMA-alone header.
    size = read_int(guided, 25, 8)
    require(0 < size <= 64 * 1024**2, "invalid DXE FV decompression size")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=128 * 1024**2)
    try:
        inflated = decoder.decompress(guided[20:], max_length=size + 1)
    except lzma.LZMAError as exc:
        raise ValueError(f"invalid DXE LZMA stream: {exc}") from exc
    require(len(inflated) == size and decoder.eof and not decoder.unused_data,
            "invalid compressed DXE FV length")
    return only(sections(inflated, 0x17), "DXE firmware volume")


def packaged_data(fd):
    dxe = dxe_volume(fd)
    content = files(dxe, {PCD_DXE: 7, ACPI_TABLES: 2})
    db = only(sections(content[PCD_DXE], 0x19), "PcdDxe RAW database")
    tables = {}
    raw = list(sections(content[ACPI_TABLES], 0x19))
    for signature in (b"MCFG", b"DSDT"):
        name = signature.decode()
        section = only((sec for sec in raw if sec[:4] == signature), name)
        # ASLC output can have ELF/linker padding beyond the ACPI header length.
        size = read_int(section, 4, 4)
        require(size >= 36 and section[10:16] == b"SPMT  ", f"invalid {name} header")
        tables[name] = span(section, 0, size, name)
    require(sum(tables["DSDT"]) % 256 == 0, "invalid DSDT checksum")
    return db, tables


def trace_masks(libraries):
    masks = {}
    for lib, key, required in (
            ("BaseDebugPrintErrorLevelLib", "PcdDebugPrintErrorLevel", 0xffffffff),
            ("BaseDebugLibSerialPort", "PcdDebugPropertyMask", 0x02),
            ("BaseDebugLibSerialPort", "PcdFixedDebugPrintErrorLevel", 0xffffffff)):
        header = libraries / lib / lib / "DEBUG/AutoGen.h"
        value = re.search(r"^#define\s+_PCD_VALUE_" + key + r"\s+(0x[0-9a-fA-F]+|\d+)\s*$",
                          header.read_text(), re.M)
        require(value and int(value[1], 0) & required == required,
                f"serial trace requires {key} mask {required:#x} in {header}")
        masks[key] = int(value[1], 0)
    return masks


def verify_serial_trace(fd, build_dir):
    """Bind the logging configuration and driver link inputs to the packaged PE images."""
    arch = build_dir / "RISCV64"
    masks = trace_masks(arch / "MdePkg/Library")
    volume = dxe_volume(fd)
    drivers = {}
    for name, identifier, marker in (
            ("PciBusDxe", "93b80004-9fb3-11d4-9a3a-0090273fc14d", b"PciBus: Discovered"),
            ("PciHostBridgeDxe", "128fb770-5e79-4176-9e51-9bb268a17dd1", b"Base/Length/Alignment")):
        out = arch / "Silicon/Spacemit/Override/MdeModulePkg/Bus/Pci" / name / name / "OUTPUT"
        links = {Path(line).name for line in (out / "static_library_files.lst").read_text().splitlines()}
        require({"BaseDebugPrintErrorLevelLib.lib", "BaseDebugLibSerialPort.lib",
                 "BaseSerialPortLibRiscVSbiLibRam.lib"} <= links, f"{name} lacks the serial debug libraries")
        key = guid(identifier)
        pe = only(sections(files(volume, {key: 7})[key], 0x10), f"{name} executable")
        require(marker in pe and pe == (out / (name + ".efi")).read_bytes(),
                f"{name} trace executable differs from its packaged image or lacks its PCI trace")
        drivers[name] = hashlib.sha256(pe).hexdigest()
    return {"masks": masks, "drivers_sha256": drivers}


def packaged_tables(path):
    fd, _, _ = read_edk2_fit(path)
    return packaged_data(fd)[1]


def decode_pcd(raw):
    """Resolve DEFAULT tokens as PcdDxe does, including the string and size tables."""
    require(raw[:16] == PCD_SIGNATURE and read_int(raw, 16, 4) == 7 and
            read_int(raw, 24, 8) == 0 and read_int(raw, 32, 4) == len(raw),
            "unsupported DXE PCD database version, SKU, or size")
    db = span(raw, 0, read_int(raw, 20, 4), "DEFAULT PCD database")
    local, _, _, strings, sizes = struct.unpack_from("<5I", span(db, 40, 20, "PCD offsets"))
    count = read_int(db, 68, 2)
    require(count >= BRIDGES_TOKEN, "missing PCIe PCD tokens")
    entries = [value for value, in struct.iter_unpack("<I", span(db, local, 4*count, "PCD tokens"))]
    mask = entries[MASK_TOKEN-1]
    pointer = entries[BRIDGES_TOKEN-1]
    require(mask >> 20 == 0x10 and pointer >> 20 == 0x100, "unexpected PCIe PCD token types")
    mask_value = read_int(db, mask & 0xfffff, 1)
    offset = strings + read_int(db, pointer & 0xfffff, 4)
    # Each preceding VOID* consumes two UINT16s (maximum and current length).
    preceding = sum((value & 0x0f000000) == 0 for value in entries[:BRIDGES_TOKEN-1])
    maximum, current = struct.unpack("<HH", span(db, sizes+4*preceding, 4, "PCD size entry"))
    require(0 < current <= maximum and offset+maximum <= sizes, "invalid PCIe array pointer or size")
    table = span(db, offset, current, "PCD root bridge table")
    # Packed PciRootBrdigeResourceConfig.h: UINT16, four UINT64s, five triples
    # of UINT64s (Io, Mem, Mem64, PMem, PMem64), BOOLEAN. ArrayNum is UINT16.
    record = struct.Struct("<H19QB")
    n = read_int(table, 0, 2)
    require(n == 5 and len(table) == 2+n*record.size, "unexpected PCIe bridge array shape")
    bridges = {}
    for index, row in enumerate(record.iter_unpack(table[2:])):
        seg, config, size, bus0, bus1 = row[:5]
        io, mem, mem64, pmem, pmem64 = row[5:8], row[8:11], row[11:14], row[14:17], row[17:20]
        require(seg == index, f"misindexed PCD segment {seg} at port {index}")
        triple = lambda t: {"pci_base": t[0], "size": t[1], "cpu_base": t[2]}
        bridges[str(seg)] = {"config_base": config, "config_size": size, "bus": [bus0, bus1],
                             "io": triple(io), "mem": triple(mem), "mem64": triple(mem64),
                             "pmem": triple(pmem), "pmem64": triple(pmem64)}
    return {"sku": 0, "enable_mask": mask_value, "segments": bridges,
            "mask_token": MASK_TOKEN, "mask_db_offset": mask & 0xfffff,
            "bridge_array_token": BRIDGES_TOKEN, "bridge_array_db_offset": offset}


def decode_crs(buf):
    """Decode Word/DWord/QWord address space descriptors from the evaluated _CRS."""
    pos = 0
    descriptors = []
    while pos < len(buf):
        tag = buf[pos]
        if tag == 0x79:
            require(pos + 2 == len(buf), "invalid _CRS End Tag")
            return descriptors
        # These K3 root bridge templates consist exclusively of address descriptors.
        width = {0x88: 2, 0x87: 4, 0x8a: 8}.get(tag)
        require(width is not None, f"unexpected _CRS descriptor {tag:#x}")
        payload = span(buf, pos+3, read_int(buf, pos+1, 2), "_CRS descriptor")
        require(len(payload) == 3+5*width, "unsupported _CRS address descriptor length")
        kind = {0: "memory", 1: "io", 2: "bus"}.get(payload[0])
        require(kind is not None, "unsupported _CRS resource type")
        values = [read_int(payload, 3+i*width, width) for i in range(5)]
        descriptors.append(dict(kind=kind, flags=payload[1], type_flags=payload[2],
                                granularity=values[0], minimum=values[1], maximum=values[2],
                                translation=values[3], length=values[4]))
        pos += 3 + len(payload)
    raise ValueError("unterminated _CRS resource template")


def decode_dsdt(dsdt):
    """Evaluate fully qualified objects with ACPICA's host interpreter."""
    keys = {"_HID": "hid", "_SEG": "seg", "_BBN": "bbn", "_CRS": "resources"}
    paths = {rf"\_SB.PCI{seg}.{field}": (str(seg), key)
             for seg in CPU_IO_BASE for field, key in keys.items()}
    commands = ";".join("evaluate " + path for path in paths)
    with tempfile.TemporaryDirectory() as tmp:
        table = Path(tmp) / "DSDT.aml"
        table.write_bytes(dsdt)
        try:
            proc = subprocess.run(["acpiexec", "-di", "-dt", "-dr", "-b", commands, str(table)],
                                  capture_output=True, cwd=tmp, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"could not evaluate DSDT with acpiexec: {exc}") from exc
    require(proc.returncode == 0, f"acpiexec failed: {proc.stderr.strip()}")
    result = {str(seg): {} for seg in CPU_IO_BASE}
    for block in re.split(r"^Evaluating ", proc.stdout, flags=re.M)[1:]:
        path, _, body = block.partition("\n")
        require(path in paths and f"Evaluation of {path} returned object" in body,
                f"missing DSDT object {path}")
        seg, key = paths[path]
        require(key not in result[seg], f"duplicate ACPICA result for {path}")
        if key == "resources":
            length = re.search(r"\[Buffer\] Length ([0-9a-fA-F]+) =", body)
            require(length, f"{path} did not evaluate to a buffer")
            buf = bytearray()
            for off, octets in re.findall(r"^\s*([0-9A-Fa-f]+): ([0-9A-Fa-f ]+)//", body, re.M):
                require(int(off, 16) == len(buf), f"truncated ACPICA output for {path}")
                buf.extend(bytes.fromhex(octets))
            require(len(buf) == int(length[1], 16), f"invalid ACPICA buffer length for {path}")
            value = decode_crs(buf)
        elif key == "hid":
            match = re.search(r'\[String\] Length [0-9A-Fa-f]+ = "([^"]+)"', body)
            require(match, f"missing PCI host hardware ID at {path}")
            value = match[1]
        else:
            match = re.search(r"\[Integer\] = ([0-9A-Fa-f]+)", body)
            require(match, f"{path} did not evaluate to an integer")
            value = int(match[1], 16)
        result[seg][key] = value
    for seg, values in result.items():
        require(values.keys() == set(keys.values()), f"incomplete AML evaluation for PCI{seg}")
    return result


def decode_mcfg(table):
    require(len(table) == 60 and table[:4] == b"MCFG" and table[8] == 1 and
            table[16:24] == b"K3      " and read_int(table, 24, 4) == 1 and
            read_int(table, 36, 8) == 0, "expected K3 MCFG with one allocation")
    base, seg, start, end, reserved = struct.unpack_from("<QHBBI", table, 44)
    require((base, seg, start, end, reserved) == (0x1100000000, 0, 0, 255, 0),
            "MCFG must describe only segment 0 at 0x1100000000, buses 0..255")
    return {"base": base, "segment": seg, "bus": [start, end]}


def describe_address(d):
    return (f"{d['minimum']:#x}..{d['maximum']:#x}, translation={d['translation']:#x}, "
            f"length={d['length']:#x}, flags={d['flags']:#x}/{d['type_flags']:#x}, "
            f"granularity={d['granularity']:#x}")


def check_pcie_profile(pcd, aml):
    errors = []
    if pcd["enable_mask"] != 0x15:
        errors.append(f"DEFAULT PCIe enable mask={pcd['enable_mask']:#x}, expected 0x15")
    nvme = pcd["segments"]["0"]
    if (nvme["config_base"], nvme["config_size"], nvme["bus"]) != (0x1100000000, 0x10000000, [0, 255]):
        errors.append("PCD segment 0 must match MCFG: ECAM base 0x1100000000, 256 MiB, buses 0..255")
    for seg, cpu in CPU_IO_BASE.items():
        rb = pcd["segments"][str(seg)]
        first, last = rb["bus"]
        if first != 0 or not 1 <= last <= 255:
            errors.append(f"PCD segment {seg} bus range {first}..{last} must cover buses 0 and 1")
        if rb["config_base"] != cpu - 0x10000 or rb["config_size"] != 0x10000:
            errors.append(f"PCD segment {seg} has unexpected compact config window")
        io = rb["io"]
        if io != {"pci_base": 0, "size": IO_SIZE, "cpu_base": cpu}:
            errors.append(f"PCD segment {seg} I/O pci_base={io['pci_base']:#x}, size={io['size']:#x}, "
                          f"cpu_base={io['cpu_base']:#x}; expected 0x0, 0x100000, {cpu:#x}")
        dev = aml[str(seg)]
        if (dev["hid"], dev["seg"], dev["bbn"]) != ("PNP0A08", seg, 0):
            errors.append(f"DSDT PCI{seg} _HID={dev['hid']}, _SEG={dev['seg']}, _BBN={dev['bbn']}")
        # General flags 0x0c = producer, positive decode, fixed min and max.
        # Compare PCI-side endpoints AND CPU translation, including the length.
        for kind, type_flags, low, high, translation, size in (
                ("bus", 0, first, last, 0, last-first+1),
                ("io", 3, 0, IO_SIZE-1, cpu, IO_SIZE)):
            descriptors = [d for d in dev["resources"] if d["kind"] == kind]
            expected = dict(kind=kind, flags=12, type_flags=type_flags, granularity=0,
                            minimum=low, maximum=high, translation=translation, length=size)
            if descriptors != [expected]:
                label = "I/O" if kind == "io" else "bus"
                actual = " | ".join(describe_address(d) for d in descriptors) or "missing"
                errors.append(f"DSDT PCI{seg} _CRS {label}: {actual}; expected {describe_address(expected)}")
        # Memory triples: non-prefetchable (MTP uncacheable) and
        # prefetchable (MTP prefetchable) QWordMemory producers must
        # match the PCD windows (rhct12 audit: the checker previously
        # dropped the memory triples; the PCI2 1 MiB top-end mismatch
        # went unnoticed). _QWD TypeFlags MTP bits [1:0]:
        # 1 = uncacheable (non-prefetchable), 3 = prefetchable.
        for kind, pcd_key, mtp in (("memory", "mem", 1), ("memory", "pmem64", 3)):
            window = rb[pcd_key]
            if window["size"] == 0:
                continue
            descriptors = []
            for d in dev["resources"]:
                if d["kind"] == kind and (d["type_flags"] & 0x3) == mtp:
                    d = dict(d, type_flags=mtp)
                    descriptors.append(d)
            lo, sz = window["pci_base"], window["size"]
            expected = dict(kind=kind, flags=12, type_flags=mtp, granularity=0,
                            minimum=lo, maximum=lo+sz-1,
                            translation=window["cpu_base"] - lo, length=sz)
            if descriptors != [expected]:
                label = "prefetchable memory" if mtp == 3 else "memory"
                actual = " | ".join(describe_address(d) for d in descriptors) or "missing"
                errors.append(f"DSDT PCI{seg} _CRS {label}: {actual}; expected {describe_address(expected)}")
    if errors:
        raise ValueError("\n".join(errors))


def check_bus_limit(pcd, aml, limit):
    require(0 <= limit <= 255, "expected secondary bus limit must be in 0..255")
    for seg in CPU_IO_BASE:
        key = str(seg)
        bus = pcd["segments"][key]["bus"]
        bridge = aml[key]
        require((bridge["hid"], bridge["seg"], bridge["bbn"]) == ("PNP0A08", seg, 0),
                f"packaged AML root PCI{seg} must identify segment {seg}, base bus 0")
        ranges = [(d["minimum"], d["maximum"], d["length"]) for d in bridge["resources"]
                  if d["kind"] == "bus"]
        require(bus == [0, limit] and ranges == [(0, limit, limit + 1)],
                f"segment {seg} expected buses 0..{limit}, packaged PCD {bus}, AML {ranges}")


def verify_fit(path, *, diagnostic=False, expected_bus_limit=None):
    try:
        fd, hashes, fit = read_edk2_fit(path)
        db, tables = packaged_data(fd)
        pcd = decode_pcd(db)
        aml = decode_dsdt(tables["DSDT"])
        mcfg = decode_mcfg(tables["MCFG"])
        if expected_bus_limit is not None:
            check_bus_limit(pcd, aml, expected_bus_limit)
        violations = []
        try:
            check_pcie_profile(pcd, aml)
        except ValueError as exc:
            if not diagnostic:
                raise
            violations = str(exc).splitlines()
        return {"fit": fit, "images": hashes, "pcd": pcd, "dsdt": aml, "mcfg": mcfg,
                "profile_violations": violations,
                "tables_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in tables.items()},
                "pcd_database_sha256": hashlib.sha256(db).hexdigest()}
    except OSError as exc:
        raise ValueError(str(exc)) from exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fit", type=Path, help="final packaged edk2.bin or .itb")
    parser.add_argument("--diagnostic", action="store_true", help="report PCIe profile differences as data")
    parser.add_argument("--expect-bus-limit", type=lambda s: int(s, 0), help="assert the PCD and AML bus limit on segments 2 and 4")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_fit(args.fit, diagnostic=args.diagnostic,
                                    expected_bus_limit=args.expect_bus_limit), indent=2))
    except ValueError as error:
        sys.exit(str(error))
