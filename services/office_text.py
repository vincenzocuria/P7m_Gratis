"""Recognise Office documents and extract their plain text for the preview.

Word 97-2003 (.doc) is read from its Compound File (OLE2) container without
external libraries; .docx and .odt are read from their ZIP packages. Only text
is returned: layout, images and embedded objects are ignored.
"""
import re
import struct
import zipfile
from io import BytesIO
from typing import Dict, Optional, Tuple
from xml.etree import ElementTree as ET

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MAX_STREAM = 64 * 1024 * 1024
MAX_XML = 20 * 1024 * 1024
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE

OLE_TYPES = (
    ("WordDocument", "application/msword", ".doc"),
    ("Workbook", "application/vnd.ms-excel", ".xls"),
    ("Book", "application/vnd.ms-excel", ".xls"),
    ("PowerPoint Document", "application/vnd.ms-powerpoint", ".ppt"),
)
ODF_TYPES = {
    b"application/vnd.oasis.opendocument.text": ".odt",
    b"application/vnd.oasis.opendocument.spreadsheet": ".ods",
    b"application/vnd.oasis.opendocument.presentation": ".odp",
}


class CompoundFile:
    """Minimal read-only Compound File Binary (MS-CFB) reader."""

    def __init__(self, data: bytes):
        if len(data) < 512 or not data.startswith(OLE_MAGIC):
            raise ValueError("Non è un file OLE2")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
        if self.sector_size not in (512, 4096) or self.mini_size != 64:
            raise ValueError("Dimensione dei settori OLE2 non valida")
        (fat_count, dir_start) = struct.unpack_from("<II", data, 0x2C)
        (self.mini_cutoff, mini_fat_start, mini_fat_count,
         difat_start, difat_count) = struct.unpack_from("<IIIII", data, 0x38)
        fat_sectors = [s for s in struct.unpack_from("<109I", data, 0x4C) if s != FREESECT]
        sector = difat_start
        for _ in range(min(difat_count, 10000)):
            if sector in (FREESECT, ENDOFCHAIN):
                break
            values = struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(sector))
            fat_sectors.extend(v for v in values[:-1] if v != FREESECT)
            sector = values[-1]
        self.fat = []
        for s in fat_sectors[:fat_count]:
            self.fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(s)))
        self.entries = self._directory(self._chain(dir_start, self.fat, self.sector_size, self._sector))
        root = self.entries.get("Root Entry")
        self.mini_stream = (self._chain(root[0], self.fat, self.sector_size, self._sector)[:root[1]]
                            if root else b"")
        mini_fat_bytes = self._chain(mini_fat_start, self.fat, self.sector_size, self._sector) if mini_fat_count else b""
        self.mini_fat = list(struct.unpack_from(f"<{len(mini_fat_bytes) // 4}I", mini_fat_bytes))

    def _sector(self, index: int) -> bytes:
        start = (index + 1) * self.sector_size
        if start + self.sector_size > len(self.data):
            raise ValueError("Settore OLE2 fuori dal file")
        return self.data[start:start + self.sector_size]

    def _mini_sector(self, index: int) -> bytes:
        start = index * self.mini_size
        if start + self.mini_size > len(self.mini_stream):
            raise ValueError("Mini settore OLE2 fuori dallo stream")
        return self.mini_stream[start:start + self.mini_size]

    @staticmethod
    def _chain(start: int, table, size: int, read) -> bytes:
        out, seen, sector = [], set(), start
        while sector not in (ENDOFCHAIN, FREESECT):
            if sector in seen or sector >= len(table) or len(out) * size > MAX_STREAM:
                raise ValueError("Catena OLE2 non valida")
            seen.add(sector)
            out.append(read(sector))
            sector = table[sector]
        return b"".join(out)

    @staticmethod
    def _directory(raw: bytes) -> Dict[str, Tuple[int, int]]:
        entries = {}
        for offset in range(0, len(raw) - 127, 128):
            name_len = struct.unpack_from("<H", raw, offset + 64)[0]
            kind = raw[offset + 66]
            if kind not in (1, 2, 5) or not 2 <= name_len <= 64:
                continue
            name = raw[offset:offset + name_len - 2].decode("utf-16-le", errors="replace")
            start, size = struct.unpack_from("<IQ", raw, offset + 116)
            entries.setdefault(name, (start, size))
        return entries

    def stream(self, name: str) -> bytes:
        if name not in self.entries:
            raise KeyError(name)
        start, size = self.entries[name]
        if size > MAX_STREAM:
            raise ValueError("Stream OLE2 troppo grande")
        if size < self.mini_cutoff and name != "Root Entry":
            return self._chain(start, self.mini_fat, self.mini_size, self._mini_sector)[:size]
        return self._chain(start, self.fat, self.sector_size, self._sector)[:size]


def detect_office_type(payload: bytes) -> Optional[Tuple[str, str]]:
    """MIME type and extension of OLE2 or OpenDocument payloads, else None."""
    if payload.startswith(OLE_MAGIC):
        try:
            names = CompoundFile(payload).entries
        except Exception:
            names = {}
        for stream, mime, ext in OLE_TYPES:
            if stream in names:
                return mime, ext
        return "application/x-ole-storage", ".ole"
    if payload.startswith(b"PK\x03\x04") and payload[30:38] == b"mimetype":
        for mime, ext in ODF_TYPES.items():
            if payload[38:38 + len(mime)] == mime:
                return mime.decode(), ext
    if payload.startswith(b"{\\rtf"):
        return "application/rtf", ".rtf"
    return None


def _clean_word_text(text: str) -> str:
    # Fields: keep the displayed result, drop the instruction (0x13 instr 0x14 result 0x15).
    out, stack = [], []
    for ch in text:
        if ch == "\x13":
            stack.append(True)
        elif ch == "\x14" and stack:
            stack[-1] = False
        elif ch == "\x15" and stack:
            stack.pop()
        elif not (stack and stack[-1]):
            out.append(ch)
    text = "".join(out)
    text = text.replace("\r\x07", "\n").replace("\x07", "\t")
    text = text.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n\n")
    text = re.sub(r"[\x00-\x08\x0e-\x1f\x01]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def word97_text(payload: bytes) -> str:
    """Main document text of a Word 97-2003 file, via the piece table (CLX)."""
    ole = CompoundFile(payload)
    word = ole.stream("WordDocument")
    if len(word) < 0x1AA or struct.unpack_from("<H", word, 0)[0] != 0xA5EC:
        raise ValueError("Documento Word non riconosciuto")
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    if flags & 0x0100:
        raise ValueError("Documento Word cifrato")
    table = ole.stream("1Table" if flags & 0x0200 else "0Table")
    ccp_text = struct.unpack_from("<i", word, 0x4C)[0]
    fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x1A2)
    clx = table[fc_clx:fc_clx + lcb_clx]
    pos = 0
    while pos < len(clx) and clx[pos] == 0x01:  # skip Prc (property modifiers)
        size = struct.unpack_from("<h", clx, pos + 1)[0]
        if size < 0:
            raise ValueError("Tabella dei pezzi non valida")
        pos += 3 + size
    if pos >= len(clx) or clx[pos] != 0x02:
        raise ValueError("Tabella dei pezzi assente")
    lcb = struct.unpack_from("<I", clx, pos + 1)[0]
    plc = clx[pos + 5:pos + 5 + lcb]
    count = (len(plc) - 4) // 12
    cps = struct.unpack_from(f"<{count + 1}I", plc, 0)
    parts, total = [], 0
    for i in range(count):
        if total >= ccp_text > 0:
            break
        fc = struct.unpack_from("<I", plc, (count + 1) * 4 + i * 8 + 2)[0]
        length = cps[i + 1] - cps[i]
        if length <= 0 or length > MAX_STREAM:
            continue
        if fc & 0x40000000:
            start = (fc & 0x3FFFFFFF) // 2
            parts.append(word[start:start + length].decode("cp1252", errors="replace"))
        else:
            parts.append(word[fc:fc + 2 * length].decode("utf-16-le", errors="replace"))
        total += length
    text = "".join(parts)
    if ccp_text > 0:
        text = text[:ccp_text]
    return _clean_word_text(text)


def _zip_xml(payload: bytes, name: str) -> ET.Element:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        info = archive.getinfo(name)
        if info.file_size > MAX_XML:
            raise ValueError("Documento troppo grande per l'anteprima")
        return ET.fromstring(archive.read(info))


def docx_text(payload: bytes) -> str:
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = _zip_xml(payload, "word/document.xml")
    lines = []
    for paragraph in root.iter(f"{w}p"):
        line = []
        for node in paragraph.iter():
            if node.tag == f"{w}t":
                line.append(node.text or "")
            elif node.tag == f"{w}tab":
                line.append("\t")
            elif node.tag in (f"{w}br", f"{w}cr"):
                line.append("\n")
        lines.append("".join(line))
    return "\n".join(lines).strip()


def odt_text(payload: bytes) -> str:
    t = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    root = _zip_xml(payload, "content.xml")

    def walk(element) -> str:
        out = [element.text or ""]
        for child in element:
            if child.tag == f"{t}tab":
                out.append("\t")
            elif child.tag == f"{t}line-break":
                out.append("\n")
            elif child.tag == f"{t}s":
                out.append(" " * max(1, min(100, int(child.get(f"{t}c", "1") or 1))))
            else:
                out.append(walk(child))
            out.append(child.tail or "")
        return "".join(out)

    blocks = [walk(e) for e in root.iter() if e.tag in (f"{t}p", f"{t}h")]
    return "\n".join(blocks).strip()


def extract_text(payload: bytes, ext: str) -> Optional[str]:
    """Plain text for .doc, .docx and .odt; None when unsupported or unreadable."""
    try:
        if ext == ".doc":
            text = word97_text(payload)
        elif ext == ".docx":
            text = docx_text(payload)
        elif ext == ".odt":
            text = odt_text(payload)
        else:
            return None
    except Exception:
        return None
    return text or None
