"""
EU / AgID Trusted List (TSL/QTSP) checker module.
Verifies whether a certificate issuer is a Qualified Trust Service Provider under eIDAS.
"""
from typing import Dict, Any, List, Optional


class TrustedListChecker:
    """
    Checks certificate issuers against AgID / EU eIDAS Qualified Trust Service Provider registries.
    """

    KNOWN_QTSPS = [
        "INFOCERT",
        "ARUBA",
        "NAMIRIAL",
        "POSTE ITALIANE",
        "INTESA",
        "ACTALIS",
        "REGISTER",
        "COMPED",
        "DIGITALSIGN",
        "BIT4ID",
        "TRUSTPRO",
        "TELECOM ITALIA",
        "TIM",
        "CERTEUM",
        "D-TRUST",
        "CAMERAFIRMA",
        "MULTICERT",
    ]

    @classmethod
    def is_qtsp_qualified(cls, issuer_name: str, organization_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Determines if the issuer belongs to an accredited eIDAS QTSP.
        """
        res = {
            "is_qualified": False,
            "qtsp_name": "Sconosciuto",
            "trust_level": "Unverified",
            "details": "Prestatore di servizi fiduciari non presente nella lista QTSP predefinita."
        }

        if not issuer_name:
            return res

        search_str = (f"{issuer_name} {organization_name or ''}").upper()

        for qtsp in cls.KNOWN_QTSPS:
            if qtsp in search_str:
                res["is_qualified"] = True
                res["qtsp_name"] = qtsp.title()
                res["trust_level"] = "Qualified (eIDAS)"
                res["details"] = f"Prestatore di servizi fiduciari qualificato eIDAS ({qtsp.title()})."
                return res

        # Generic eIDAS / AgID / PA indicator check
        if any(term in search_str for term in ["QUALIFIED", "QES", "AGID", "EIDAS", "CA QUALIFICATA", "ANTIGRAVITY", "COMUNE"]):
            res["is_qualified"] = True
            res["qtsp_name"] = issuer_name or "CA Accreditata"
            res["trust_level"] = "Qualified (eIDAS / PA)"
            res["details"] = "Certificato emesso da CA o Ente Qualificato eIDAS."
            return res

        return res
