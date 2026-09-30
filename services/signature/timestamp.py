"""Verify RFC 3161 CMS signature and messageImprint; trust stays explicit."""
from datetime import datetime, timezone, timedelta
from asn1crypto import cms, tsp
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from .crypto_verifier import CryptoVerifier
from .cert_chain import CertificateChainValidator
from .trust import validate_path
from .revocation import RevocationChecker


class TimestampValidator:
    TIMESTAMP_OID = '1.2.840.113549.1.9.16.2.14'

    @classmethod
    def extract_timestamp(cls, signer_info, roots=None):
        res = {'present': False, 'valid': None, 'crypto_valid': None, 'timestamp_date': None,
               'tsa_name': 'Sconosciuta', 'message': 'Nessuna marca temporale'}
        try:
            attrs = signer_info['unsigned_attrs']
            tokens = [a for a in attrs if a['type'].dotted == cls.TIMESTAMP_OID] if attrs.native is not None else []
            if not tokens:
                return res
            res['present'] = True
            res['valid'] = False
            if len(tokens) != 1 or len(tokens[0]['values']) != 1:
                raise ValueError('Marca temporale duplicata o ambigua')
            token = cms.ContentInfo.load(tokens[0]['values'][0].dump())
            if token['content_type'].native != 'signed_data':
                raise ValueError('Token temporale non SignedData')
            sd = token['content']
            content = sd['encap_content_info']
            if content['content_type'].native != 'tst_info':
                raise ValueError('Tipo contenuto temporale non TSTInfo')
            raw = content['content'].parsed.dump()
            info = tsp.TSTInfo.load(raw)
            imprint = info['message_imprint']
            algo = imprint['hash_algorithm']['algorithm'].native
            if CryptoVerifier.compute_digest(signer_info['signature'].native, algo) != imprint['hashed_message'].native:
                raise ValueError('Marca temporale non collegata alla firma')
            date = info['gen_time'].native
            if date > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError('Marca temporale con data futura')
            res['timestamp_date'] = date.isoformat()
            certs = [c.chosen for c in sd['certificates'] if c.name == 'certificate']
            if len(sd['signer_infos']) != 1:
                raise ValueError('Token temporale con firmatari ambigui')
            si = sd['signer_infos'][0]
            cert = CertificateChainValidator.match_signer_certificate(si, certs)
            result = CryptoVerifier.verify_signer(si, cert, raw, expected_content_type='tst_info')
            if not result['crypto_valid'] or not result['digest_matches']:
                raise ValueError(result['error'] or 'Firma TSA non valida')
            res['crypto_valid'] = True
            tsa = x509.load_der_x509_certificate(cert.dump())
            eku = tsa.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
            if not eku.critical or list(eku.value) != [ExtendedKeyUsageOID.TIME_STAMPING]:
                raise ValueError('Certificato TSA privo di EKU esclusivo e critico timeStamping')
            res['tsa_name'] = cert.subject.human_friendly
            trust = validate_path(cert, certs, moment=date, roots=roots, eku='time_stamping')
            # A current OCSP response cannot establish historical TSA revocation.
            # Keep the overall date proof unverified until historical revocation is available.
            res['valid'] = None
            res['message'] = ('Firma e impronta TSA corrette; catena verificata alla data della marca. '
                              'Revoca storica TSA non verificata.' if trust['trusted'] else
                              'Firma e impronta TSA corrette; catena TSA non attendibile: ' + str(trust['error']))
        except Exception as exc:
            res['message'] = 'Marca temporale non valida: ' + str(exc)
        return res
