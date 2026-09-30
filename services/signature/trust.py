"""PKIX path validation against local trust anchors, never against names."""
import asyncio
import ssl
from functools import lru_cache
from asn1crypto import x509
from pyhanko_certvalidator import CertificateValidator, ValidationContext


@lru_cache(maxsize=1)
def system_roots():
    roots = []
    if hasattr(ssl, 'enum_certificates'):
        for der, encoding, trust in ssl.enum_certificates('ROOT'):
            if encoding == 'x509_asn' and trust is True:
                roots.append(x509.Certificate.load(der))
    else:
        roots = [x509.Certificate.load(der) for der in ssl.create_default_context().get_ca_certs(binary_form=True)]
    return tuple(roots)


def validate_path(cert, certificates, moment=None, roots=None, eku=None):
    if cert is None:
        return {"trusted": False, "path": [], "error": "Certificato del firmatario non trovato"}
    try:
        context = ValidationContext(
            trust_roots=list(system_roots() if roots is None else roots),
            other_certs=certificates, allow_fetching=False, moment=moment,
            revocation_mode='soft-fail', weak_hash_algos={'md2', 'md5', 'sha1'})
        validator = CertificateValidator(cert, certificates, context)
        path = asyncio.run(validator.async_validate_usage(set(), {eku} if eku else None))
        return {"trusted": True, "path": list(path), "error": None}
    except Exception as exc:
        return {"trusted": False, "path": [], "error": str(exc)}


def find_issuer(cert, certificates):
    if cert is None:
        return None
    from cryptography import x509 as cx
    leaf = cx.load_der_x509_certificate(cert.dump())
    for candidate in certificates:
        if candidate.subject != cert.issuer:
            continue
        try:
            leaf.verify_directly_issued_by(cx.load_der_x509_certificate(candidate.dump()))
            return candidate
        except Exception:
            continue
    return None
