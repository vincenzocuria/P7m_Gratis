"""Synthetic Word 97-2003 (.doc, Compound File) fixtures for the text preview.

The Compound File builder mirrors test_office_documents.py at the repository root.
"""
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

out = Path(__file__).resolve().parents[1] / 'test' / 'fixtures'
END, FREE, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFF


def compound_file(streams):
    """Version 3 Compound File; streams under 4096 bytes go in the mini stream."""
    big = {n: d for n, d in streams.items() if len(d) >= 4096}
    small = {n: d for n, d in streams.items() if len(d) < 4096}
    mini, mini_fat, mini_start = b'', [], {}
    for name, data in small.items():
        count = max(1, -(-len(data) // 64))
        mini_start[name] = len(mini) // 64
        mini_fat += [mini_start[name] + i + 1 for i in range(count - 1)] + [END]
        mini += data.ljust(count * 64, b'\0')
    names = list(streams)
    sectors_of = lambda data: max(1, -(-len(data) // 512))
    dir_count = sectors_of(b'\0' * 128 * (len(names) + 1))
    mf_bytes = struct.pack(f'<{len(mini_fat)}I', *mini_fat) if mini_fat else b''
    mf_count = sectors_of(mf_bytes) if mini_fat else 0
    ms_count = sectors_of(mini) if mini else 0
    body = dir_count + mf_count + ms_count + sum(sectors_of(d) for d in big.values())
    fat_count = 1
    while fat_count * 128 < fat_count + body:
        fat_count += 1
    fat, layout, next_sector = [0xFFFFFFFD] * fat_count, {}, fat_count

    def allocate(key, count):
        nonlocal next_sector
        layout[key] = next_sector
        fat.extend([next_sector + i + 1 for i in range(count - 1)] + [END])
        next_sector += count

    allocate('dir', dir_count)
    if mf_count:
        allocate('minifat', mf_count)
    if ms_count:
        allocate('ministream', ms_count)
    for name, data in big.items():
        allocate(name, sectors_of(data))

    def entry(name, kind, start, size, right=NOSTREAM, child=NOSTREAM):
        encoded = (name + '\0').encode('utf-16-le')
        return (encoded.ljust(64, b'\0') + struct.pack('<HBB', len(encoded), kind, 1)
                + struct.pack('<III', NOSTREAM, right, child) + b'\0' * 36
                + struct.pack('<IQ', start, size))

    directory = entry('Root Entry', 5, layout.get('ministream', END), len(mini), child=1)
    for i, name in enumerate(names):
        start = layout[name] if name in big else mini_start[name]
        right = i + 2 if i + 1 < len(names) else NOSTREAM
        directory += entry(name, 2, start, len(streams[name]), right=right)
    fat += [FREE] * (fat_count * 128 - len(fat))
    difat = list(range(fat_count)) + [FREE] * (109 - fat_count)
    header = (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\0' * 16
              + struct.pack('<HHHHH', 0x3E, 3, 0xFFFE, 9, 6) + b'\0' * 6
              + struct.pack('<IIIIIIIII', 0, fat_count, layout['dir'], 0, 4096,
                            layout.get('minifat', END), mf_count, END, 0)
              + struct.pack('<109I', *difat))
    data = header + struct.pack(f'<{len(fat)}I', *fat)
    data += directory.ljust(dir_count * 512, b'\0')
    if mf_count:
        data += mf_bytes.ljust(mf_count * 512, b'\xff')
    if ms_count:
        data += mini.ljust(ms_count * 512, b'\0')
    for name, data_big in big.items():
        data += data_big.ljust(sectors_of(data_big) * 512, b'\0')
    return data


def word97(flags=0x0200):
    """A cp1252 piece, a UTF-16 piece with a field, then text past ccpText (footnotes)."""
    first = 'Comune di prova – è\r'
    second = 'Campo: \x13 PAGE \x141\x15 fine €\r'
    hidden = 'NOTA A PIE DI PAGINA\r'
    word = bytearray(8192)  # main stream in the FAT, table stream in the mini stream
    struct.pack_into('<H', word, 0, 0xA5EC)
    struct.pack_into('<H', word, 0x0A, flags)
    struct.pack_into('<i', word, 0x4C, len(first) + len(second))
    word[0x800:0x800 + len(first)] = first.encode('cp1252')
    word[0x900:0x900 + 2 * len(second)] = second.encode('utf-16-le')
    word[0xA00:0xA00 + len(hidden)] = hidden.encode('cp1252')
    cps = [0, len(first), len(first) + len(second), len(first) + len(second) + len(hidden)]
    fcs = [(0x800 * 2) | 0x40000000, 0x900, (0xA00 * 2) | 0x40000000]
    plc = struct.pack('<4I', *cps) + b''.join(struct.pack('<HIH', 0, fc, 0) for fc in fcs)
    clx = b'\x01' + struct.pack('<h', 2) + b'\0\0' + b'\x02' + struct.pack('<I', len(plc)) + plc
    struct.pack_into('<II', word, 0x1A2, 16, len(clx))
    return compound_file({'WordDocument': bytes(word), '1Table': b'\0' * 16 + clx})


def signed(data):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Firmatario Word 97')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(97)
            .not_valid_before(now - timedelta(days=100)).not_valid_after(now + timedelta(days=100))
            .sign(key, hashes.SHA256()))
    return (pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256())
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]))


doc = word97()
out.joinpath('sample.doc').write_bytes(doc)
out.joinpath('sample.doc.p7m').write_bytes(signed(doc))
out.joinpath('word97.p7m').write_bytes(signed(doc))  # payload without extension
out.joinpath('encrypted.doc').write_bytes(word97(flags=0x0300))
print('fixtures ok')
