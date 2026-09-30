import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from p7m_viewer import P7MViewerWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("P7M Viewer PA")
    app.setOrganizationName("Antigravity PA")

    icon_path = os.path.join(os.path.dirname(__file__), "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from self_test import run
        sys.exit(run(app, sys.argv[2]))

    initial_file = None
    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if os.path.exists(candidate):
            initial_file = candidate

    window = P7MViewerWindow(initial_file=initial_file)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

