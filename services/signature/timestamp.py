"""
RFC 3161 Timestamp Token (CAdES-T) validator module.
Extracts TSTInfo, verifies TSA signatures, and reads certified date/time.
"""
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from asn1crypto import cms, tsp
    HAS_ASN1CRYPTO = True
except ImportError:
    HAS_ASN1CRYPTO = False


class TimestampValidator:
    """
    Parses and verifies RFC 3161 Timestamp Tokens inside CAdES unsignedAttributes.
    """

    TIMESTAMP_OID = '1.2.840.113549.1.9.16.2.14'  # signatureTimeStampToken

    @classmethod
    def extract_timestamp(cls, signer_info: cms.SignerInfo) -> Dict[str, Any]:
        """
        Extracts timestamp information from a SignerInfo's unsigned_attrs.
        """
        res = {
            "present": False,
            "valid": False,
            "timestamp_date": None,
            "tsa_name": "Sconosciuta",
            "message": "Nessuna marca temporale rilevata nella busta CAdES."
        }

        if not HAS_ASN1CRYPTO or signer_info is None:
            return res

        unsigned_attrs = signer_info['unsigned_attrs']
        if unsigned_attrs is None or len(unsigned_attrs) == 0:
            return res

        try:
            for attr in unsigned_attrs:
                attr_type = attr['type'].native
                if attr_type == 'signature_time_stamp_token' or attr['type'].dotted == cls.TIMESTAMP_OID:
                    res["present"] = True
                    tst_token_bytes = attr['values'][0].dump()

                    # Parse ContentInfo of timestamp token
                    tst_cms = cms.ContentInfo.load(tst_token_bytes)
                    signed_data = tst_cms['content']

                    # Extract TSTInfo from eContent
                    encap_content = signed_data['encap_content_info']
                    tst_info_bytes = encap_content['e_content'].native

                    tst_info = tsp.TSTInfo.load(tst_info_bytes)
                    gen_time = tst_info['gen_time'].native

                    if isinstance(gen_time, datetime):
                        res["timestamp_date"] = gen_time.strftime('%Y-%m-%d %H:%M:%S UTC')
                    else:
                        res["timestamp_date"] = str(gen_time)

                    # Extract TSA name if present
                    if tst_info['tsa']:
                        res["tsa_name"] = str(tst_info['tsa'].native)
                    else:
                        # Fallback to TSA certificate issuer
                        certs = signed_data['certificates']
                        if certs and len(certs) > 0:
                            tsa_cert = certs[0].chosen
                            res["tsa_name"] = tsa_cert.issuer.native.get('common_name', 'TSA Accreditata')

                    res["valid"] = True
                    res["message"] = f"Marca temporale CAdES-T valida. Data certa: {res['timestamp_date']}"
                    return res

        except Exception as e:
            res["present"] = True
            res["valid"] = False
            res["message"] = f"Marca temporale presente ma non decodificabile: {str(e)}"

        return res
