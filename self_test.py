"""Offline packaged application smoke test: --self-test report.json."""
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from PySide6.QtCore import QEventLoop, QTimer, QSettings
from PySide6.QtGui import QFontDatabase
from p7m_decoder import P7MDecoder
from p7m_viewer import P7MViewerWindow, APP_VERSION


def run(app, report_path):
    if not QFontDatabase.families():
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    report = {'version': APP_VERSION, 'passed': False}
    window = None
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Self-test Comune CA')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
        payload = b'Packaged viewer smoke test'
        raw = (pkcs7.PKCS7SignatureBuilder().set_data(payload).add_signer(cert, key, hashes.SHA256())
               .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary]))
        result = P7MDecoder.decode_file(raw)
        assert result['payload'] == payload
        assert result['signer_info']['crypto_valid'] is True
        assert result['signer_info']['is_qtsp_qualified'] is None
        assert result['signer_info']['revocation_status'] == 'UNKNOWN'
        report['signed_payload'] = True
        plain = P7MDecoder.decode_file(b'%PDF-1.4\n%%EOF')
        assert plain['signer_info']['crypto_valid'] is None
        report['unsigned_payload'] = True
        window = P7MViewerWindow()
        window.settings = QSettings(str(Path(report_path).with_suffix(".ini")), QSettings.IniFormat)
        window.check_for_updates = lambda *a, **kw: None
        window.show()
        window._latest_load = 'unsigned'
        window._display_file('unsigned', plain)
        assert 'NON VERIFICATA' in window.lbl_badge_text.text()
        window._latest_load = 'signed'
        window._display_file('signed', result)
        assert 'CRITTOGRAFICA' in window.lbl_badge_text.text()
        report['gui_verdict'] = True
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / 'test.p7m'
            fixture.write_bytes(raw)
            window.load_file(str(fixture))
            loop = QEventLoop()
            timer = QTimer()
            timer.timeout.connect(lambda: loop.quit() if window.current_data else None)
            timer.start(20)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            timer.stop()
            assert window.current_data and window.current_data['payload'] == payload
            if window._load_threads:
                for worker in list(window._load_threads):
                    worker.wait()
                app.processEvents()
            report['background_decode'] = True
        app.processEvents()
        window.grab().save(str(Path(report_path).with_suffix('.png')))
        report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if window:
            window.close()
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
