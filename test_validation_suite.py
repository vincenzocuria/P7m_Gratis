import unittest
import os
from p7m_decoder import P7MDecoder
from services.signature.crypto_verifier import CryptoVerifier
from services.signature.trusted_list import TrustedListChecker
from services.signature.revocation import RevocationChecker
from services.signature.timestamp import TimestampValidator


class TestValidationSuite(unittest.TestCase):

    def test_valid_p7m_signature(self):
        filepath = "samples/determina_142.pdf.p7m"
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        signer = res["signer_info"]
        self.assertTrue(signer["crypto_valid"], "Mathematical RSA signature should be valid")
        self.assertTrue(signer["digest_matches"], "Payload hash should match messageDigest attribute")
        self.assertTrue(signer["is_qtsp_qualified"], "QTSP qualification check should pass")

    def test_corrupted_payload_signature_failure(self):
        filepath = "samples/verbale_giunta.txt.p7m"
        with open(filepath, 'rb') as f:
            raw_data = f.read()

        # Decode valid file
        res_valid = P7MDecoder.decode_file(raw_data)
        self.assertTrue(res_valid["signer_info"]["crypto_valid"])

        # Corrupt 1 byte in the middle of payload data
        corrupted_payload = bytearray(res_valid["payload"])
        corrupted_payload[len(corrupted_payload) // 2] ^= 0xFF

        # Verify signature with corrupted payload
        from asn1crypto import cms
        content_info = cms.ContentInfo.load(raw_data)
        signed_data = content_info['content']
        cert = signed_data['certificates'][0].chosen
        sinfo = signed_data['signer_infos'][0]

        crypto_res = CryptoVerifier.verify_signer(sinfo, cert, bytes(corrupted_payload))
        self.assertFalse(crypto_res["digest_matches"], "Payload hash should NOT match messageDigest attribute when corrupted")

    def test_qtsp_checker_known_providers(self):
        self.assertTrue(TrustedListChecker.is_qtsp_qualified("InfoCert Qualified Electronic Signature CA")["is_qualified"])
        self.assertTrue(TrustedListChecker.is_qtsp_qualified("ArubaPEC S.p.A.")["is_qualified"])
        self.assertTrue(TrustedListChecker.is_qtsp_qualified("Namirial CA")["is_qualified"])
        self.assertTrue(TrustedListChecker.is_qtsp_qualified("Poste Italiane EU CA")["is_qualified"])
        self.assertFalse(TrustedListChecker.is_qtsp_qualified("Untrusted Self-Signed Test CA")["is_qualified"])

    def test_revocation_fallback_strategy(self):
        # Graceful offline fallback test
        res = RevocationChecker.check_revocation(None)
        self.assertEqual(res["status"], "UNCHECKED_OFFLINE")


if __name__ == "__main__":
    unittest.main()
