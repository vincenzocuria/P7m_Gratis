import unittest
import os
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

    def test_xml_extraction(self):
        filepath = "samples/fattura_FPA12.xml.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "text/xml")
        self.assertEqual(res["ext"], ".xml")
        self.assertIn(b"FatturaElettronica", res["payload"])

    def test_txt_extraction(self):
        filepath = "samples/verbale_giunta.txt.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "text/plain")
        self.assertEqual(res["ext"], ".txt")
        self.assertIn(b"VERBALE DI DELIBERAZIONE", res["payload"])

    def test_png_extraction(self):
        filepath = "samples/certificato_allegato.png.p7m"
        self.assertTrue(os.path.exists(filepath))
        res = P7MDecoder.decode_file(filepath)
        self.assertTrue(res["success"])
        self.assertEqual(res["mime_type"], "image/png")
        self.assertEqual(res["ext"], ".png")
        self.assertTrue(res["payload"].startswith(b"\x89PNG"))


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

