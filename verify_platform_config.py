#!/usr/bin/env python3
"""Verify the K3 Platform Configuration form and its native timeout link in a FIT."""
import argparse
import json
from pathlib import Path
import struct

from edk2_verify import (ACPI_TABLES, PCD_DXE, PCD_SIGNATURE, dxe_volume, files,
                         guid, only, read_int, require, sections, span)
from k3_fit import read_edk2_fit


SNAPSHOT_DRIVER = guid("8e1fbc5f-c4c3-4f3f-8059-13736855a1d0")
HII_DRIVER = guid("804b392a-e5ed-4b29-8183-60047e8b037c")
PAGE = guid("cc9c5ba8-aa74-444e-9ea5-d83898308d71")
PLATFORM_MANAGER = guid("2faa29ba-0cf4-4dcf-8669-4a44532a694f")
MANAGER_FORMSET = guid("26741529-7779-4217-9853-a922cdacf960")
UI_APP = guid("462caa21-7614-4503-836e-8ab6f4662331")
BDS = guid("6d33944a-ec75-4855-a54d-809c75241f6c")
BROWSER = guid("ebf342fe-b1d3-4ef8-957c-8048606ff671")
BOOT_MAINTENANCE = guid("642237c7-35d4-472d-8365-12e0ccf27a22")
TIANO = guid("0f0b1735-87a0-4193-b266-538c38af48ce")
EFI_GLOBAL = guid("8be4df61-93ca-11d2-aa0d-00e098032b8c")
BMM_MAIN = 0x1001
BMM_TIMEOUT = 0x1012


def form_package(pe, identity):
    """Find the forms package headed by this scoped FORM_SET in the compiled PE."""
    starts = []
    pos = pe.find(identity)
    while pos != -1:
        if pos >= 6 and pe[pos - 3] == 2 and pe[pos - 2] == 0x0e and pe[pos - 1] & 0x80:
            starts.append(pos - 6)
        pos = pe.find(identity, pos + len(identity))
    start = only(starts, "HII forms package with the specified formset identity")
    end = start + read_int(pe, start, 3)
    require(start + 6 <= end <= len(pe), "invalid HII forms package length")
    pos = start + 4
    # Track the enclosing form for references and dynamic update labels.
    forms = []
    while pos < end:
        code, flags = span(pe, pos, 2, "IFR header")
        length = flags & 0x7f
        require(length >= 2 and pos + length <= end, "invalid IFR opcode length")
        op = pe[pos:pos+length]
        form = forms[-1] if forms else None
        if code == 0x01:
            form = read_int(op, 2, 2)
        yield form, code, op
        if code == 0x29:
            require(forms and length == 2, "unmatched IFR END")
            forms.pop()
        elif flags & 0x80:
            forms.append(form)
        pos += length
    require(not forms, "unterminated IFR scope")


def check_page(pe, mode):
    ops = list(form_package(pe, PAGE))
    formset = only((op for _, code, op in ops if code == 0x0e), "K3 formset")
    require(len(formset) == 39 and formset[22] == 1 and formset[23:] == PLATFORM_MANAGER,
            "K3 formset must link once under the Platform Manager class")
    only((op for form, code, op in ops if code == 1 and form == 1), "K3 main form")
    require(all(code not in (0x24, 0x25, 0x26) for _, code, _ in ops),
            "unexpected writable varstore on K3 information page")
    # REF3 holds a destination form ID, question ID and formset GUID after its
    # 11-byte question header. The native question is created on BMM form open.
    destination = struct.pack("<HH", BMM_MAIN, BMM_TIMEOUT) + BOOT_MAINTENANCE
    refs = [(form, op[13:]) for form, code, op in ops if code == 0x0f]
    require(refs == ([(1, destination)] if mode == "acpi" else []),
            f"unexpected timeout reference in {mode.upper()} form package")
    check_open_callback(ops, 1, 0x7f01)


def check_open_callback(ops, form, key):
    # Both owners use the EDK II suppressed interactive text idiom. The VFR
    # compiler emits an ACTION under SUPPRESS_IF TRUE with the callback flag.
    statements = [op for main, _, op in ops if main == form]
    index = only((i for i, op in enumerate(statements)
                  if op[0] == 0x0c and len(op) >= 13 and read_int(op, 6, 2) == key),
                 f"FORM_OPEN callback action {key:#06x}")
    require(statements[index][12] & 4 and
            statements[max(0, index-2):index] == [b"\x0a\x82", b"\x46\x02"],
            f"FORM_OPEN action {key:#06x} needs a callback flag and SUPPRESS_IF TRUE")


def check_timeout_pcd(raw):
    require(raw[:16] == PCD_SIGNATURE and read_int(raw, 16, 4) == 7,
            "unsupported PcdDxe database")
    db = span(raw, 0, read_int(raw, 20, 4), "DEFAULT PCD database")
    local, _, guids, strings = struct.unpack_from("<4I", span(db, 40, 16, "table offsets"))
    count = read_int(db, 68, 2)
    timeout = "Timeout\0".encode("utf-16-le")
    defaults = []
    for (token,) in struct.iter_unpack("<I", span(db, local, 4 * count, "token table")):
        if token >> 24 != 0x82:  # HII storage, UINT16 datum
            continue
        off = token & 0xffffff
        name, default, index, varoff = struct.unpack_from("<IIHH", span(db, off, 12, "HII head"))
        if (varoff == 0 and db[guids+16*index:guids+16*(index+1)] == EFI_GLOBAL and
                db.startswith(timeout, strings + name)):
            defaults.append(read_int(db, default, 2))
    seconds = only(defaults, "global UINT16 Timeout binding")
    require(seconds == 3, f"rhct13 factory boot timeout changed to {seconds} seconds")
    return seconds


def verify(fit, mode):
    fd, _, _ = read_edk2_fit(fit)
    wanted = {HII_DRIVER: 7, SNAPSHOT_DRIVER: 7, PCD_DXE: 7, BDS: 7, BROWSER: 7, UI_APP: 9}
    if mode == "acpi":
        wanted[ACPI_TABLES] = 2
    content = files(dxe_volume(fd), wanted)
    pe = {key: only(sections(content[key], 0x10), "PE32")
          for key in (HII_DRIVER, SNAPSHOT_DRIVER, BDS, BROWSER, UI_APP)}
    check_page(pe[HII_DRIVER], mode)
    # UiApp's BMM dynamically inserts the numeric editor between these labels.
    # A source reference to BMM's GUID also exists in its varstore and is
    # insufficient evidence that the actual destination form is packaged.
    for formset, main, expected in [(MANAGER_FORMSET, 0x1000, [0x1100, 0xffff]),
                                    (BOOT_MAINTENANCE, BMM_MAIN, [0xfffc, 0xfffd])]:
        ops = list(form_package(pe[UI_APP], formset))
        labels = [read_int(op, 19, 2) for form, code, op in ops
                  if form == main and code == 0x5f and op[2:19] == TIANO + b"\x00"]
        require(labels == expected, f"UiApp form {main:#06x} is missing its update labels")
        if formset == BOOT_MAINTENANCE:
            check_open_callback(ops, main, 0x1117)
    raw = only(sections(content[PCD_DXE], 0x19), "PcdDxe database")
    return {"mode": mode, "native_timeout_link": mode == "acpi",
            "timeout_default_seconds": check_timeout_pcd(raw)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fit", type=Path)
    parser.add_argument("--mode", choices=["acpi", "dt"], default="acpi")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.fit, args.mode), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
