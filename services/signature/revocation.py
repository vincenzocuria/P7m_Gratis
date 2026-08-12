"""
AIA, OCSP, and CRL revocation status checking module.
Interrogates online revocation endpoints with timeout and caching.
"""
import urllib.request
from typing import Dict, Any, Optional

try:
    from asn1crypto import x509
    HAS_ASN1CRYPTO = True
except ImportError:
    HAS_ASN1CRYPTO = False


class RevocationChecker:
    """
    Handles online & offline revocation status checking for X.509 certificates.
    """

    @classmethod
    def check_revocation(
        cls,
        cert: x509.Certificate,
        timeout_seconds: float = 2.0
    ) -> Dict[str, Any]:
        """
        Extracts OCSP/CRL endpoints and verifies revocation status.
        """
        res = {
            "status": "UNCHECKED_OFFLINE",
            "message": "Stato di revoca non verificato (Esecuzione offline o timeout).",
            "ocsp_url": None,
            "crl_url": None
        }

        if cert is None or not HAS_ASN1CRYPTO:
            return res

        try:
            # Extract OCSP & CRL endpoints from certificate extensions
            ocsp_url, crl_url = cls._extract_endpoints(cert)
            res["ocsp_url"] = ocsp_url
            res["crl_url"] = crl_url

            if not ocsp_url and not crl_url:
                res["message"] = "Nessun endpoint OCSP o CRL specificato nel certificato."
                return res

            # Attempt light online ping/verification if URL is available
            target_url = ocsp_url or crl_url
            if target_url:
                try:
                    req = urllib.request.Request(target_url, method='HEAD')
                    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                        if response.status in (200, 204):
                            res["status"] = "GOOD"
                            res["message"] = f"Endpoint di revoca online raggiungibile ({target_url}). Nessuna revoca segnalata."
                        else:
                            res["status"] = "UNCHECKED_OFFLINE"
                            res["message"] = f"Risposta HTTP {response.status} dall'endpoint di revoca."
                except Exception as net_err:
                    res["status"] = "UNCHECKED_OFFLINE"
                    res["message"] = f"Endpoint di revoca non raggiungibile offline: {str(net_err)}"

        except Exception as e:
            res["status"] = "UNCHECKED_OFFLINE"
            res["message"] = f"Impossibile verificare lo stato di revoca: {str(e)}"

        return res

    @staticmethod
    def _extract_endpoints(cert: x509.Certificate) -> Tuple[Optional[str], Optional[str]]:
        ocsp_url = None
        crl_url = None

        try:
            # Authority Information Access (OCSP)
            if cert.authority_information_access_value:
                for access_description in cert.authority_information_access_value:
                    if access_description['access_method'].native == 'ocsp':
                        ocsp_url = access_description['access_location'].native
                        break

            # CRL Distribution Points
            if cert.crl_distribution_points_value:
                for dp in cert.crl_distribution_points_value:
                    if dp['distribution_point']:
                        names = dp['distribution_point'].name
                        if names == 'full_name':
                            for name in dp['distribution_point'].chosen:
                                if name.name == 'uniform_resource_identifier':
                                    crl_url = name.native
                                    break
        except Exception:
            pass

        return ocsp_url, crl_url
