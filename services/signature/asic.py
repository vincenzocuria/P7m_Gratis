"""ASiC-S and ASiC-E containers holding a detached CAdES or XAdES signature."""
import base64
import hashlib
import io
import os
import zipfile
from typing import Dict, List, Optional

from lxml import etree

MAX_ENTRIES = 64
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024

DIGESTS = {
    "http://www.w3.org/2000/09/xmldsig#sha1": "sha1",
    "http://www.w3.org/2001/04/xmlenc#sha256": "sha256",
    "http://www.w3.org/2001/04/xmldsig-more#sha384": "sha384",
    "http://www.w3.org/2001/04/xmlenc#sha512": "sha512",
}


def _safe_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re_drive(normalized) or any(part == ".." for part in normalized.split("/")):
        raise ValueError("Percorso non consentito nel contenitore ASiC")
    return normalized


def re_drive(name: str) -> bool:
    return len(name) > 1 and name[1] == ":"


def _read_zip(data: bytes) -> Optional[Dict[str, bytes]]:
    if not data.startswith(b"PK"):
        return None
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    names = archive.namelist()
    if len(names) > MAX_ENTRIES:
        raise ValueError("Contenitore ASiC con troppi file")
    files = {}
    total = 0
    for info in archive.infolist():
        name = _safe_name(info.filename)
        if name.endswith("/"):
            continue
        if info.file_size > MAX_MEMBER:
            raise ValueError("File del contenitore ASiC troppo grande")
        total += info.file_size
        if total > MAX_TOTAL:
            raise ValueError("Contenitore ASiC troppo grande")
        files[name] = archive.read(info)
    return files


def _is_asic(files: Dict[str, bytes]) -> bool:
    mimetype = files.get("mimetype", b"").decode("ascii", "replace")
    if "application/vnd.etsi.asic-" in mimetype:
        return True
    for name in files:
        upper = name.upper()
        if upper.startswith("META-INF/") and (name.lower().endswith(".p7s") or "signature" in name.lower()):
            return True
    return False


def _basename(name: str) -> str:
    return name.replace("\\", "/").split("/")[-1]


def _find(files: Dict[str, bytes], uri: str) -> Optional[bytes]:
    candidates = [uri, uri.lstrip("./"), _basename(uri)]
    for candidate in candidates:
        if candidate in files:
            return files[candidate]
    for name, content in files.items():
        if _basename(name) == _basename(uri):
            return content
    return None


def manifest_digest_error(manifest: bytes, files: Dict[str, bytes]) -> Optional[str]:
    try:
        root = etree.fromstring(manifest)
    except etree.XMLSyntaxError as exc:
        return f"Manifest ASiC illeggibile: {exc}"
    checked = 0
    for element in root.iter():
        if etree.QName(element).localname != "DataObjectReference":
            continue
        uri = element.get("URI")
        method = next((child for child in element.iter() if etree.QName(child).localname == "DigestMethod"), None)
        value = next((child for child in element.iter() if etree.QName(child).localname == "DigestValue"), None)
        algorithm = DIGESTS.get(method.get("Algorithm") if method is not None else None)
        if not uri or algorithm is None or value is None:
            return "Riferimento del manifest ASiC non supportato"
        content = _find(files, uri)
        if content is None:
            return f"File del manifest assente: {uri}"
        expected = base64.b64decode("".join(value.itertext()).strip())
        if hashlib.new(algorithm, content).digest() != expected:
            return f"Impronta diversa per {uri}"
        checked += 1
    if checked == 0:
        return "Manifest ASiC senza file di dati"
    return None


def inspect_asic(data: bytes) -> Optional[Dict]:
    """Return the container parts, or None when the bytes are not an ASiC package."""
    files = _read_zip(data)
    if files is None or not _is_asic(files):
        return None
    data_files = [name for name in files if name != "mimetype" and not name.upper().startswith("META-INF/")]
    cades = [name for name in files if name.upper().startswith("META-INF/") and name.lower().endswith(".p7s")]
    manifests = [name for name in files if name.upper().startswith("META-INF/") and "asicmanifest" in name.lower()]
    xades = [
        name for name in files
        if name.upper().startswith("META-INF/") and name.lower().endswith(".xml")
        and "signature" in name.lower() and "manifest" not in name.lower()
    ]
    mimetype = files.get("mimetype", b"").decode("ascii", "replace").strip()
    profile = "ASiC-E" if manifests or "asic-e" in mimetype else "ASiC-S"
    return {
        "files": files,
        "data_files": data_files,
        "cades": cades,
        "manifests": manifests,
        "xades": xades,
        "profile": profile,
        "preview_name": os.path.basename(data_files[0]) if data_files else "contenuto.bin",
        "preview": files[data_files[0]] if data_files else b"",
    }
