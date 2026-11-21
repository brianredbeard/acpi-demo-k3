#!/usr/bin/env python3
"""Validate captured pre-install tables; no runtime checksum claim.

Run: python3 docs/audit-2026-11-20/fixed_tables.py
"""
from pathlib import Path
import hashlib
import struct

ROOT = Path(__file__).parent / "evidence/fixed-tables"


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def nodes(b, start):
    result = []
    while start < len(b):
        assert start + 2 <= len(b), "truncated node header"
        kind, size = b[start:start + 2]
        assert size >= 2 and start + size <= len(b), "invalid node length"
        result.append((start, kind, b[start:start + size]))
        start += size
    assert start == len(b)
    return result


def validate_madt(b):
    ns = nodes(b, 44)
    assert [t for _, t, _ in ns] == [24] * 8 + [25, 26]
    assert b[36:44] == bytes(8)
    for h, (_, _, n) in enumerate(ns[:8]):
        assert len(n) == 36 and n[2] == 1 and n[3] == 0
        assert u32(n, 4) == 1
        assert struct.unpack_from("<Q", n, 8)[0] == h
        assert u32(n, 16) == h and u32(n, 20) == 0
        assert struct.unpack_from("<Q", n, 24)[0] == 0xe0400000 + h * 0x40000
        assert u32(n, 32) == 0x40000
    n = ns[8][2]
    assert len(n) == 16 and n[2:8] == b"\x01" + bytes(5)
    assert struct.unpack_from("<HHBBBB", n, 8) == (511, 63, 6, 4, 0, 24)
    n = ns[9][2]
    assert len(n) == 36 and n[2:8] == b"\x01" + bytes(5)
    assert n[8:16] == b"SPMT0001" and struct.unpack_from("<HHI", n, 16) == (0, 512, 0)
    assert struct.unpack_from("<QI", n, 24) == (0xe0804000, 0x4000)


def main():
    tables = {}
    for name, sig in [('Madt', b'APIC'), ('Mcfg', b'MCFG'), ('Rhct', b'RHCT'),
                      ('Pptt', b'PPTT'), ('Fadt', b'FACP'), ('Spcr', b'SPCR')]:
        raw = (ROOT / (name + '.acpi')).read_bytes()
        assert raw[:4] == sig and 36 <= u32(raw, 4) <= len(raw)
        b = raw[:u32(raw, 4)]
        assert b[9] == 0, 'expected pre-install checksum initializer'
        tables[name] = b
        print(name, len(b), 'revision', b[8], 'sha256', hashlib.sha256(b).hexdigest())
    validate_madt(tables['Madt'])
    b = tables['Mcfg']
    assert len(b) == 60 and b[36:44] == bytes(8)
    assert struct.unpack_from('<QHBBI', b, 44) == (0x1100000000, 0, 0, 255, 0)
    b = tables['Rhct']
    count, pos = struct.unpack_from('<II', b, 48)
    assert count == 11 and pos == 56
    starts, refs, uids = set(), [], []
    for _ in range(count):
        starts.add(pos)
        kind, size, rev = struct.unpack_from('<HHH', b, pos)
        assert size >= 6 and pos + size <= len(b) and rev == 1
        if kind == 65535:
            assert size == 24 and struct.unpack_from('<H', b, pos + 6)[0] == 3
            uids.append(u32(b, pos + 8))
            refs.extend(struct.unpack_from('<III', b, pos + 12))
        pos += size
    assert pos == len(b) and uids == list(range(8)) and set(refs) <= starts
    b = tables['Pptt']
    ns = nodes(b, 36)
    starts = {o for o, _, _ in ns}
    uids = []
    for _, kind, n in ns:
        assert n[2:4] == bytes(2)
        if kind == 0:
            flags, parent, uid, count = struct.unpack_from('<IIII', n, 4)
            assert len(n) == 20 + 4 * count and (parent == 0 or parent in starts)
            assert all(u32(n, 20 + 4 * i) in starts for i in range(count))
            if flags & 8:
                uids.append(uid)
    assert uids == list(range(8))
    for offset, value in [(45, 0), (45, 255), (340, 0)]:
        bad = bytearray(tables['Madt']); bad[offset] = value
        try:
            validate_madt(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError('negative MADT mutation unexpectedly accepted')
    print('PASS: structure, topology, references, reserved fields sampled; 3 negative mutations rejected.')
    print('Runtime checksum/install path and hardware behavior NOT tested.')


if __name__ == '__main__':
    main()
