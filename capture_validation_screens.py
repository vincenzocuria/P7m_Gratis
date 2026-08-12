"""
Headless / Offscreen PySide6 screenshot generator for P7M Viewer PA validation suite.
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from p7m_viewer import P7MViewerWindow

def capture():
    app = QApplication.instance() or QApplication(sys.argv)
    win = P7MViewerWindow()
    win.resize(1280, 850)
    win.show()

    def process_samples():
        sample_path = os.path.abspath("samples/determina_142.pdf.p7m")
        if os.path.exists(sample_path):
            win.load_file(sample_path)
            app.processEvents()
            
            # Save screenshot of new Validation Dashboard
            screen_file = os.path.abspath("samples/validation_dashboard_pdf.png")
            pix = win.grab()
            pix.save(screen_file)
            print(f"[OK] Visual screenshot captured: {screen_file}")

        app.quit()

    QTimer.singleShot(1000, process_samples)
    app.exec()

if __name__ == "__main__":
    capture()
