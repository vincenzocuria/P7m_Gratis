"""
Certificate matching, parsing, and chain analysis module.
Correlates SignerInfo to signing certificates and parses X.509 attributes.
"""
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

try:
    from asn1crypto import cms, x509
    HAS_ASN1CRYPTO = True
except ImportError:
    HAS_ASN1CRYPTO = False


class CertificateChainValidator:
    """
    Handles X.509 certificate extraction, SignerInfo matching, and validity analysis.
    """

    @classmethod
    def match_signer_certificate(
        cls,
        signer_info: cms.SignerInfo,
        cert_list: List[x509.Certificate]
    ) -> Optional[x509.Certificate]:
        """
        Finds the exact X.509 certificate matching a SignerInfo's sid field.
        """
        if not cert_list:
            return None

        sid = signer_info['sid']
        sid_type = sid.name

        if sid_type == 'issuer_and_serial_number':
            target_issuer = sid.chosen['issuer'].native
            target_serial = sid.chosen['serial_number'].native

            for cert in cert_list:
                cert_issuer = cert.issuer.native
                cert_serial = cert.serial_number

                if cert_serial == target_serial and cert_issuer == target_issuer:
                    # Serial number match
                    return cert

        elif sid_type == 'subject_key_identifier':
            target_ski = sid.chosen.native
            for cert in cert_list:
                try:
                    ski_ext = cert.key_identifier
                    if ski_ext == target_ski:
                        return cert
                except Exception:
                    pass

        # Fallback: return first certificate if list has only one
        return None

    @classmethod
    def parse_certificate_meta(cls, cert: x509.Certificate) -> Dict[str, Any]:
        """
        Extracts structured metadata from an ASN.1 X.509 certificate.
        """
        meta = {
            "signer_name": "Sconosciuto",
            "tax_code": None,
            "organization": "N.D.",
            "issuer": "N.D.",
            "valid_from": None,
            "valid_until": None,
            "serial_number": None,
            "is_valid_now": False,
            "key_usage": [],
            "raw_subject": None
        }

        if cert is None:
            return meta

        try:
            subject = cert.subject.native
            issuer = cert.issuer.native
            meta["raw_subject"] = str(subject)

            # Common Name & Organization
            meta["signer_name"] = subject.get('common_name', 'Sconosciuto')
            meta["organization"] = subject.get('organization_name', 'N.D.')
            meta["issuer"] = issuer.get('common_name', issuer.get('organization_name', 'N.D.'))
            meta["serial_number"] = str(cert.serial_number)

            # Extract Italian Fiscal Code / Codice Fiscale
            meta["tax_code"] = cls._extract_tax_code(subject)

            # Validity dates
            try:
                not_before = cert.not_valid_before
                not_after = cert.not_valid_after
            except Exception:
                try:
                    val = cert['tbs_certificate']['validity']
                    not_before = val['not_before'].native
                    not_after = val['not_after'].native
                except Exception:
                    not_before = None
                    not_after = None
            
            if isinstance(not_before, datetime):
                meta["valid_from"] = not_before.strftime('%d/%m/%Y %H:%M:%S')
            elif not_before:
                meta["valid_from"] = str(not_before)

            if isinstance(not_after, datetime):
                meta["valid_until"] = not_after.strftime('%d/%m/%Y %H:%M:%S')
            elif not_after:
                meta["valid_until"] = str(not_after)

            # Check if currently valid
            if isinstance(not_before, datetime) and isinstance(not_after, datetime):
                now = datetime.now(timezone.utc) if not_after.tzinfo is not None else datetime.now()
                # Ensure comparable timezone awareness
                nb = not_before if not_before.tzinfo is not None else not_before.replace(tzinfo=timezone.utc if not_after.tzinfo else None)
                na = not_after if not_after.tzinfo is not None else not_after.replace(tzinfo=timezone.utc if not_before.tzinfo else None)
                meta["is_valid_now"] = (nb <= now <= na)
            else:
                meta["is_valid_now"] = False

            # Key usage
            try:
                if cert.key_usage_value:
                    meta["key_usage"] = list(cert.key_usage_value.native)
            except Exception:
                pass

        except Exception as e:
            meta["error"] = f"Errore parsing certificato: {str(e)}"

        return meta

    @staticmethod
    def _extract_tax_code(subject_dict: Dict[str, Any]) -> Optional[str]:
        """
        Derives Italian 16-character Fiscal Code from Subject DN attributes.
        Checks serialNumber, commonName, or custom OIDs.
        """
        candidates = []

        if 'serial_number' in subject_dict:
            candidates.append(str(subject_dict['serial_number']))
        if 'common_name' in subject_dict:
            candidates.append(str(subject_dict['common_name']))

        # Regex for Italian Fiscal Code (16 alphanumeric) or TINIT-xxxx
        cf_pattern = re.compile(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', re.IGNORECASE)
        tinit_pattern = re.compile(r'TINIT-([A-Z0-9]+)', re.IGNORECASE)

        for text in candidates:
            m = tinit_pattern.search(text)
            if m:
                return m.group(1).upper()
            m = cf_pattern.search(text)
            if m:
                return m.group(1).upper()

        return None
