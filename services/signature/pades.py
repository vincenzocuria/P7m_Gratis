"""PAdES signatures embedded in a PDF, verified as detached CMS over the ByteRange."""
import re
from typing import Dict, List, Optional

SUPPORTED_SUBFILTERS = {"adbe.pkcs7.detached", "ETSI.CAdES.detached"}


def _der_length(data: bytes) -> int:
    if len(data) < 2 or data[0] != 0x30:
        raise ValueError("CMS DER non riconosciuto")
    length = data[1]
    if length < 0x80:
        total = 2 + length
    else:
        count = length & 0x7F
        if count == 0 or count > 4 or len(data) < 2 + count:
            raise ValueError("Lunghezza CMS non valida")
        total = 2 + count + int.from_bytes(data[2:2 + count], "big")
    if total > len(data):
        raise ValueError("CMS troncato")
    return total


def _cms_from_contents(gap: bytes) -> bytes:
    compact = re.sub(rb"\s+", b"", gap)
    if len(compact) < 4 or compact[:1] != b"<" or compact[-1:] != b">":
        raise ValueError("Contenuto della firma assente")
    hex_body = compact[1:-1]
    if not hex_body or len(hex_body) % 2 or not re.fullmatch(rb"[0-9A-Fa-f]+", hex_body):
        raise ValueError("Contenuto della firma non esadecimale")
    padded = bytes.fromhex(hex_body.decode("ascii"))
    return padded[:_der_length(padded)]


def _subfilter(window: bytes) -> Optional[str]:
    match = re.search(rb"/SubFilter\s*/([A-Za-z0-9_.]+)", window)
    if not match:
        return None
    return match.group(1).decode("ascii", "replace")


def extract_pades_signatures(pdf: bytes) -> List[Dict]:
    """Return every signature whose ByteRange points at a hexadecimal Contents value."""
    if not pdf.startswith(b"%PDF-"):
        return []
    found = []
    pattern = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
    for match in pattern.finditer(pdf):
        start, length, start2, length2 = (int(item) for item in match.groups())
        if min(start, length, start2, length2) < 0:
            continue
        if start + length > start2 or start2 + length2 > len(pdf):
            continue
        gap = pdf[start + length:start2]
        try:
            cms_der = _cms_from_contents(gap)
        except ValueError:
            continue
        window_start = max(0, start + length - 8000)
        window_end = min(len(pdf), start2 + length2)
        subfilter = _subfilter(pdf[window_start:window_end])
        covers = start == 0 and start2 + length2 == len(pdf)
        supported = subfilter in SUPPORTED_SUBFILTERS
        if subfilter is None:
            error = "SubFilter della firma PDF assente"
        elif not supported:
            error = f"SubFilter non supportato: {subfilter}"
        elif not covers:
            error = "Il ByteRange non copre l'intero PDF"
        else:
            error = None
        found.append({
            "cms": cms_der,
            "signed_bytes": pdf[start:start + length] + pdf[start2:start2 + length2],
            "covers_document": covers,
            "subfilter": subfilter,
            "supported": supported,
            "error": error,
        })
    return found
