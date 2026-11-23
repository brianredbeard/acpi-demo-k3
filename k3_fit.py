"""Read the external-data K3 EDK2 FIT and compare its complete payload set."""
import hashlib
from pathlib import Path
import struct
import subprocess
import zlib


def _header(blob):
    """Index property locations in an FDT v17 header (excluding external data)."""
    if len(blob) < 40:
        raise ValueError('truncated FIT')
    magic, total, pos, strings, _, version, _, _, names_len, tree_len = struct.unpack_from('>10I', blob)
    end = pos + tree_len
    if (magic != 0xd00dfeed or version != 17 or total > len(blob) or
            pos < 40 or end > total or strings < 40 or strings + names_len > total):
        raise ValueError('invalid FIT header')
    names = blob[strings:strings + names_len]
    nodes = {}
    stack = []
    while pos + 4 <= end:
        token, = struct.unpack_from('>I', blob, pos)
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            nul = blob.find(b'\0', pos, end)
            if nul < 0:
                break
            name = blob[pos:nul].decode('ascii')
            if '/' in name or bool(stack) != bool(name):
                raise ValueError('invalid FIT node name')
            path = '/'.join(stack + [name])
            if path in nodes:
                raise ValueError(f'duplicate FIT node: {path}')
            nodes[path] = {}
            stack.append(name)
            pos = (nul + 4) & ~3
        elif token == 2 and stack:  # FDT_END_NODE
            stack.pop()
        elif token == 3 and stack and pos + 8 <= end:  # FDT_PROP
            size, offset = struct.unpack_from('>II', blob, pos)
            pos += 8
            nul = names.find(b'\0', offset)
            if pos + size > end or nul < 0:
                break
            key = names[offset:nul].decode('ascii')
            props = nodes['/'.join(stack)]
            if key in props:
                raise ValueError(f'duplicate FIT property: {key}')
            props[key] = slice(pos, pos + size)
            pos = (pos + size + 3) & ~3
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9 and not stack:
            return total, nodes
        else:
            break
    raise ValueError('malformed FIT structure')


def read_edk2_fit(path):
    """Return the selected FD bytes, hashes of *all* image nodes, and identity metadata."""
    blob = Path(path).read_bytes()
    total, nodes = _header(blob)

    def prop(node, key):
        try:
            return blob[nodes[node][key]]
        except KeyError as exc:
            raise ValueError(f'missing FIT property {node}/{key}') from exc

    def string(node, key):
        raw = prop(node, key)
        if not raw.endswith(b'\0') or b'\0' in raw[:-1]:
            raise ValueError(f'invalid FIT string {node}/{key}')
        return raw[:-1].decode('ascii')

    def cell(node, key):
        raw = prop(node, key)
        if len(raw) != 4:
            raise ValueError(f'invalid FIT cell {node}/{key}')
        return int.from_bytes(raw, 'big')

    def children(node):
        return [key for key in nodes if key.rpartition('/')[0] == node and key]

    cfg_name = string('/configurations', 'default')
    cfg = '/configurations/' + cfg_name
    if cfg not in children('/configurations') or string(cfg, 'description') != 'k3-pico-itx':
        raise ValueError('default configuration must select the Pico-ITX')
    if set(nodes[cfg]) - {'description', 'loadables', 'fdt'} or string(cfg, 'loadables') != 'uefi':
        raise ValueError('unsupported Pico FIT boot selection')
    fdt = string(cfg, 'fdt')
    if '/images/' + fdt not in children('/images') or fdt == 'uefi':
        raise ValueError('missing Pico DTB')
    if (string('/images/uefi', 'arch') != 'riscv' or string('/images/uefi', 'type') != 'standalone'
            or prop('/images/uefi', 'load') != struct.pack('>Q', 0x102000000)):
        raise ValueError('unsupported EDK2 image or load address')

    # Mask only the bytes expected to vary in a same-layout FD replacement.
    # This fingerprint includes config selection, metadata and padding in the FIT.
    unchanged = bytearray(blob)
    if 'timestamp' in nodes['']:
        cell('', 'timestamp')
        unchanged[nodes['']['timestamp']] = bytes(4)
    hashes = {}
    payloads = {}
    ranges = []
    for image in children('/images'):
        name = image.rsplit('/', 1)[1]
        if string(image, 'compression') != 'none':
            raise ValueError(f'{name}: unsupported compression')
        if {'data', 'data-position'} & nodes[image].keys():
            raise ValueError(f'{name}: expected external data-offset layout')
        start = ((total + 3) & ~3) + cell(image, 'data-offset')
        size = cell(image, 'data-size')
        stop = start + size
        if size == 0 or stop > len(blob) or any(start < b and a < stop for a, b in ranges):
            raise ValueError(f'{name}: invalid or overlapping FIT data range')
        ranges.append((start, stop))
        payload = blob[start:stop]
        payloads[name] = payload
        hashes[name] = hashlib.sha256(payload).hexdigest()
        if name == 'uefi':
            unchanged[start:stop] = bytes(size)
        elif string(image, 'type') != 'flat_dt' or not children(image):
            raise ValueError(f'{name}: expected DTB with checksum')
        for child in children(image):
            if string(child, 'algo') != 'crc32' or cell(child, 'value') != zlib.crc32(payload):
                raise ValueError(f'{name}: invalid FIT checksum')
            if name == 'uefi':
                unchanged[nodes[child]['value']] = bytes(4)

    model = subprocess.run(['fdtget', '/dev/stdin', '/', 'model'], input=payloads[fdt],
                           capture_output=True)
    if model.returncode or model.stdout.rstrip(b'\n') != b'SpacemiT K3 Pico ITX':
        raise ValueError(f'{fdt}: selected DTB does not identify the Pico ITX')
    return payloads['uefi'], hashes, {
        'configuration': cfg_name, 'dtb': fdt,
        'unchanged_sha256': hashlib.sha256(unchanged).hexdigest(),
    }


def compare_edk2_fits(baseline, candidate, fd_sha256):
    _, before, old_layout = read_edk2_fit(baseline)
    _, after, new_layout = read_edk2_fit(candidate)
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    if changed != ['uefi']:
        raise ValueError(f'expected only uefi to change; changed FIT images: {changed}')
    if after['uefi'] != fd_sha256:
        raise ValueError('packaged UEFI FD differs from build manifest')
    if old_layout != new_layout:
        raise ValueError('unexpected changes to EDK2 FIT layout, configuration, or padding')
    return after
