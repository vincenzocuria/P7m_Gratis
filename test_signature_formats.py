import base64
import hashlib
import io
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from p7m_decoder import P7MDecoder

DSIG = "http://www.w3.org/2000/09/xmldsig#"
XADES = "http://uri.etsi.org/01903/v1.3.2#"
EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"


def certificate(common_name="MARIO ROSSI"):
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


def sign_detached(key, cert, data):
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(data)
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    )


def build_pades(key, cert, tamper=False, append=b""):
    byte_range = b"[0000000000 0000000000 0000000000 0000000000]"
    contents = b"<" + (b"0" * 8192) + b">"
    pdf = (
        b"%PDF-1.7\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 21 >>\nstream\nBT (Ciao) Tj ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
        b"/ByteRange " + byte_range + b" /Contents " + contents + b" >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    contents_at = pdf.index(contents)
    start2 = contents_at + len(contents)
    updated = f"[{0:010d} {contents_at:010d} {start2:010d} {len(pdf) - start2:010d}]".encode()
    pdf = pdf.replace(byte_range, updated, 1)
    signed = pdf[:contents_at] + pdf[start2:]
    encoded = sign_detached(key, cert, signed).hex().upper().encode()
    if len(encoded) > 8192:
        raise AssertionError("placeholder della firma troppo corto")
    pdf = pdf[:contents_at] + b"<" + encoded + (b"0" * (8192 - len(encoded))) + b">" + pdf[start2:]
    if tamper:
        pdf = pdf[:10] + bytes([pdf[10] ^ 1]) + pdf[11:]
    return pdf + append


def c14n(element):
    from lxml import etree
    return etree.tostring(element, method="c14n", exclusive=True, with_comments=False, inclusive_ns_prefixes=[])


def build_xades(key, cert, text="Contratto n. 12", wrong_cert_digest=False):
    from lxml import etree
    certificate_der = cert.public_bytes(serialization.Encoding.DER)
    cert_digest = base64.b64encode(hashlib.sha256(certificate_der).digest()).decode()
    if wrong_cert_digest:
        cert_digest = base64.b64encode(b"\x00" * 32).decode()
    root = etree.Element("Fattura", nsmap={None: "urn:test"})
    etree.SubElement(root, "Documento").text = text
    signature = etree.SubElement(root, "{%s}Signature" % DSIG, nsmap={"ds": DSIG})
    signed_info = etree.SubElement(signature, "{%s}SignedInfo" % DSIG)
    etree.SubElement(signed_info, "{%s}CanonicalizationMethod" % DSIG, Algorithm=EXC)
    etree.SubElement(signed_info, "{%s}SignatureMethod" % DSIG, Algorithm=RSA_SHA256)
    document_ref = etree.SubElement(signed_info, "{%s}Reference" % DSIG, URI="")
    transforms = etree.SubElement(document_ref, "{%s}Transforms" % DSIG)
    etree.SubElement(transforms, "{%s}Transform" % DSIG, Algorithm=ENVELOPED)
    etree.SubElement(transforms, "{%s}Transform" % DSIG, Algorithm=EXC)
    etree.SubElement(document_ref, "{%s}DigestMethod" % DSIG, Algorithm=SHA256)
    document_digest = etree.SubElement(document_ref, "{%s}DigestValue" % DSIG)
    props_ref = etree.SubElement(
        signed_info, "{%s}Reference" % DSIG, URI="#signed-props",
        Type="http://uri.etsi.org/01903#SignedProperties",
    )
    props_transforms = etree.SubElement(props_ref, "{%s}Transforms" % DSIG)
    etree.SubElement(props_transforms, "{%s}Transform" % DSIG, Algorithm=EXC)
    etree.SubElement(props_ref, "{%s}DigestMethod" % DSIG, Algorithm=SHA256)
    props_digest = etree.SubElement(props_ref, "{%s}DigestValue" % DSIG)
    etree.SubElement(signature, "{%s}SignatureValue" % DSIG)
    key_info = etree.SubElement(signature, "{%s}KeyInfo" % DSIG)
    x509_data = etree.SubElement(key_info, "{%s}X509Data" % DSIG)
    x509_cert = etree.SubElement(x509_data, "{%s}X509Certificate" % DSIG)
    x509_cert.text = base64.b64encode(certificate_der).decode()
    obj = etree.SubElement(signature, "{%s}Object" % DSIG)
    qualifying = etree.SubElement(obj, "{%s}QualifyingProperties" % XADES, nsmap={"xades": XADES})
    signed_props = etree.SubElement(qualifying, "{%s}SignedProperties" % XADES, Id="signed-props")
    signed_signature = etree.SubElement(signed_props, "{%s}SignedSignatureProperties" % XADES)
    signing_cert = etree.SubElement(signed_signature, "{%s}SigningCertificate" % XADES)
    cert_node = etree.SubElement(signing_cert, "{%s}Cert" % XADES)
    cert_digest_node = etree.SubElement(cert_node, "{%s}CertDigest" % XADES)
    etree.SubElement(cert_digest_node, "{%s}DigestMethod" % DSIG, Algorithm=SHA256)
    etree.SubElement(cert_digest_node, "{%s}DigestValue" % DSIG).text = cert_digest

    parent = signature.getparent()
    index = list(parent).index(signature)
    parent.remove(signature)
    document_digest.text = base64.b64encode(hashlib.sha256(c14n(root)).digest()).decode()
    parent.insert(index, signature)
    props_digest.text = base64.b64encode(hashlib.sha256(c14n(signed_props)).digest()).decode()
    signature_value = signature.find("{%s}SignatureValue" % DSIG)
    signature_value.text = base64.b64encode(
        key.sign(c14n(signed_info), padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def build_asic(key, cert, content=b"nota di prova", manifest=False, tamper=False):
    stored = content + b"!" if tamper else content
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        profile = "application/vnd.etsi.asic-e+zip" if manifest else "application/vnd.etsi.asic-s+zip"
        archive.writestr(info, profile)
        archive.writestr("nota.txt", stored)
        if manifest:
            digest = base64.b64encode(hashlib.sha256(content).digest()).decode()
            manifest_bytes = (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<asic:ASiCManifest xmlns:asic=\"http://uri.etsi.org/02918/v1.2.1#\">"
                "<asic:SigReference URI=\"META-INF/signature.p7s\" MimeType=\"application/pkcs7-signature\"/>"
                "<asic:DataObjectReference URI=\"nota.txt\">"
                "<ds:DigestMethod xmlns:ds=\"http://www.w3.org/2000/09/xmldsig#\" Algorithm=\"http://www.w3.org/2001/04/xmlenc#sha256\"/>"
                "<ds:DigestValue xmlns:ds=\"http://www.w3.org/2000/09/xmldsig#\">" + digest + "</ds:DigestValue>"
                "</asic:DataObjectReference></asic:ASiCManifest>"
            ).encode()
            archive.writestr("META-INF/ASiCManifest001.xml", manifest_bytes)
            archive.writestr("META-INF/signature.p7s", sign_detached(key, cert, manifest_bytes))
        else:
            archive.writestr("META-INF/signature.p7s", sign_detached(key, cert, content))
    return buf.getvalue()


class SignatureFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key, cls.cert = certificate()

    def test_pades_signature_covers_the_pdf(self):
        result = P7MDecoder.decode_file(build_pades(self.key, self.cert))
        self.assertTrue(result["success"], result.get("error"))
        self.assertEqual(result["signature_format"], "PAdES")
        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertTrue(result["signer_info"]["crypto_valid"], result["signer_info"].get("validation_error"))
        self.assertTrue(result["signer_info"]["digest_matches"])
        self.assertEqual(result["signer_info"]["signer_name"], "MARIO ROSSI")

    def test_pades_rejects_a_changed_byte(self):
        result = P7MDecoder.decode_file(build_pades(self.key, self.cert, tamper=True))
        self.assertTrue(result["success"])
        self.assertFalse(result["signer_info"]["digest_matches"])

    def test_pades_does_not_accept_a_byte_range_shorter_than_the_file(self):
        result = P7MDecoder.decode_file(build_pades(self.key, self.cert, append=b"\n%modifica"))
        self.assertTrue(result["success"])
        self.assertIsNone(result["signer_info"]["crypto_valid"])
        self.assertIn("ByteRange", result["signer_info"]["validation_error"])

    def test_xades_signature_is_verified(self):
        result = P7MDecoder.decode_file(build_xades(self.key, self.cert))
        self.assertTrue(result["success"], result.get("error"))
        self.assertEqual(result["signature_format"], "XAdES")
        self.assertEqual(result["ext"], ".xml")
        self.assertTrue(result["signer_info"]["crypto_valid"], result["signer_info"].get("validation_error"))
        self.assertTrue(result["signer_info"]["digest_matches"])
        self.assertEqual(result["signer_info"]["signer_name"], "MARIO ROSSI")

    def test_xades_rejects_changed_text_and_wrong_certificate_digest(self):
        signed = build_xades(self.key, self.cert)
        changed = signed.replace(b"Contratto n. 12", b"Contratto n. 99")
        result = P7MDecoder.decode_file(changed)
        self.assertFalse(result["signer_info"]["digest_matches"])
        mismatched = P7MDecoder.decode_file(build_xades(self.key, self.cert, wrong_cert_digest=True))
        self.assertFalse(mismatched["signer_info"]["crypto_valid"])

    def test_asic_s_and_asic_e(self):
        simple = P7MDecoder.decode_file(build_asic(self.key, self.cert))
        self.assertTrue(simple["success"], simple.get("error"))
        self.assertEqual(simple["signature_format"], "ASiC-S")
        self.assertEqual(simple["suggested_filename"], "nota.txt")
        self.assertTrue(simple["signer_info"]["crypto_valid"], simple["signer_info"].get("validation_error"))
        self.assertTrue(simple["signer_info"]["digest_matches"])

        tampered = P7MDecoder.decode_file(build_asic(self.key, self.cert, tamper=True))
        self.assertFalse(tampered["signer_info"]["digest_matches"])

        extended = P7MDecoder.decode_file(build_asic(self.key, self.cert, manifest=True))
        self.assertEqual(extended["signature_format"], "ASiC-E")
        self.assertTrue(extended["signer_info"]["crypto_valid"], extended["signer_info"].get("validation_error"))
        self.assertTrue(extended["signer_info"]["digest_matches"])

        extended_tampered = P7MDecoder.decode_file(build_asic(self.key, self.cert, manifest=True, tamper=True))
        self.assertFalse(extended_tampered["signer_info"]["digest_matches"])

    def test_plain_zip_is_not_an_asic_container(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("nota.txt", b"senza firma")
        result = P7MDecoder.decode_file(buf.getvalue())
        self.assertFalse(result["success"])

    def test_detached_p7s_uses_the_original_document(self):
        document = b"%PDF-1.4\nCiao\n%%EOF"
        signature = sign_detached(self.key, self.cert, document)
        missing = P7MDecoder.decode_file(signature)
        self.assertFalse(missing["success"])
        self.assertTrue(missing["needs_detached_content"])

        opened = P7MDecoder.decode_file(signature, detached_content=document)
        self.assertTrue(opened["success"], opened.get("error"))
        self.assertEqual(opened["signature_format"], "CAdES detached")
        self.assertTrue(opened["signer_info"]["crypto_valid"], opened["signer_info"].get("validation_error"))
        self.assertTrue(opened["signer_info"]["digest_matches"])
        self.assertEqual(opened["payload"], document)

        with tempfile.TemporaryDirectory() as folder:
            document_path = os.path.join(folder, "Contratto n. 12.pdf")
            signature_path = document_path + ".p7s"
            with open(document_path, "wb") as handle:
                handle.write(document)
            with open(signature_path, "wb") as handle:
                handle.write(signature)
            named = P7MDecoder.decode_file(signature_path)
        self.assertTrue(named["success"], named.get("error"))
        self.assertEqual(named["suggested_filename"], "Contratto n. 12.pdf")
        self.assertTrue(named["signer_info"]["digest_matches"])


if __name__ == "__main__":
    unittest.main()
