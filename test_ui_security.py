import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import hashlib
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QTimer, QSettings
from p7m_viewer import P7MViewerWindow, UpdateCheckerThread, UpdateDownloadThread, GITHUB_REPO
from p7m_decoder import P7MDecoder


class Response:
    status = 200
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.headers = {'content-length': str(len(data))}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size=-1):
        if size < 0: return self.data
        result = self.data[self.offset:self.offset + size]
        self.offset += len(result)
        return result


class UISecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._settings_dir = tempfile.TemporaryDirectory()
        self.window = P7MViewerWindow()
        self.window.settings = QSettings(os.path.join(self._settings_dir.name, "test.ini"), QSettings.IniFormat)
        self.window.check_for_updates = lambda *a, **kw: None

    def tearDown(self):
        self.window.close()
        QTest.qWait(20)
        self._settings_dir.cleanup()

    def display(self, result):
        self.window._latest_load = 'test'
        self.window._display_file('test', result)

    def test_unsigned_document_has_no_green_verdict(self):
        self.display(P7MDecoder.decode_file(b'%PDF-1.4\n%%EOF'))
        self.assertIn('NON VERIFICATA', self.window.lbl_badge_text.text())
        self.assertIn('Non verificata', self.window.val_crypto.text())

    def test_bad_second_signer_affects_document(self):
        r = P7MDecoder.decode_file('samples/determina_142.pdf.p7m')
        bad = dict(r['signer_info'], crypto_valid=False)
        r['all_signers'].append(bad)
        self.display(r)
        self.assertIn('NON VALIDA', self.window.lbl_badge_text.text())

    def test_revoked_second_signer_affects_document(self):
        r = P7MDecoder.decode_file('samples/determina_142.pdf.p7m')
        r['all_signers'].append(dict(r['signer_info'], revocation_status='REVOKED'))
        self.display(r)
        self.assertIn('REVOCATO', self.window.lbl_badge_text.text())

    def test_decoder_does_not_block_event_loop(self):
        r = P7MDecoder.decode_file('samples/determina_142.pdf.p7m')
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        def slow(*args, **kwargs):
            time.sleep(0.15)
            return r
        with patch.object(P7MDecoder, 'decode_file', side_effect=slow):
            self.window.load_file('samples/determina_142.pdf.p7m')
            QTest.qWait(300)
        timer.stop()
        self.assertGreater(len(ticks), 5)
        self.assertIsNotNone(self.window.current_data)
        self.assertFalse(self.window._load_threads)

    def test_updater_selects_only_installer_and_digest(self):
        url = f'https://github.com/{GITHUB_REPO}/releases/download/v9.0.0/P7MViewer_Setup.exe'
        data = {'tag_name': 'v9.0.0', 'assets': [
            {'name': 'P7MViewer.exe', 'browser_download_url': 'wrong'},
            {'name': 'P7MViewer_Setup.exe', 'browser_download_url': url, 'digest': 'sha256:' + 'a'*64}]}
        checker = UpdateCheckerThread()
        found = []
        checker.update_found.connect(lambda *args: found.append(args))
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(data).encode())):
            checker.run()
        self.assertEqual(found[0][1], url + '#sha256:' + 'a'*64)

    def test_updater_rejects_missing_digest(self):
        checker = UpdateCheckerThread()
        errors = []
        checker.check_failed.connect(errors.append)
        data = {'tag_name': 'v9.0.0', 'assets': [{'name': 'P7MViewer_Setup.exe', 'browser_download_url': 'bad'}]}
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(data).encode())):
            checker.run()
        self.assertTrue(errors)

    def test_download_checks_digest_before_success(self):
        data = b'MZtest-installer'
        url = f'https://github.com/{GITHUB_REPO}/releases/download/v9.0.0/P7MViewer_Setup.exe'
        for expected, succeeds in [(hashlib.sha256(data).hexdigest(), True), ('a'*64, False)]:
            with tempfile.TemporaryDirectory(dir=".") as folder:
                worker = UpdateDownloadThread(url + '#sha256:' + expected, os.path.join(folder, 'setup.exe'))
                result = []
                worker.download_finished.connect(lambda path: result.append(True))
                worker.download_failed.connect(lambda msg: result.append(False))
                with patch('urllib.request.urlopen', return_value=Response(data)):
                    worker.run()
                self.assertEqual(result, [succeeds])

    def test_prerelease_version_not_installed(self):
        with self.assertRaises(ValueError):
            UpdateCheckerThread._is_newer('v2.2.0-rc1', '2.1.0')


if __name__ == '__main__':
    unittest.main()
