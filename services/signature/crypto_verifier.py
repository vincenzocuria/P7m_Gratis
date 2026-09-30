"""
Cryptographic signature and digest verification module for PKCS#7 / CMS / CAdES.
Verifies RSA & ECDSA signatures over signedAttributes, and checks payload digest matching.
"""
import hashlib
from typing import Dict, Any, Tuple, Optional

try:
    from asn1crypto import cms, x509
    HAS_ASN1CRYPTO = True
except ImportError:
    HAS_ASN1CRYPTO = False

try:
    from cryptography import x509 as crypto_x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, ec, rsa, dsa
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CryptoVerifier:
    """
    Handles cryptographic verification of CMS/CAdES SignerInfo structures.
    """

    HASH_ALGO_MAP = {
        'sha256': hashes.SHA256(),
        'sha384': hashes.SHA384(),
        'sha512': hashes.SHA512(),
        'sha1': hashes.SHA1(),
    }

    @classmethod
    def verify_signer(
        cls,
        signer_info: cms.SignerInfo,
        cert_asn1: x509.Certificate,
        payload_bytes: bytes,
        expected_content_type: str = "data"
    ) -> Dict[str, Any]:
        """
        Verifies a single SignerInfo structure against the signer's certificate and payload.
        
        Returns a dict:
        - crypto_valid: bool (true if cryptographic signature math is valid)
        - digest_matches: bool (true if payload digest matches messageDigest attribute)
        - algorithm: str
        - digest_name: str
        - error: Optional[str]
        """
        res = {
            "crypto_valid": False,
            "digest_matches": False,
            "algorithm": "Unknown",
            "digest_name": "sha256",
            "error": None
        }

        if not HAS_ASN1CRYPTO or not HAS_CRYPTOGRAPHY:
            res["error"] = "Librerie crittografiche (asn1crypto/cryptography) non disponibili."
            return res

        try:
            # 1. Determine digest algorithm
            digest_algo_name = signer_info['digest_algorithm']['algorithm'].native.lower()
            res["digest_name"] = digest_algo_name

            # Calculate actual payload hash
            if digest_algo_name not in cls.HASH_ALGO_MAP:
                raise ValueError(f"Algoritmo di digest non supportato: {digest_algo_name}")
            actual_digest = cls.compute_digest(payload_bytes, digest_algo_name)

            # 2. Inspect signedAttributes if present
            signed_attrs = signer_info['signed_attrs']
            signature_bytes = signer_info['signature'].native

            if signed_attrs is not None and len(signed_attrs) > 0:
                # Find messageDigest attribute
                md_attrs = [a for a in signed_attrs if a['type'].native == 'message_digest']
                ct_attrs = [a for a in signed_attrs if a['type'].native == 'content_type']
                if len(md_attrs) != 1 or len(md_attrs[0]['values']) != 1:
                    raise ValueError("Attributo messageDigest mancante o duplicato")
                if len(ct_attrs) != 1 or len(ct_attrs[0]['values']) != 1:
                    raise ValueError("Attributo contentType mancante o duplicato")
                if ct_attrs[0]['values'][0].native != expected_content_type:
                    raise ValueError('contentType non corrisponde al contenuto')
                msg_digest_attr = md_attrs[0]['values'][0].native

                if msg_digest_attr is not None:
                    res["digest_matches"] = (msg_digest_attr == actual_digest)
                else:
                    # Message digest attribute missing
                    raise ValueError("Attributo messageDigest mancante")

                # Per RFC 5652 Section 5.3, the signature is computed over the DER encoding of signedAttrs
                # using the SET OF tag (0x31)
                data_to_verify = signed_attrs.dump()
                # Ensure tag is SET (0x31)
                if data_to_verify[0] != 0x31:
                    data_to_verify = bytearray(data_to_verify)
                    data_to_verify[0] = 0x31
                    data_to_verify = bytes(data_to_verify)
            else:
                # Signature is directly over payload
                if expected_content_type != 'data':
                    raise ValueError("signedAttributes obbligatori per contenuti non-data")
                res["digest_matches"] = True
                data_to_verify = payload_bytes

            # 3. Load public key from certificate using cryptography
            cert_der = cert_asn1.dump()
            crypto_cert = crypto_x509.load_der_x509_certificate(cert_der)
            public_key = crypto_cert.public_key()

            # Determine signature algorithm & hash object
            hash_obj = cls.HASH_ALGO_MAP[digest_algo_name]
            sig_algo = signer_info['signature_algorithm']['algorithm'].native

            if isinstance(public_key, rsa.RSAPublicKey):
                res["algorithm"] = f"RSA-{digest_algo_name.upper()}"
                rsa_padding = padding.PKCS1v15()
                if sig_algo == 'rsassa_pss':
                    params = signer_info['signature_algorithm']['parameters']
                    pss_hash = params['hash_algorithm']['algorithm'].native
                    mgf = params['mask_gen_algorithm']
                    mgf_hash = mgf['parameters']['algorithm'].native
                    if pss_hash != digest_algo_name or mgf['algorithm'].native != 'mgf1' or mgf_hash not in cls.HASH_ALGO_MAP:
                        raise ValueError("Parametri RSA-PSS non supportati o incoerenti")
                    if params['trailer_field'].native != 'trailer_field_bc':
                        raise ValueError("Trailer RSA-PSS non supportato")
                    rsa_padding = padding.PSS(mgf=padding.MGF1(cls.HASH_ALGO_MAP[mgf_hash]), salt_length=params['salt_length'].native)
                elif sig_algo not in ('rsassa_pkcs1v15', f'{digest_algo_name}_rsa'):
                    raise ValueError(f"Algoritmo firma RSA non supportato: {sig_algo}")
                public_key.verify(
                    signature_bytes,
                    data_to_verify,
                    rsa_padding,
                    hash_obj
                )
                res["crypto_valid"] = True
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                if sig_algo != f'{digest_algo_name}_ecdsa':
                    raise ValueError("Algoritmo ECDSA non coerente con il digest")
                res["algorithm"] = f"ECDSA-{digest_algo_name.upper()}"
                public_key.verify(
                    signature_bytes,
                    data_to_verify,
                    ec.ECDSA(hash_obj)
                )
                res["crypto_valid"] = True
            elif isinstance(public_key, dsa.DSAPublicKey):
                if sig_algo not in ('dsa', f'{digest_algo_name}_dsa'):
                    raise ValueError("Algoritmo DSA non coerente con il digest")
                res["algorithm"] = f"DSA-{digest_algo_name.upper()}"
                public_key.verify(
                    signature_bytes,
                    data_to_verify,
                    hash_obj
                )
                res["crypto_valid"] = True
            else:
                res["error"] = f"Tipo di chiave pubblica non supportato: {type(public_key)}"

        except Exception as e:
            res["crypto_valid"] = False
            res["error"] = f"Verifica crittografica fallita: {str(e)}"

        return res

    @staticmethod
    def compute_digest(data: bytes, algo_name: str) -> bytes:
        algo = algo_name.lower()
        if algo in ('sha256', '2.16.840.1.101.3.4.2.1'):
            return hashlib.sha256(data).digest()
        elif algo in ('sha384', '2.16.840.1.101.3.4.2.2'):
            return hashlib.sha384(data).digest()
        elif algo in ('sha512', '2.16.840.1.101.3.4.2.3'):
            return hashlib.sha512(data).digest()
        elif algo in ('sha1', '1.3.14.3.2.26'):
            return hashlib.sha1(data).digest()
        else:
            raise ValueError(f"Algoritmo digest non supportato: {algo_name}")
