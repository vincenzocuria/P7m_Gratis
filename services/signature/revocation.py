"""Authenticated OCSP and complete, direct CRL checks. Errors remain unknown."""
from datetime import datetime, timezone, timedelta
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
import ipaddress
import socket
from typing import Tuple, Optional
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa, padding


def verify_signature(key, signature, data, algorithm):
    if isinstance(key, rsa.RSAPublicKey):
        key.verify(signature, data, padding.PKCS1v15(), algorithm)
    elif isinstance(key, ec.EllipticCurvePublicKey):
        key.verify(signature, data, ec.ECDSA(algorithm))
    elif isinstance(key, dsa.DSAPublicKey):
        key.verify(signature, data, algorithm)
    else:
        key.verify(signature, data)


def fresh(this_update, next_update, now):
    return (this_update is not None and next_update is not None
            and this_update <= now + timedelta(minutes=5) and next_update >= now
            and this_update < next_update)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect endpoint di revoca non consentito")


class RevocationChecker:
    MAX_RESPONSE = 16 * 1024 * 1024

    @classmethod
    def fetch(cls, url, timeout, data=None):
        parts = urlsplit(url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username:
            raise ValueError('Endpoint di revoca non HTTP(S)')
        if parts.port not in (None, 80, 443):
            raise ValueError('Porta endpoint di revoca non consentita')
        for item in socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(item[4][0]).is_global:
                raise ValueError('Endpoint di revoca su rete privata o locale')
        headers = {'User-Agent': 'P7M-Viewer-PA/2.1'}
        if data is not None:
            headers.update({'Content-Type': 'application/ocsp-request', 'Accept': 'application/ocsp-response'})
        with build_opener(NoRedirect()).open(Request(url, data=data, headers=headers), timeout=timeout) as response:
            blob = response.read(cls.MAX_RESPONSE + 1)
            if len(blob) > cls.MAX_RESPONSE:
                raise ValueError('Risposta di revoca troppo grande')
            return blob

    @classmethod
    def check_revocation(cls, cert, timeout_seconds=3.0, issuer=None):
        res = {'status': 'UNKNOWN', 'message': 'Revoca non verificata', 'ocsp_url': None, 'crl_url': None}
        if cert is None or issuer is None:
            res['message'] = 'Certificato emittente non disponibile: revoca non verificata'
            return res
        try:
            leaf = x509.load_der_x509_certificate(cert.dump())
            ca = x509.load_der_x509_certificate(issuer.dump())
            leaf.verify_directly_issued_by(ca)
            ocsp_url, crl_url = cls._extract_endpoints(cert)
            res.update(ocsp_url=ocsp_url, crl_url=crl_url)
            errors = []
            if ocsp_url:
                try:
                    request = ocsp.OCSPRequestBuilder().add_certificate(leaf, ca, hashes.SHA256()).build()
                    response = ocsp.load_der_ocsp_response(cls.fetch(ocsp_url, timeout_seconds, request.public_bytes(serialization.Encoding.DER)))
                    status = cls.validate_ocsp(response, request, ca)
                    if status != 'UNKNOWN':
                        return dict(res, status=status, message='Stato certificato verificato tramite OCSP firmato')
                except Exception as exc:
                    errors.append(str(exc))
            if crl_url:
                try:
                    blob = cls.fetch(crl_url, timeout_seconds)
                    crl = x509.load_pem_x509_crl(blob) if blob.startswith(b'-----') else x509.load_der_x509_crl(blob)
                    status = cls.validate_crl(crl, leaf, ca)
                    return dict(res, status=status, message='Stato certificato verificato tramite CRL firmata')
                except Exception as exc:
                    errors.append(str(exc))
            res['message'] = '; '.join(errors) or 'Endpoint OCSP/CRL non disponibile'
        except Exception as exc:
            res['message'] = str(exc)
        return res

    @staticmethod
    def validate_ocsp(response, request, issuer, now=None):
        now = now or datetime.now(timezone.utc)
        if response.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            raise ValueError('Risposta OCSP non riuscita')
        if (response.serial_number != request.serial_number or response.issuer_name_hash != request.issuer_name_hash
                or response.issuer_key_hash != request.issuer_key_hash or response.hash_algorithm.name != request.hash_algorithm.name):
            raise ValueError('Risposta OCSP per un altro certificato')
        if not fresh(response.this_update_utc, response.next_update_utc, now):
            raise ValueError('Risposta OCSP scaduta o senza intervallo di validità')
        responder = None
        for candidate in [issuer, *response.certificates]:
            name_matches = response.responder_name is not None and response.responder_name == candidate.subject
            key_matches = response.responder_key_hash is not None and response.responder_key_hash == x509.SubjectKeyIdentifier.from_public_key(candidate.public_key()).digest
            if name_matches or key_matches:
                responder = candidate
                break
        if responder is None:
            raise ValueError('Certificato del responder OCSP non trovato')
        if responder.fingerprint(hashes.SHA256()) != issuer.fingerprint(hashes.SHA256()):
            responder.verify_directly_issued_by(issuer)
            eku = responder.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if ExtendedKeyUsageOID.OCSP_SIGNING not in eku:
                raise ValueError('Responder non autorizzato per OCSP')
            # Without OCSP no-check the delegated responder itself needs revocation validation.
            responder.extensions.get_extension_for_class(x509.OCSPNoCheck)
        if not responder.not_valid_before_utc <= now <= responder.not_valid_after_utc:
            raise ValueError('Certificato OCSP fuori validità')
        if any(ext.critical for ext in response.extensions):
            raise ValueError('Estensione OCSP critica non supportata')
        verify_signature(responder.public_key(), response.signature, response.tbs_response_bytes, response.signature_hash_algorithm)
        return {ocsp.OCSPCertStatus.GOOD: 'GOOD', ocsp.OCSPCertStatus.REVOKED: 'REVOKED'}.get(response.certificate_status, 'UNKNOWN')

    @staticmethod
    def validate_crl(crl, leaf, issuer, now=None):
        now = now or datetime.now(timezone.utc)
        if crl.issuer != issuer.subject or leaf.issuer != issuer.subject:
            raise ValueError('CRL emessa da un altro certificato')
        if not fresh(crl.last_update_utc, crl.next_update_utc, now):
            raise ValueError('CRL scaduta o senza intervallo di validità')
        usage = issuer.extensions.get_extension_for_class(x509.KeyUsage).value
        if not usage.crl_sign:
            raise ValueError('Emittente non autorizzato a firmare CRL')
        for ext in crl.extensions:
            if ext.oid in (ExtensionOID.DELTA_CRL_INDICATOR, ExtensionOID.ISSUING_DISTRIBUTION_POINT) or (ext.critical and ext.oid != ExtensionOID.AUTHORITY_KEY_IDENTIFIER):
                raise ValueError('CRL parziale, indiretta o con estensione non supportata')
        if not crl.is_signature_valid(issuer.public_key()):
            raise ValueError('Firma CRL non valida')
        entry = crl.get_revoked_certificate_by_serial_number(leaf.serial_number)
        if entry is not None:
            return 'REVOKED'
        return 'GOOD'

    @staticmethod
    def _extract_endpoints(cert) -> Tuple[Optional[str], Optional[str]]:
        ocsp_url = crl_url = None
        if cert.authority_information_access_value:
            for entry in cert.authority_information_access_value:
                if entry['access_method'].native == 'ocsp':
                    ocsp_url = entry['access_location'].native
                    break
        if cert.crl_distribution_points_value:
            for point in cert.crl_distribution_points_value:
                name = point['distribution_point']
                if name.native and name.name == 'full_name':
                    for item in name.chosen:
                        if item.name == 'uniform_resource_identifier':
                            crl_url = item.native
                            break
                if crl_url:
                    break
        return ocsp_url, crl_url
