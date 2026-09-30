"""Issuer names are never proof of eIDAS qualification."""
class TrustedListChecker:
    @classmethod
    def is_qtsp_qualified(cls, issuer_name, organization_name=None):
        return {"is_qualified": None, "qtsp_name": "Non verificato", "trust_level": "Unverified",
                "details": "Qualifica eIDAS non verificata: lista fiduciaria autenticata non disponibile."}
