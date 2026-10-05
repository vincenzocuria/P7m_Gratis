import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from p7m_decoder import P7MDecoder

class TestP7MDecoder(unittest.TestCase):

    def test_pdf_extraction(self):
        filepath = "samples/determina_142.pdf.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"], f"Failed decoding: {res.get('error')}")
        self.assertEqual(res["mime_type"], "application/pdf")
        self.assertEqual(res["ext"], ".pdf")
        self.assertTrue(res["payload"].startswith(b"%PDF-"))
        signer = res["signer_info"]
        self.assertEqual(signer["signer_name"], "MARIO ROSSI")
        self.assertEqual(signer["tax_code"], "RSSMRA80A01H501Z")
        self.assertTrue(signer.get("crypto_valid", False))
        self.assertTrue(signer.get("digest_matches", False))
        self.assertIsNone(signer.get("is_qtsp_qualified"))

    def test_xml_extraction(self):
        filepath = "samples/fattura_FPA12.xml.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "text/xml")
        self.assertEqual(res["ext"], ".xml")
        self.assertIn(b"FatturaElettronica", res["payload"])
        signer = res["signer_info"]
        self.assertTrue(signer.get("crypto_valid", False))
        self.assertTrue(signer.get("digest_matches", False))

    def test_txt_extraction(self):
        filepath = "samples/verbale_giunta.txt.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "text/plain")
        self.assertEqual(res["ext"], ".txt")
        self.assertIn(b"VERBALE DI DELIBERAZIONE", res["payload"])
        signer = res["signer_info"]
        self.assertTrue(signer.get("crypto_valid", False))
        self.assertTrue(signer.get("digest_matches", False))

    def test_png_extraction(self):
        filepath = "samples/certificato_allegato.png.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "image/png")
        self.assertEqual(res["ext"], ".png")
        self.assertTrue(res["payload"].startswith(b"\x89PNG"))
        signer = res["signer_info"]
        self.assertTrue(signer.get("crypto_valid", False))
        self.assertTrue(signer.get("digest_matches", False))

    def test_nested_envelopes_open_inner_document(self):
        pdf = b"%PDF-1.4\n%%EOF"
        inner = _sign(pdf, "INNER SIGNER")
        outer = _sign(inner, "OUTER SIGNER")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Stato Finale PDF.p7m.p7m")
            with open(path, "wb") as handle:
                handle.write(outer)
            res = P7MDecoder.decode_file(path)

        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["mime_type"], "application/pdf")
        self.assertEqual(res["ext"], ".pdf")
        self.assertEqual(res["payload"], pdf)
        self.assertTrue(res["payload"].startswith(b"%PDF-"))
        self.assertEqual(res["suggested_filename"], "Stato Finale PDF.pdf")
        self.assertEqual(len(res["all_signers"]), 2)
        self.assertEqual(
            [signer["signer_name"] for signer in res["all_signers"]],
            ["OUTER SIGNER", "INNER SIGNER"],
        )
        self.assertEqual(res["signer_info"]["signer_name"], "OUTER SIGNER")
        for signer in res["all_signers"]:
            self.assertTrue(signer.get("crypto_valid"))
            self.assertTrue(signer.get("digest_matches"))

    def test_too_many_nested_envelopes(self):
        key, cert = _key_and_cert("NESTED SIGNER")
        data = b"verbale"
        for _ in range(P7MDecoder.MAX_NESTED_ENVELOPES + 1):
            data = _sign(data, cert=cert, key=key)
        res = P7MDecoder.decode_file(data)
        self.assertFalse(res["success"])
        self.assertEqual(res.get("error"), "Troppe buste P7M annidate")
        self.assertNotIn("payload", res)


def _key_and_cert(common_name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _sign(data, common_name=None, cert=None, key=None):
    if cert is None or key is None:
        key, cert = _key_and_cert(common_name or "SIGNER")
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(data)
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )


class TestUpdateChecker(unittest.TestCase):

    def test_version_comparison(self):
        from p7m_viewer import UpdateCheckerThread
        self.assertTrue(UpdateCheckerThread._is_newer("1.0.1", "1.0.0"))
        self.assertTrue(UpdateCheckerThread._is_newer("v1.1.0", "1.0.0"))
        self.assertTrue(UpdateCheckerThread._is_newer("2.0.0", "1.9.9"))
        self.assertFalse(UpdateCheckerThread._is_newer("1.0.0", "1.0.0"))
        self.assertFalse(UpdateCheckerThread._is_newer("0.9.9", "1.0.0"))
        self.assertFalse(UpdateCheckerThread._is_newer("v1.0.0", "1.0.0"))


if __name__ == "__main__":
    unittest.main()

