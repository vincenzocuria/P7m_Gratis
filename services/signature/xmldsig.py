"""XML-DSig and the XAdES properties carried inside the same signature."""
import base64
import hashlib
import re
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from lxml import etree

DSIG = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

DIGESTS = {
    "http://www.w3.org/2000/09/xmldsig#sha1": "sha1",
    "http://www.w3.org/2001/04/xmlenc#sha256": "sha256",
    "http://www.w3.org/2001/04/xmldsig-more#sha384": "sha384",
    "http://www.w3.org/2001/04/xmlenc#sha512": "sha512",
}
SIGNATURES = {
    "http://www.w3.org/2000/09/xmldsig#rsa-sha1": ("rsa", "sha1"),
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": ("rsa", "sha256"),
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384": ("rsa", "sha384"),
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512": ("rsa", "sha512"),
    "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256": ("ecdsa", "sha256"),
}
HASHES = {
    "sha1": hashes.SHA1(),
    "sha256": hashes.SHA256(),
    "sha384": hashes.SHA384(),
    "sha512": hashes.SHA512(),
}


def _local(element) -> str:
    return etree.QName(element).localname


def _child(element, name: str):
    for child in element:
        if _local(child) == name:
            return child
    return None


def _children(element, name: str):
    return [child for child in element if _local(child) == name]


def _descendants(element, name: str):
    return [item for item in element.iter() if _local(item) == name]


def _parser():
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)


def _digest(data: bytes, name: str) -> bytes:
    return hashlib.new(name, data).digest()


def _prefixes(element) -> List[str]:
    for child in element:
        if _local(child) == "InclusiveNamespaces":
            return (child.get("PrefixList") or "").split()
    return []


def _c14n(element, algorithm: str, prefix_source=None) -> bytes:
    if algorithm is not None and "WithComments" in algorithm:
        raise ValueError("Canonicalizzazione con commenti non supportata")
    exclusive = algorithm == EXC_C14N
    if algorithm not in (C14N, EXC_C14N, None):
        raise ValueError("Canonicalizzazione non supportata")
    return etree.tostring(
        element,
        method="c14n",
        exclusive=exclusive,
        with_comments=False,
        inclusive_ns_prefixes=_prefixes(prefix_source) if exclusive and prefix_source is not None else ([] if exclusive else None),
    )


def _find_id(root, ref_id: str):
    matches = []
    for element in root.iter():
        for attribute, value in element.attrib.items():
            if attribute.split("}")[-1] in ("Id", "ID", "id") and value == ref_id:
                matches.append(element)
                break
    if len(matches) != 1:
        raise ValueError("Riferimento XML ambiguo o assente")
    return matches[0]


def _lookup_file(uri: str, files: Dict[str, bytes]) -> bytes:
    if not files:
        raise ValueError("Riferimento esterno senza documento")
    candidates = [uri, uri.lstrip("./"), uri.split("/")[-1]]
    for candidate in candidates:
        if candidate in files:
            return files[candidate]
    raise ValueError(f"File firmato assente: {uri}")


def _apply_transforms(root, signature, reference, uri: str, files: Optional[Dict[str, bytes]]) -> bytes:
    transforms = _child(reference, "Transforms")
    operations = list(transforms) if transforms is not None else []
    if uri and not uri.startswith("#"):
        current = _lookup_file(uri, files or {})
        if operations:
            raise ValueError("Trasformazioni su file esterno non supportate")
        return current

    current = root if not uri else _find_id(root, uri[1:])
    removed = False
    parent = index = None
    try:
        for operation in operations:
            algorithm = operation.get("Algorithm")
            if algorithm == ENVELOPED:
                if not isinstance(current, etree._Element):
                    raise ValueError("Trasformazione enveloped non applicabile")
                parent = signature.getparent()
                index = list(parent).index(signature)
                parent.remove(signature)
                removed = True
                current = root
            elif algorithm in (C14N, EXC_C14N):
                if isinstance(current, bytes):
                    raise ValueError("Canonicalizzazione ripetuta")
                current = etree.tostring(
                    current,
                    method="c14n",
                    exclusive=algorithm == EXC_C14N,
                    with_comments=False,
                    inclusive_ns_prefixes=_prefixes(operation) if algorithm == EXC_C14N else None,
                )
            else:
                raise ValueError("Trasformazione XML non supportata")
        if isinstance(current, etree._Element):
            current = _c14n(current, C14N)
        return current
    finally:
        if removed and parent is not None:
            parent.insert(index, signature)


def _certificates(signature) -> List[bytes]:
    certificates = []
    for element in _descendants(signature, "X509Certificate"):
        encoded = re.sub(r"\s+", "", "".join(element.itertext()))
        if encoded:
            certificates.append(base64.b64decode(encoded))
    return certificates


def _signing_certificate(signature, certificates: List[bytes]) -> Optional[bytes]:
    digests = []
    for element in _descendants(signature, "CertDigest"):
        method = _child(element, "DigestMethod")
        value = _child(element, "DigestValue")
        algorithm = DIGESTS.get(method.get("Algorithm") if method is not None else None)
        if algorithm is None or value is None:
            raise ValueError("Impronta del certificato XAdES non supportata")
        digests.append((algorithm, base64.b64decode(re.sub(r"\s+", "", "".join(value.itertext())))))
    if not digests:
        return certificates[0] if certificates else None
    algorithm, expected = digests[0]
    for certificate in certificates:
        if _digest(certificate, algorithm) == expected:
            return certificate
    raise ValueError("Il certificato dichiarato da XAdES non coincide")


def _verify_signature(certificate: bytes, signed_info: bytes, signature_value: bytes, method: str) -> str:
    kind, digest_name = SIGNATURES[method]
    parsed = x509.load_der_x509_certificate(certificate)
    key = parsed.public_key()
    algorithm = HASHES[digest_name]
    if kind == "rsa":
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("Chiave non RSA")
        key.verify(signature_value, signed_info, padding.PKCS1v15(), algorithm)
        return f"RSA-{digest_name.upper()}"
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("Chiave non ECDSA")
    key.verify(signature_value, signed_info, ec.ECDSA(algorithm))
    return f"ECDSA-{digest_name.upper()}"


def _verify_one(root, signature, files: Optional[Dict[str, bytes]]) -> Dict:
    result = {
        "certificates": [],
        "crypto_valid": False,
        "digest_matches": False,
        "algorithm": "XML-DSig",
        "error": None,
        "profile": "XML-DSig",
    }
    try:
        signed_info = _child(signature, "SignedInfo")
        signature_value = _child(signature, "SignatureValue")
        if signed_info is None or signature_value is None:
            raise ValueError("SignedInfo o SignatureValue assente")
        method = _child(signed_info, "SignatureMethod")
        signature_method = method.get("Algorithm") if method is not None else None
        if signature_method not in SIGNATURES:
            raise ValueError("Algoritmo di firma XML non supportato")
        canonicalization = _child(signed_info, "CanonicalizationMethod")
        canonical_method = canonicalization.get("Algorithm") if canonicalization is not None else None
        signed_bytes = _c14n(signed_info, canonical_method, canonicalization)
        references = _children(signed_info, "Reference")
        if not references:
            raise ValueError("Nessun riferimento firmato")
        digest_ok = True
        for reference in references:
            if reference.get("URI") is None:
                raise ValueError("URI del riferimento assente")
            digest_method = _child(reference, "DigestMethod")
            digest_value = _child(reference, "DigestValue")
            algorithm = DIGESTS.get(digest_method.get("Algorithm") if digest_method is not None else None)
            if algorithm is None or digest_value is None:
                raise ValueError("Digest del riferimento non supportato")
            produced = _apply_transforms(root, signature, reference, reference.get("URI"), files)
            expected = base64.b64decode(re.sub(r"\s+", "", "".join(digest_value.itertext())))
            digest_ok = digest_ok and _same_bytes(_digest(produced, algorithm), expected)
        certificates = _certificates(signature)
        result["certificates"] = certificates
        certificate = _signing_certificate(signature, certificates)
        if certificate is None:
            raise ValueError("Certificato del firmatario assente")
        result["certificates"] = [certificate] + [item for item in certificates if item != certificate]
        result["algorithm"] = _verify_signature(
            certificate,
            signed_bytes,
            base64.b64decode(re.sub(r"\s+", "", "".join(signature_value.itertext()))),
            signature_method,
        )
        result["crypto_valid"] = True
        result["digest_matches"] = digest_ok
        if any(_local(item) == "QualifyingProperties" for item in signature.iter()):
            result["profile"] = "XAdES"
        if not digest_ok:
            result["error"] = "Impronta del contenuto XML diversa"
    except Exception as exc:
        result["crypto_valid"] = False
        result["digest_matches"] = False
        result["error"] = str(exc)
    return result


def _same_bytes(left: bytes, right: bytes) -> bool:
    if len(left) != len(right):
        return False
    difference = 0
    for first, second in zip(left, right):
        difference |= first ^ second
    return difference == 0


def verify_xml_signatures(xml_bytes: bytes, extra_files: Optional[Dict[str, bytes]] = None) -> List[Dict]:
    """Verify every XML-DSig signature. An empty list means the document has none."""
    try:
        root = etree.fromstring(xml_bytes, _parser())
    except etree.XMLSyntaxError:
        return []
    signatures = [item for item in root.iter() if _local(item) == "Signature" and etree.QName(item).namespace == DSIG]
    return [_verify_one(root, signature, extra_files) for signature in signatures]
