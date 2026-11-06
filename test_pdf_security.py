import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
import unittest
import tempfile
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter
from PySide6.QtWidgets import QApplication
from p7m_viewer import P7MViewerWindow
from p7m_decoder import P7MDecoder
from services.pdf_security import unlocked_copy
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7


def encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.encrypt('segreto', algorithm='AES-256')
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class PdfSecurityTests(unittest.TestCase):
    def test_unsupported_timestamp_container_has_specific_error(self):
        with tempfile.TemporaryDirectory() as folder:
            for extension in ('tsd', 'm7m'):
                path = os.path.join(folder, 'document.' + extension)
                with open(path, 'wb') as output:
                    output.write(b'unsupported timestamp container %PDF-1.4')
                result = P7MDecoder.decode_file(path)
                self.assertFalse(result['success'])
                self.assertIn('non supportato', result['error'])

    def test_export_removes_encryption_and_preserves_source(self):
        source = encrypted_pdf()
        result = unlocked_copy(source, 'segreto')
        self.assertFalse(PdfReader(BytesIO(result)).is_encrypted)
        self.assertEqual(len(PdfReader(BytesIO(result)).pages), 1)
        self.assertTrue(PdfReader(BytesIO(source)).is_encrypted)
        with self.assertRaises(ValueError):
            unlocked_copy(source, 'errata')

    def test_encrypted_pdf_never_claims_absence_of_signatures(self):
        source = encrypted_pdf()
        result = P7MDecoder.decode_file(source)
        self.assertEqual(result['original_bytes'], source)
        self.assertIn('non verificate', result['signer_info']['signer_name'])

    def test_viewer_retries_password_and_can_cancel(self):
        app = QApplication.instance() or QApplication([])
        with patch.object(P7MViewerWindow, 'check_for_updates'):
            window = P7MViewerWindow()
        try:
            with patch('p7m_viewer.QInputDialog.getText', side_effect=[('errata', True), ('segreto', True)]) as dialog:
                window._render_pdf(encrypted_pdf())
                self.assertEqual(dialog.call_count, 2)
                self.assertEqual(window.pdf_document.pageCount(), 1)
            with patch('p7m_viewer.QInputDialog.getText', return_value=('', False)):
                window._render_pdf(encrypted_pdf())
                self.assertEqual(window.pdf_document.pageCount(), 0)
                self.assertEqual(window.pdf_password, '')
        finally:
            window.close()

    def test_encrypted_pdf_inside_signed_envelope(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(12)
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                .sign(key, hashes.SHA256()))
        source = encrypted_pdf()
        envelope = (pkcs7.PKCS7SignatureBuilder().set_data(source).add_signer(cert, key, hashes.SHA256())
                    .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]))
        result = P7MDecoder.decode_file(envelope)
        self.assertEqual(result['payload'], source)
        self.assertEqual(result['original_bytes'], envelope)
        self.assertTrue(result['signer_info']['crypto_valid'])
        app = QApplication.instance() or QApplication([])
        with patch.object(P7MViewerWindow, 'check_for_updates'):
            window = P7MViewerWindow()
        try:
            window._latest_load = 'test.p7m'
            with patch('p7m_viewer.QInputDialog.getText', return_value=('segreto', True)):
                window._display_file('test.p7m', result)
            self.assertEqual(window.pdf_document.pageCount(), 1)
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, 'saved.p7m')
                with patch('p7m_viewer.QInputDialog.getItem', return_value=('Originale ricevuto', True)), \
                     patch('p7m_viewer.QFileDialog.getSaveFileName', return_value=(path, '')), \
                     patch('p7m_viewer.QMessageBox.information'):
                    window.export_payload()
                with open(path, 'rb') as saved:
                    self.assertEqual(saved.read(), envelope)
        finally:
            window.close()
