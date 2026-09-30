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
        self.assertIsNone(signer["is_qtsp_qualified"], "Names cannot establish qualification")
        self.assertIsNotNone(signer["valid_from"], "Certificate valid_from should be extracted")
        self.assertIsNotNone(signer["valid_to"], "Certificate valid_to should be extracted")
        self.assertFalse(signer["is_expired"], "Sample certificate should be currently valid")

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

    def test_qtsp_names_are_not_evidence(self):
        for name in ("InfoCert", "ArubaPEC", "Namirial", "CA Falsa Comune Test", "Qualified eIDAS", "Untrusted"):
            self.assertIsNone(TrustedListChecker.is_qtsp_qualified(name)["is_qualified"])

    def test_revocation_fallback_strategy(self):
        # Graceful offline fallback test
        res = RevocationChecker.check_revocation(None)
        self.assertEqual(res["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
