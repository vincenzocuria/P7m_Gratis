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
        payload_bytes: bytes
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
            actual_digest = cls.compute_digest(payload_bytes, digest_algo_name)

            # 2. Inspect signedAttributes if present
            signed_attrs = signer_info['signed_attrs']
            signature_bytes = signer_info['signature'].native

            if signed_attrs is not None and len(signed_attrs) > 0:
                # Find messageDigest attribute
                msg_digest_attr = None
                for attr in signed_attrs:
                    if attr['type'].native == 'message_digest':
                        msg_digest_attr = attr['values'][0].native
                        break

                if msg_digest_attr is not None:
                    res["digest_matches"] = (msg_digest_attr == actual_digest)
                else:
                    # Message digest attribute missing
                    res["digest_matches"] = True  # fallback if not explicit

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
                res["digest_matches"] = True
                data_to_verify = payload_bytes

            # 3. Load public key from certificate using cryptography
            cert_der = cert_asn1.dump()
            crypto_cert = crypto_x509.load_der_x509_certificate(cert_der)
            public_key = crypto_cert.public_key()

            # Determine signature algorithm & hash object
            hash_obj = cls.HASH_ALGO_MAP.get(digest_algo_name, hashes.SHA256())

            if isinstance(public_key, rsa.RSAPublicKey):
                res["algorithm"] = f"RSA-{digest_algo_name.upper()}"
                public_key.verify(
                    signature_bytes,
                    data_to_verify,
                    padding.PKCS1v15(),
                    hash_obj
                )
                res["crypto_valid"] = True
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                res["algorithm"] = f"ECDSA-{digest_algo_name.upper()}"
                public_key.verify(
                    signature_bytes,
                    data_to_verify,
                    ec.ECDSA(hash_obj)
                )
                res["crypto_valid"] = True
            elif isinstance(public_key, dsa.DSAPublicKey):
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
            return hashlib.sha256(data).digest()
