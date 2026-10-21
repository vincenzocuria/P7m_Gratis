import io
import os
import struct
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from p7m_decoder import P7MDecoder
from services.office_text import detect_office_type, extract_text

END, FREE, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFF


def compound_file(streams):
    """Build a version 3 Compound File; streams under 4096 bytes go in the mini stream."""
    big = {n: d for n, d in streams.items() if len(d) >= 4096}
    small = {n: d for n, d in streams.items() if len(d) < 4096}
    mini, mini_fat, mini_start = b"", [], {}
    for name, data in small.items():
        count = max(1, -(-len(data) // 64))
        mini_start[name] = len(mini) // 64
        mini_fat += [mini_start[name] + i + 1 for i in range(count - 1)] + [END]
        mini += data.ljust(count * 64, b"\0")
    names = list(streams)
    directory = b""
    sectors_of = lambda data: max(1, -(-len(data) // 512))
    dir_count = sectors_of(b"\0" * 128 * (len(names) + 1))
    mf_bytes = struct.pack(f"<{len(mini_fat)}I", *mini_fat) if mini_fat else b""
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

    allocate("dir", dir_count)
    if mf_count:
        allocate("minifat", mf_count)
    if ms_count:
        allocate("ministream", ms_count)
    for name, data in big.items():
        allocate(name, sectors_of(data))

    def entry(name, kind, start, size, right=NOSTREAM, child=NOSTREAM):
        encoded = (name + "\0").encode("utf-16-le")
        return (encoded.ljust(64, b"\0") + struct.pack("<HBB", len(encoded), kind, 1)
                + struct.pack("<III", NOSTREAM, right, child) + b"\0" * 36
                + struct.pack("<IQ", start, size))

    directory += entry("Root Entry", 5, layout.get("ministream", END), len(mini), child=1)
    for i, name in enumerate(names):
        start = layout[name] if name in big else mini_start[name]
        right = i + 2 if i + 1 < len(names) else NOSTREAM
        directory += entry(name, 2, start, len(streams[name]), right=right)
    fat += [FREE] * (fat_count * 128 - len(fat))
    difat = list(range(fat_count)) + [FREE] * (109 - fat_count)
    header = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 16
              + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\0" * 6
              + struct.pack("<IIIIIIIII", 0, fat_count, layout["dir"], 0, 4096,
                            layout.get("minifat", END), mf_count, END, 0)
              + struct.pack("<109I", *difat))
    out = header + struct.pack(f"<{len(fat)}I", *fat)
    out += directory.ljust(dir_count * 512, b"\0")
    if mf_count:
        out += mf_bytes.ljust(mf_count * 512, b"\xff")
    if ms_count:
        out += mini.ljust(ms_count * 512, b"\0")
    for name, data in big.items():
        out += data.ljust(sectors_of(data) * 512, b"\0")
    return out


def word97(flags=0x0200, prc_size=2):
    """Word 97 document: a cp1252 piece, a UTF-16 piece with a field, then hidden text."""
    first = "Comune di prova – è\r"
    second = "Campo: \x13 PAGE \x141\x15 fine €\r"
    hidden = "NOTA A PIE DI PAGINA\r"
    word = bytearray(8192)
    struct.pack_into("<H", word, 0, 0xA5EC)
    struct.pack_into("<H", word, 0x0A, flags)
    struct.pack_into("<i", word, 0x4C, len(first) + len(second))
    word[0x800:0x800 + len(first)] = first.encode("cp1252")
    word[0x900:0x900 + 2 * len(second)] = second.encode("utf-16-le")
    word[0xA00:0xA00 + len(hidden)] = hidden.encode("cp1252")
    cps = [0, len(first), len(first) + len(second), len(first) + len(second) + len(hidden)]
    fcs = [(0x800 * 2) | 0x40000000, 0x900, (0xA00 * 2) | 0x40000000]
    plc = struct.pack("<4I", *cps) + b"".join(struct.pack("<HIH", 0, fc, 0) for fc in fcs)
    clx = b"\x01" + struct.pack("<h", prc_size) + b"\0\0" + b"\x02" + struct.pack("<I", len(plc)) + plc
    table = b"\0" * 16 + clx
    struct.pack_into("<II", word, 0x1A2, 16, len(clx))
    return compound_file({"WordDocument": bytes(word), "1Table": table})


def signed(data):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MARIO ROSSI")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(7)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return (pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256())
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]))


EXPECTED = "Comune di prova – è\nCampo: 1 fine €"


class OfficeDocumentTests(unittest.TestCase):
    def test_word97_text_uses_piece_table_and_mini_stream(self):
        doc = word97()
        self.assertEqual(detect_office_type(doc), ("application/msword", ".doc"))
        self.assertEqual(extract_text(doc, ".doc"), EXPECTED)

    def test_missing_table_stream_gives_no_preview(self):
        # The FIB points to 0Table but the file only has 1Table.
        self.assertIsNone(extract_text(word97(flags=0), ".doc"))

    def test_encrypted_or_damaged_word97_has_no_preview(self):
        self.assertIsNone(extract_text(word97(flags=0x0300), ".doc"))
        damaged = bytearray(word97())
        damaged[0x30:0x34] = b"\xff\xff\xff\x7f"
        self.assertIsNone(extract_text(bytes(damaged), ".doc"))

    def test_negative_prc_size_gives_no_preview_without_hanging(self):
        # A negative Prc size would make the CLX scan stand still or go back forever.
        result = []
        worker = threading.Thread(
            target=lambda: result.append(extract_text(word97(prc_size=-3), ".doc")), daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "word97_text non termina con un Prc negativo")
        self.assertEqual(result, [None])

    def test_p7m_with_doc_keeps_extension_and_verifies(self):
        envelope = signed(word97())
        for filename, expected in [("atto.doc.p7m", "atto.doc"), ("atto.p7m", "atto.doc")]:
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, filename)
                with open(path, "wb") as handle:
                    handle.write(envelope)
                res = P7MDecoder.decode_file(path)
            self.assertTrue(res["success"], res.get("error"))
            self.assertEqual(res["mime_type"], "application/msword")
            self.assertEqual(res["ext"], ".doc")
            self.assertEqual(res["suggested_filename"], expected)
            self.assertEqual(extract_text(res["payload"], res["ext"]), EXPECTED)

    def test_other_ole_and_open_document_types(self):
        xls = compound_file({"Workbook": b"\0" * 5000})
        self.assertEqual(detect_office_type(xls), ("application/vnd.ms-excel", ".xls"))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
            z.writestr("content.xml",
                       '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                       '<text:h>Titolo</text:h><text:p>Uno<text:s text:c="2"/>due<text:tab/>tre</text:p>'
                       '</office:text></office:body></office:document-content>')
        odt = buffer.getvalue()
        self.assertEqual(detect_office_type(odt), ("application/vnd.oasis.opendocument.text", ".odt"))
        self.assertEqual(extract_text(odt, ".odt"), "Titolo\nUno  due\ttre")
        self.assertEqual(detect_office_type(b"{\\rtf1 ciao}"), ("application/rtf", ".rtf"))

    def test_docx_text(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("word/document.xml",
                       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       '<w:body><w:p><w:r><w:t>Primo</w:t></w:r><w:r><w:tab/><w:t>paragrafo</w:t></w:r></w:p>'
                       '<w:p><w:r><w:t>Secondo</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(extract_text(buffer.getvalue(), ".docx"), "Primo\tparagrafo\nSecondo")

    def test_arbitrary_bytes_are_not_office(self):
        self.assertIsNone(detect_office_type(b"\xd0\xcf\x11\xe0" + b"\0" * 10))
        self.assertIsNone(extract_text(b"testo qualsiasi", ".doc"))


if __name__ == "__main__":
    unittest.main()
