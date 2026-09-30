import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from asn1crypto import cms, x509 as ax, tsp, core
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs7
from p7m_decoder import P7MDecoder
from services.signature.crypto_verifier import CryptoVerifier
from services.signature.cert_chain import CertificateChainValidator
from services.signature.revocation import RevocationChecker
from services.signature.timestamp import TimestampValidator
from services.signature.trust import validate_path

NOW = datetime.now(timezone.utc)


def cert_for(key, name, issuer=None, issuer_key=None, ca=False, serial=None, eku=None):
    dn = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    b = x509.CertificateBuilder().subject_name(dn).issuer_name(issuer.subject if issuer else dn)
    b = b.public_key(key.public_key()).serial_number(serial or x509.random_serial_number())
    b = b.not_valid_before(NOW - timedelta(days=2)).not_valid_after(NOW + timedelta(days=365))
    b = b.add_extension(x509.BasicConstraints(ca=ca, path_length=None), True)
    b = b.add_extension(x509.KeyUsage(True, False, False, False, False, ca, ca, False, False), True)
    if eku:
        b = b.add_extension(x509.ExtendedKeyUsage([eku]), True)
    return b.sign(issuer_key or key, hashes.SHA256())


def asn(cert):
    return ax.Certificate.load(cert.public_bytes(serialization.Encoding.DER))


def envelope(key, cert, data=b'Hello', options=None):
    raw = pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256()).sign(serialization.Encoding.DER, options or [pkcs7.PKCS7Options.Binary])
    return cms.ContentInfo.load(raw)


class SecurityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.root = cert_for(cls.root_key, 'Root', ca=True)
        cls.leaf = cert_for(cls.key, 'Signer', cls.root, cls.root_key)
        cls.tsa = cert_for(cls.key, 'TSA', cls.root, cls.root_key, eku=ExtendedKeyUsageOID.TIME_STAMPING)

    def test_plain_pdf_has_no_valid_signature(self):
        r = P7MDecoder.decode_file(b'%PDF-1.4\n%%EOF')
        self.assertTrue(r['success'])
        self.assertIsNone(r['signer_info']['crypto_valid'])
        self.assertIsNone(r['signer_info']['is_qtsp_qualified'])
        self.assertEqual(r['signer_info']['revocation_status'], 'UNKNOWN')

    def test_pades_is_detected_but_not_validated(self):
        r = P7MDecoder.decode_file(b'%PDF-1.4 /ByteRange [0 1 2 3] %%EOF')
        self.assertIn('PAdES', r['signer_info']['signer_name'])
        self.assertIsNone(r['signer_info']['crypto_valid'])

    def test_raw_recovery_has_no_positive_verdict(self):
        r = P7MDecoder.decode_file(b'garbage%PDF-1.4\n%%EOF')
        self.assertTrue(r['success'])
        self.assertIsNone(r['signer_info']['crypto_valid'])

    def test_missing_file_returns_error(self):
        self.assertFalse(P7MDecoder.decode_file('missing-file.p7m')['success'])

    def test_certificate_match_requires_issuer_and_serial(self):
        ci = envelope(self.key, self.leaf)
        other = cert_for(self.root_key, 'Other', serial=self.leaf.serial_number)
        self.assertIsNone(CertificateChainValidator.match_signer_certificate(ci['content']['signer_infos'][0], [asn(other)]))

    def test_missing_digest_rejected(self):
        si = envelope(self.key, self.leaf)['content']['signer_infos'][0]
        si['signed_attrs'] = cms.CMSAttributes([a for a in si['signed_attrs'] if a['type'].native != 'message_digest'])
        r = CryptoVerifier.verify_signer(si, asn(self.leaf), b'Hello')
        self.assertFalse(r['crypto_valid'])
        self.assertFalse(r['digest_matches'])

    def test_duplicate_digest_rejected(self):
        si = envelope(self.key, self.leaf)['content']['signer_infos'][0]
        attrs = list(si['signed_attrs'])
        attrs.append(next(a for a in attrs if a['type'].native == 'message_digest'))
        si['signed_attrs'] = cms.CMSAttributes(attrs)
        self.assertFalse(CryptoVerifier.verify_signer(si, asn(self.leaf), b'Hello')['crypto_valid'])

    def test_content_type_rejected(self):
        si = envelope(self.key, self.leaf)['content']['signer_infos'][0]
        self.assertFalse(CryptoVerifier.verify_signer(si, asn(self.leaf), b'Hello', 'tst_info')['crypto_valid'])

    def test_tampered_payload_rejected(self):
        si = envelope(self.key, self.leaf)['content']['signer_infos'][0]
        self.assertFalse(CryptoVerifier.verify_signer(si, asn(self.leaf), b'HELLO')['digest_matches'])

    def test_tampered_signature_rejected(self):
        si = envelope(self.key, self.leaf)['content']['signer_infos'][0]
        si['signature'] = bytes(len(si['signature'].native))
        self.assertFalse(CryptoVerifier.verify_signer(si, asn(self.leaf), b'Hello')['crypto_valid'])

    def test_unknown_hash_rejected(self):
        with self.assertRaises(ValueError):
            CryptoVerifier.compute_digest(b'Hello', 'unknown')

    def test_rsa_pss_supported(self):
        ci = pkcs7.PKCS7SignatureBuilder().set_data(b'Hello').add_signer(self.leaf, self.key, hashes.SHA256(), rsa_padding=padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)).sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
        si = cms.ContentInfo.load(ci)['content']['signer_infos'][0]
        r = CryptoVerifier.verify_signer(si, asn(self.leaf), b'Hello')
        self.assertTrue(r['crypto_valid'], r['error'])
        self.assertTrue(r['digest_matches'])

    def test_path_requires_trusted_root(self):
        self.assertFalse(validate_path(asn(self.leaf), [asn(self.root)], roots=[])['trusted'])
        r = validate_path(asn(self.leaf), [asn(self.root)], roots=[asn(self.root)])
        self.assertTrue(r['trusted'], r['error'])

    def make_crl(self, revoked=False, expired=False, wrong_key=False):
        b = x509.CertificateRevocationListBuilder().issuer_name(self.root.subject)
        b = b.last_update(NOW - timedelta(days=2)).next_update(NOW + timedelta(days=-1 if expired else 1))
        if revoked:
            entry = x509.RevokedCertificateBuilder().serial_number(self.leaf.serial_number).revocation_date(NOW - timedelta(hours=1)).build()
            b = b.add_revoked_certificate(entry)
        return b.sign(self.key if wrong_key else self.root_key, hashes.SHA256())

    def test_signed_crl_good_and_revoked(self):
        self.assertEqual(RevocationChecker.validate_crl(self.make_crl(), self.leaf, self.root), 'GOOD')
        self.assertEqual(RevocationChecker.validate_crl(self.make_crl(revoked=True), self.leaf, self.root), 'REVOKED')

    def test_stale_crl_rejected(self):
        with self.assertRaises(ValueError):
            RevocationChecker.validate_crl(self.make_crl(expired=True), self.leaf, self.root)

    def test_forged_crl_rejected(self):
        with self.assertRaises(ValueError):
            RevocationChecker.validate_crl(self.make_crl(wrong_key=True), self.leaf, self.root)

    def make_ocsp(self, status, expired=False, wrong_key=False):
        b = ocsp.OCSPResponseBuilder().add_response(self.leaf, self.root, hashes.SHA256(), status,
            NOW - timedelta(hours=1), NOW + timedelta(minutes=-1 if expired else 60),
            NOW - timedelta(hours=1) if status == ocsp.OCSPCertStatus.REVOKED else None, None)
        b = b.responder_id(ocsp.OCSPResponderEncoding.NAME, self.root)
        return b.sign(self.key if wrong_key else self.root_key, hashes.SHA256())

    def request(self):
        return ocsp.OCSPRequestBuilder().add_certificate(self.leaf, self.root, hashes.SHA256()).build()

    def test_signed_ocsp_good_revoked_unknown(self):
        for status, expected in [(ocsp.OCSPCertStatus.GOOD, 'GOOD'), (ocsp.OCSPCertStatus.REVOKED, 'REVOKED'), (ocsp.OCSPCertStatus.UNKNOWN, 'UNKNOWN')]:
            self.assertEqual(RevocationChecker.validate_ocsp(self.make_ocsp(status), self.request(), self.root), expected)

    def test_stale_ocsp_rejected(self):
        with self.assertRaises(ValueError):
            RevocationChecker.validate_ocsp(self.make_ocsp(ocsp.OCSPCertStatus.GOOD, expired=True), self.request(), self.root)

    def test_wrong_ocsp_certificate_rejected(self):
        request = ocsp.OCSPRequestBuilder().add_certificate(self.tsa, self.root, hashes.SHA256()).build()
        with self.assertRaises(ValueError):
            RevocationChecker.validate_ocsp(self.make_ocsp(ocsp.OCSPCertStatus.GOOD), request, self.root)

    def test_forged_ocsp_rejected(self):
        with self.assertRaises(Exception):
            RevocationChecker.validate_ocsp(self.make_ocsp(ocsp.OCSPCertStatus.GOOD, wrong_key=True), self.request(), self.root)

    def test_http_success_is_not_revocation_evidence(self):
        with patch.object(RevocationChecker, '_extract_endpoints', return_value=('https://ca.test/ocsp', None)), patch.object(RevocationChecker, 'fetch', return_value=b'HTTP OK'):
            self.assertEqual(RevocationChecker.check_revocation(asn(self.leaf), issuer=asn(self.root))['status'], 'UNKNOWN')

    def timestamped(self, wrong_imprint=False, forged=False):
        outer = envelope(self.key, self.leaf)
        si = outer['content']['signer_infos'][0]
        digest = CryptoVerifier.compute_digest(si['signature'].native, 'sha256')
        info = tsp.TSTInfo({'version': 1, 'policy': '1.2.3.4', 'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'}, 'hashed_message': bytes(32) if wrong_imprint else digest}, 'serial_number': 1, 'gen_time': NOW})
        token = envelope(self.key, self.tsa, info.dump())
        sd = token['content']
        sd['version'] = 'v3'
        sd['encap_content_info'] = cms.EncapsulatedContentInfo({'content_type': 'tst_info', 'content': info})
        ts_si = sd['signer_infos'][0]
        for attr in ts_si['signed_attrs']:
            if attr['type'].native == 'content_type':
                attr['values'] = ['tst_info']
        signed = ts_si['signed_attrs'].dump()
        signed = bytes([0x31]) + signed[1:]
        ts_si['signature'] = self.key.sign(signed, padding.PKCS1v15(), hashes.SHA256()) if not forged else bytes(256)
        sd['certificates'].append(cms.CertificateChoices(name='certificate', value=asn(self.root)))
        si['unsigned_attrs'] = cms.CMSAttributes([{'type': 'signature_time_stamp_token', 'values': [token]}])
        return si

    def test_timestamp_crypto_and_imprint_verified(self):
        r = TimestampValidator.extract_timestamp(self.timestamped(), roots=[asn(self.root)])
        self.assertTrue(r['crypto_valid'], r['message'])
        self.assertIsNone(r['valid'])  # Historical revocation cannot be inferred.

    def test_unrelated_timestamp_rejected(self):
        r = TimestampValidator.extract_timestamp(self.timestamped(wrong_imprint=True))
        self.assertFalse(r['valid'])

    def test_forged_timestamp_rejected(self):
        r = TimestampValidator.extract_timestamp(self.timestamped(forged=True))
        self.assertFalse(r['valid'])


if __name__ == '__main__':
    unittest.main()
