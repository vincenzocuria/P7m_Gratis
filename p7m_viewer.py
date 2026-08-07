import sys
import os
import tempfile
import winreg
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, QSize, QUrl, Signal, Slot, QSettings, QRect, QTimer, QThread
from PySide6.QtGui import (
    QIcon, QFont, QPixmap, QImage, QColor, QPalette, QAction, QActionGroup,
    QKeySequence, QDragEnterEvent, QDropEvent, QSyntaxHighlighter,
    QTextCharFormat, QFontMetrics, QClipboard, QCursor, QPainter, QDesktopServices
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QSplitter, QStackedWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QScrollArea, QMessageBox,
    QFrame, QToolBar, QStatusBar, QLineEdit, QGroupBox, QTabWidget,
    QSizePolicy, QFormLayout, QGridLayout, QMenuBar, QMenu, QToolButton
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

# PDF Support
try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    HAS_QTPDF = True
except ImportError:
    HAS_QTPDF = False

from p7m_decoder import P7MDecoder

APP_VERSION = "1.0.0"
GITHUB_REPO = "vincenzocuria/P7m_Gratis"


class UpdateCheckerThread(QThread):
    update_found = Signal(str, str, str)    # version, download_url, release_notes
    no_update_found = Signal(str)           # current_version
    check_failed = Signal(str)              # error_message

    def __init__(self, current_version: str = APP_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        import urllib.request
        import json
        import re

        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        headers = {
            "User-Agent": "P7M-Viewer-PA-Updater",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    tag_name = data.get("tag_name", "").strip()
                    latest_ver = tag_name.lstrip("v")
                    html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
                    notes = data.get("body", "")

                    if self._is_newer(latest_ver, self.current_version):
                        self.update_found.emit(tag_name, html_url, notes)
                    else:
                        self.no_update_found.emit(self.current_version)
                    return
        except Exception:
            # Fallback check on tags endpoint if releases/latest is empty or fails
            try:
                tags_url = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
                req = urllib.request.Request(tags_url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as response:
                    if response.status == 200:
                        tags = json.loads(response.read().decode('utf-8'))
                        if tags and isinstance(tags, list):
                            tag_name = tags[0].get("name", "").strip()
                            latest_ver = tag_name.lstrip("v")
                            html_url = f"https://github.com/{GITHUB_REPO}/releases"
                            if self._is_newer(latest_ver, self.current_version):
                                self.update_found.emit(tag_name, html_url, "")
                                return
                            else:
                                self.no_update_found.emit(self.current_version)
                                return
            except Exception as e:
                self.check_failed.emit(str(e))
                return

            self.check_failed.emit("Nessuna release trovata.")
            return

    @staticmethod
    def _is_newer(latest_str: str, current_str: str) -> bool:
        import re
        def parse_version(v: str):
            parts = re.findall(r'\d+', v)
            return [int(p) for p in parts] if parts else [0]

        return parse_version(latest_str) > parse_version(current_str)


class XMLSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, is_dark: bool = True):
        super().__init__(parent)
        self.is_dark = is_dark
        self.tag_format = QTextCharFormat()
        self.attr_format = QTextCharFormat()
        self.string_format = QTextCharFormat()
        self.comment_format = QTextCharFormat()
        self.tag_format.setFontWeight(QFont.Bold)
        self.comment_format.setFontItalic(True)
        self.update_colors(is_dark)

    def update_colors(self, is_dark: bool):
        self.is_dark = is_dark
        if is_dark:
            self.tag_format.setForeground(QColor("#38bdf8"))   # Cyan 400
            self.attr_format.setForeground(QColor("#f472b6"))  # Pink 400
            self.string_format.setForeground(QColor("#34d399"))# Emerald 400
            self.comment_format.setForeground(QColor("#64748b"))# Slate 500
        else:
            self.tag_format.setForeground(QColor("#0284c7"))   # Cyan 600
            self.attr_format.setForeground(QColor("#d946ef"))  # Fuchsia 600
            self.string_format.setForeground(QColor("#16a34a"))# Green 600
            self.comment_format.setForeground(QColor("#64748b"))# Slate 500
        self.rehighlight()

    def highlightBlock(self, text: str):
        import re
        for match in re.finditer(r'</?[\w:-]+', text):
            self.setFormat(match.start(), match.end() - match.start(), self.tag_format)
        for match in re.finditer(r'\b[\w:-]+(?=\s*=)', text):
            self.setFormat(match.start(), match.end() - match.start(), self.attr_format)
        for match in re.finditer(r'"[^"]*"|\'[^\']*\'', text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)
        for match in re.finditer(r'<!--.*?-->', text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)


class P7MViewerWindow(QMainWindow):
    def __init__(self, initial_file: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("P7M Viewer PA — Material 3 Edition")
        self.resize(1380, 900)
        self.setMinimumSize(960, 660)
        self.setAcceptDrops(True)

        icon_path = os.path.join(os.path.dirname(__file__), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings("Antigravity", "P7MViewerPA")
        self.theme_mode = self.settings.value("theme_mode", "auto")
        self.current_data: Optional[Dict[str, Any]] = None
        self.temp_pdf_file: Optional[str] = None
        self.update_checker: Optional[UpdateCheckerThread] = None

        self._create_menu_bar()
        self._init_ui()
        self._apply_theme()
        self._update_recent_menu()
        self._refresh_welcome_recent_list()

        # Check for updates automatically in background after UI setup
        QTimer.singleShot(2000, lambda: self.check_for_updates(manual=False))

        if initial_file and os.path.exists(initial_file):
            self.load_file(initial_file)

    # --- THEME MANAGEMENT ---
    def _get_effective_theme(self) -> str:
        if self.theme_mode == "light":
            return "light"
        elif self.theme_mode == "dark":
            return "dark"
        else:  # "auto"
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if val == 1 else "dark"
            except Exception:
                return "dark"

    def set_theme_mode(self, mode: str):
        self.theme_mode = mode
        self.settings.setValue("theme_mode", mode)
        self._update_theme_menu_checks()
        self._apply_theme()

    def _update_theme_menu_checks(self):
        if hasattr(self, 'act_theme_light'):
            self.act_theme_light.setChecked(self.theme_mode == "light")
            self.act_theme_dark.setChecked(self.theme_mode == "dark")
            self.act_theme_auto.setChecked(self.theme_mode == "auto")
        
        if hasattr(self, 'btn_theme_quick'):
            if self.theme_mode == "light":
                self.btn_theme_quick.setText("☀️ Chiaro")
            elif self.theme_mode == "dark":
                self.btn_theme_quick.setText("🌙 Scuro")
            else:
                self.btn_theme_quick.setText("💻 Auto")

    # --- RECENT FILES MANAGEMENT ---
    def get_recent_files(self) -> List[str]:
        raw = self.settings.value("recent_files", [])
        if isinstance(raw, str):
            raw = [raw]
        elif not isinstance(raw, list):
            raw = []
        valid_files = [f for f in raw if os.path.exists(f)]
        return valid_files[:10]

    def add_recent_file(self, filepath: str):
        filepath = os.path.abspath(filepath)
        files = self.get_recent_files()
        if filepath in files:
            files.remove(filepath)
        files.insert(0, filepath)
        files = files[:10]
        self.settings.setValue("recent_files", files)
        self._update_recent_menu()
        self._refresh_welcome_recent_list()

    def clear_recent_files(self):
        self.settings.setValue("recent_files", [])
        self._update_recent_menu()
        self._refresh_welcome_recent_list()
        self.lbl_status_msg.setText("Cronologia file recenti svuotata.")

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        # Menu File
        menu_file = menu_bar.addMenu("&File")

        act_open = QAction("📂 Apri File .p7m...", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.open_file_dialog)
        menu_file.addAction(act_open)

        self.menu_recent = menu_file.addMenu("🕒 File Recenti")

        self.act_export = QAction("💾 Esporta Contenuto Originale...", self)
        self.act_export.setShortcut(QKeySequence.Save)
        self.act_export.setEnabled(False)
        self.act_export.triggered.connect(self.export_payload)
        menu_file.addAction(self.act_export)

        self.act_print = QAction("🖨️ Stampa Documento...", self)
        self.act_print.setShortcut(QKeySequence.Print)
        self.act_print.triggered.connect(self.print_current_document)
        menu_file.addAction(self.act_print)

        menu_file.addSeparator()

        act_exit = QAction("🚪 Esci", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Menu Strumenti
        menu_tools = menu_bar.addMenu("&Strumenti")

        # Sottomenu Tema Interfaccia
        menu_theme = menu_tools.addMenu("🎨 Tema Interfaccia")

        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self.act_theme_light = QAction("☀️ Chiaro", self, checkable=True)
        self.act_theme_light.triggered.connect(lambda: self.set_theme_mode("light"))
        theme_group.addAction(self.act_theme_light)
        menu_theme.addAction(self.act_theme_light)

        self.act_theme_dark = QAction("🌙 Scuro", self, checkable=True)
        self.act_theme_dark.triggered.connect(lambda: self.set_theme_mode("dark"))
        theme_group.addAction(self.act_theme_dark)
        menu_theme.addAction(self.act_theme_dark)

        self.act_theme_auto = QAction("💻 Automatico (Sistema)", self, checkable=True)
        self.act_theme_auto.triggered.connect(lambda: self.set_theme_mode("auto"))
        theme_group.addAction(self.act_theme_auto)
        menu_theme.addAction(self.act_theme_auto)

        self._update_theme_menu_checks()

        menu_tools.addSeparator()

        act_assoc = QAction("🔗 Associa Estensione .p7m a Windows...", self)
        act_assoc.setStatusTip("Associa i file .p7m per l'apertura automatica al doppio clic")
        act_assoc.triggered.connect(self.register_association)
        menu_tools.addAction(act_assoc)

        # Menu Help
        menu_help = menu_bar.addMenu("&?")

        act_update = QAction("🔄 Controlla Aggiornamenti...", self)
        act_update.setStatusTip("Verifica se è disponibile una nuova versione su GitHub")
        act_update.triggered.connect(lambda: self.check_for_updates(manual=True))
        menu_help.addAction(act_update)

        menu_help.addSeparator()

        act_info = QAction("ℹ️ Informazioni e Crediti", self)
        act_info.triggered.connect(self.show_info_dialog)
        menu_help.addAction(act_info)

        act_legal = QAction("⚖️ Avviso di Non Validità Legale", self)
        act_legal.triggered.connect(self.show_legal_disclaimer)
        menu_help.addAction(act_legal)

    def _update_recent_menu(self):
        self.menu_recent.clear()
        recent_files = self.get_recent_files()

        if not recent_files:
            no_act = QAction("Nessun file recente", self)
            no_act.setEnabled(False)
            self.menu_recent.addAction(no_act)
            return

        for filepath in recent_files:
            filename = os.path.basename(filepath)
            act = QAction(f"📄  {filename}", self)
            act.setToolTip(filepath)
            act.triggered.connect(lambda checked=False, path=filepath: self.load_file(path))
            self.menu_recent.addAction(act)

        self.menu_recent.addSeparator()
        act_clear = QAction("🗑️  Svuota Cronologia Recenti", self)
        act_clear.triggered.connect(self.clear_recent_files)
        self.menu_recent.addAction(act_clear)

    # --- MAIN UI INITIALIZATION ---
    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 8, 10, 6)
        main_layout.setSpacing(8)

        # --- MATERIAL 3 EXPRESSIVE TOP TOOLBAR ---
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(50)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 4, 12, 4)
        top_layout.setSpacing(10)

        # Brand Title & Icon
        logo_layout = QHBoxLayout()
        logo_layout.setSpacing(8)
        
        logo_icon = QLabel("🛡️")
        logo_icon.setFont(QFont("Segoe UI Emoji", 15))
        
        logo_label = QLabel("P7M Viewer PA")
        logo_label.setObjectName("BrandTitle")

        m3_chip = QLabel(f"v{APP_VERSION} M3")
        m3_chip.setObjectName("M3VersionChip")

        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(m3_chip)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setObjectName("VerticalSeparator")

        btn_open = QPushButton("📂 Apri File")
        btn_open.setObjectName("PrimaryBtn")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(self.open_file_dialog)

        self.btn_export = QPushButton("💾 Esporta Contenuto")
        self.btn_export.setObjectName("SecondaryBtn")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_payload)

        self.btn_print = QPushButton("🖨️ Stampa")
        self.btn_print.setObjectName("SecondaryBtn")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.clicked.connect(self.print_current_document)

        # Quick Theme Switcher Button
        self.btn_theme_quick = QToolButton()
        self.btn_theme_quick.setObjectName("ThemeToolBtn")
        self.btn_theme_quick.setPopupMode(QToolButton.InstantPopup)
        self.btn_theme_quick.setCursor(Qt.PointingHandCursor)

        theme_quick_menu = QMenu(self)
        act_light = theme_quick_menu.addAction("☀️ Chiaro")
        act_light.triggered.connect(lambda: self.set_theme_mode("light"))
        act_dark = theme_quick_menu.addAction("🌙 Scuro")
        act_dark.triggered.connect(lambda: self.set_theme_mode("dark"))
        act_auto = theme_quick_menu.addAction("💻 Automatico")
        act_auto.triggered.connect(lambda: self.set_theme_mode("auto"))
        self.btn_theme_quick.setMenu(theme_quick_menu)

        self._update_theme_menu_checks()

        # Author Badge Tag
        author_tag = QLabel("Vincenzo Curia • Software Gratuito")
        author_tag.setObjectName("AuthorBadge")

        top_layout.addLayout(logo_layout)
        top_layout.addWidget(sep)
        top_layout.addWidget(btn_open)
        top_layout.addWidget(self.btn_export)
        top_layout.addWidget(self.btn_print)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_theme_quick)
        top_layout.addWidget(author_tag)

        main_layout.addWidget(top_bar)

        # --- MAIN WORKSPACE SPLITTER ---
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("MainSplitter")

        # === LEFT SIDEBAR ===
        self.sidebar = QWidget()
        self.sidebar.setObjectName("SidebarWidget")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        sidebar_layout.setSpacing(10)

        # Status Banner Badge
        self.status_badge = QFrame()
        self.status_badge.setObjectName("StatusBadgeNeutral")
        badge_layout = QVBoxLayout(self.status_badge)
        badge_layout.setContentsMargins(10, 10, 10, 10)
        badge_layout.setSpacing(3)
        
        self.lbl_badge_text = QLabel("Nessun file caricato")
        self.lbl_badge_text.setAlignment(Qt.AlignCenter)
        self.lbl_badge_text.setObjectName("BadgeTitle")

        self.lbl_badge_sub = QLabel("Trascina qui un file .p7m oppure selezionalo dai recenti")
        self.lbl_badge_sub.setAlignment(Qt.AlignCenter)
        self.lbl_badge_sub.setObjectName("BadgeSubtitle")
        self.lbl_badge_sub.setWordWrap(True)

        badge_layout.addWidget(self.lbl_badge_text)
        badge_layout.addWidget(self.lbl_badge_sub)

        sidebar_layout.addWidget(self.status_badge)

        # Key-Value Info Card
        self.card_info = QFrame()
        self.card_info.setObjectName("InfoCard")
        card_layout = QVBoxLayout(self.card_info)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(10)

        section_sig = QLabel("📋 DETTAGLI FIRMA DIGITALE")
        section_sig.setObjectName("SectionHeader")
        card_layout.addWidget(section_sig)

        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(8)

        row = 0
        def add_info_row(label_text, value_widget):
            nonlocal row
            lbl = QLabel(label_text)
            lbl.setObjectName("FieldLabel")
            grid.addWidget(lbl, row, 0, Qt.AlignTop | Qt.AlignLeft)
            grid.addWidget(value_widget, row, 1, Qt.AlignTop | Qt.AlignLeft)
            row += 1

        self.val_signer = QLabel("-")
        self.val_signer.setObjectName("FieldValueBold")
        self.val_signer.setWordWrap(True)
        add_info_row("Firmatario:", self.val_signer)

        self.val_taxcode = QLabel("-")
        self.val_taxcode.setObjectName("FieldValueMono")
        add_info_row("Cod. Fiscale:", self.val_taxcode)

        self.val_org = QLabel("-")
        self.val_org.setObjectName("FieldValue")
        self.val_org.setWordWrap(True)
        add_info_row("Ente / Azienda:", self.val_org)

        self.val_issuer = QLabel("-")
        self.val_issuer.setObjectName("FieldValue")
        self.val_issuer.setWordWrap(True)
        add_info_row("Emesso da CA:", self.val_issuer)

        self.val_validity = QLabel("-")
        self.val_validity.setObjectName("FieldValue")
        self.val_validity.setWordWrap(True)
        add_info_row("Validità:", self.val_validity)

        card_layout.addLayout(grid)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setObjectName("HorizontalSeparator")
        card_layout.addWidget(div)

        section_doc = QLabel("📄 DOCUMENTO ESTRATTO")
        section_doc.setObjectName("SectionHeader")
        card_layout.addWidget(section_doc)

        grid_doc = QGridLayout()
        grid_doc.setVerticalSpacing(6)
        grid_doc.setHorizontalSpacing(8)

        self.val_inner_name = QLabel("-")
        self.val_inner_name.setObjectName("FieldValueBold")
        self.val_inner_name.setWordWrap(True)
        lbl_in = QLabel("Nome File:")
        lbl_in.setObjectName("FieldLabel")
        grid_doc.addWidget(lbl_in, 0, 0)
        grid_doc.addWidget(self.val_inner_name, 0, 1)

        self.val_mime = QLabel("-")
        self.val_mime.setObjectName("FieldValueTag")
        lbl_mi = QLabel("Formato:")
        lbl_mi.setObjectName("FieldLabel")
        grid_doc.addWidget(lbl_mi, 1, 0)
        grid_doc.addWidget(self.val_mime, 1, 1)

        self.val_size = QLabel("-")
        self.val_size.setObjectName("FieldValue")
        lbl_sz = QLabel("Dimensione:")
        lbl_sz.setObjectName("FieldLabel")
        grid_doc.addWidget(lbl_sz, 2, 0)
        grid_doc.addWidget(self.val_size, 2, 1)

        card_layout.addLayout(grid_doc)

        sha_box = QVBoxLayout()
        sha_box.setSpacing(3)
        lbl_sha_title = QLabel("Hash SHA-256 Contenuto:")
        lbl_sha_title.setObjectName("FieldLabel")
        self.val_hash = QLabel("-")
        self.val_hash.setObjectName("HashText")
        self.val_hash.setWordWrap(True)
        self.val_hash.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sha_box.addWidget(lbl_sha_title)
        sha_box.addWidget(self.val_hash)

        card_layout.addLayout(sha_box)
        sidebar_layout.addWidget(self.card_info)

        # Disclaimer Card
        disc_frame = QFrame()
        disc_frame.setObjectName("LegalDisclaimer")
        disc_layout = QVBoxLayout(disc_frame)
        disc_layout.setContentsMargins(10, 8, 10, 8)
        lbl_disc = QLabel("⚖️ <b>A scopo informativo:</b> Software di consultazione rapida del contenitore P7M. Non effettua controllo liste di revoca CRL/OCSP.")
        lbl_disc.setWordWrap(True)
        lbl_disc.setObjectName("DisclaimerText")
        disc_layout.addWidget(lbl_disc)

        sidebar_layout.addWidget(disc_frame)
        sidebar_layout.addStretch()

        self.splitter.addWidget(self.sidebar)

        # === RIGHT PREVIEW WORKSPACE (QStackedWidget) ===
        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("ViewStack")

        # Page 0: Welcome Dashboard & Recent Files
        welcome_page = self._create_welcome_page()
        self.view_stack.addWidget(welcome_page)

        # Page 1: PDF Viewer
        self.pdf_page = QWidget()
        pdf_layout = QVBoxLayout(self.pdf_page)
        pdf_layout.setContentsMargins(4, 4, 4, 4)
        pdf_layout.setSpacing(4)

        pdf_toolbar = QHBoxLayout()
        pdf_toolbar.setContentsMargins(4, 2, 4, 2)
        lbl_pdf_title = QLabel("📄 Anteprima Documento PDF")
        lbl_pdf_title.setObjectName("PreviewHeader")

        btn_pdf_zoom_in = QPushButton("🔍 Zoom +")
        btn_pdf_zoom_out = QPushButton("🔍 Zoom -")
        btn_pdf_fit = QPushButton("↔️ Adatta Larghezza")
        btn_pdf_zoom_in.setObjectName("ControlBtn")
        btn_pdf_zoom_out.setObjectName("ControlBtn")
        btn_pdf_fit.setObjectName("ControlBtn")
        btn_pdf_zoom_in.setCursor(Qt.PointingHandCursor)
        btn_pdf_zoom_out.setCursor(Qt.PointingHandCursor)
        btn_pdf_fit.setCursor(Qt.PointingHandCursor)

        btn_pdf_zoom_in.clicked.connect(lambda: self._zoom_pdf(1.2))
        btn_pdf_zoom_out.clicked.connect(lambda: self._zoom_pdf(0.8))
        btn_pdf_fit.clicked.connect(self._fit_pdf)

        pdf_toolbar.addWidget(lbl_pdf_title)
        pdf_toolbar.addStretch()
        pdf_toolbar.addWidget(btn_pdf_zoom_in)
        pdf_toolbar.addWidget(btn_pdf_zoom_out)
        pdf_toolbar.addWidget(btn_pdf_fit)
        pdf_layout.addLayout(pdf_toolbar)

        if HAS_QTPDF:
            self.pdf_document = QPdfDocument(self)
            self.pdf_view = QPdfView(self)
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            pdf_layout.addWidget(self.pdf_view)
        else:
            lbl_no_pdf = QLabel("Visualizzatore PDF Qt non disponibile su questo sistema.")
            lbl_no_pdf.setAlignment(Qt.AlignCenter)
            pdf_layout.addWidget(lbl_no_pdf)
        self.view_stack.addWidget(self.pdf_page)

        # Page 2: XML Viewer
        self.xml_page = QTabWidget()
        self.xml_page.setObjectName("XmlTabWidget")
        
        self.xml_text_edit = QTextEdit()
        self.xml_text_edit.setReadOnly(True)
        self.xml_text_edit.setFont(QFont("Consolas", 10))
        self.highlighter = XMLSyntaxHighlighter(self.xml_text_edit.document(), is_dark=(self._get_effective_theme() == "dark"))
        self.xml_page.addTab(self.xml_text_edit, "📜 Testo XML Formattato")

        self.xml_tree = QTreeWidget()
        self.xml_tree.setHeaderLabels(["Nodo / Attributo XML", "Valore Contenuto"])
        self.xml_tree.setColumnWidth(0, 380)
        self.xml_page.addTab(self.xml_tree, "🌳 Albero Strutturato XML")

        self.view_stack.addWidget(self.xml_page)

        # Page 3: Plain Text / JSON / HTML
        self.txt_page = QWidget()
        txt_layout = QVBoxLayout(self.txt_page)
        txt_layout.setContentsMargins(4, 4, 4, 4)
        self.txt_edit = QTextEdit()
        self.txt_edit.setReadOnly(True)
        self.txt_edit.setFont(QFont("Consolas", 10))
        txt_layout.addWidget(self.txt_edit)
        self.view_stack.addWidget(self.txt_page)

        # Page 4: Image Viewer
        self.img_page = QScrollArea()
        self.img_page.setWidgetResizable(True)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_page.setWidget(self.img_label)
        self.view_stack.addWidget(self.img_page)

        # Page 5: Generic Binary
        self.binary_page = QWidget()
        bin_layout = QVBoxLayout(self.binary_page)
        bin_layout.setAlignment(Qt.AlignCenter)
        self.lbl_binary_info = QLabel("File binario generico")
        self.lbl_binary_info.setObjectName("BinaryTitle")
        self.lbl_binary_info.setAlignment(Qt.AlignCenter)

        btn_open_external = QPushButton("🚀 Apri con Applicazione Predefinita")
        btn_open_external.setObjectName("PrimaryBtn")
        btn_open_external.setCursor(Qt.PointingHandCursor)
        btn_open_external.setFixedSize(320, 44)
        btn_open_external.clicked.connect(self.open_payload_externally)

        bin_layout.addWidget(self.lbl_binary_info)
        bin_layout.addSpacing(20)
        bin_layout.addWidget(btn_open_external, alignment=Qt.AlignCenter)
        self.view_stack.addWidget(self.binary_page)

        self.splitter.addWidget(self.view_stack)
        self.splitter.setSizes([320, 1060])
        self.splitter.setCollapsible(0, False)

        main_layout.addWidget(self.splitter)

        # --- MINIMAL COMPACT FOOTER BAR ---
        footer_bar = QFrame()
        footer_bar.setObjectName("FooterBar")
        footer_bar.setFixedHeight(26)
        footer_layout = QHBoxLayout(footer_bar)
        footer_layout.setContentsMargins(10, 1, 10, 1)

        self.lbl_status_msg = QLabel("Pronto")
        self.lbl_status_msg.setObjectName("FooterStatus")

        lbl_footer_credits = QLabel(
            "P7M Viewer PA • Vincenzo Curia | <i>Strumento informativo (senza validità legale formale)</i>"
        )
        lbl_footer_credits.setObjectName("FooterCredits")

        footer_layout.addWidget(self.lbl_status_msg)
        footer_layout.addStretch()
        footer_layout.addWidget(lbl_footer_credits)

        main_layout.addWidget(footer_bar)

    # --- MATERIAL 3 WELCOME DASHBOARD & RECENT FILES HUB ---
    def _create_welcome_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("WelcomeScrollArea")

        container = QWidget()
        container.setObjectName("WelcomeContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        # Hero Banner
        hero_box = QVBoxLayout()
        hero_box.setSpacing(4)
        
        lbl_hero_title = QLabel("Visualizzatore Buste Digitali .P7M")
        lbl_hero_title.setObjectName("HeroTitle")
        
        lbl_hero_sub = QLabel("Estrazione istantanea del contenuto e verifica della struttura dei certificati di firma CAdES / PKCS#7.")
        lbl_hero_sub.setObjectName("HeroSubtitle")
        lbl_hero_sub.setWordWrap(True)

        hero_box.addWidget(lbl_hero_title)
        hero_box.addWidget(lbl_hero_sub)
        layout.addLayout(hero_box)

        # Material 3 Drag & Drop Zone Card
        self.drop_card = QFrame()
        self.drop_card.setObjectName("DropZoneCard")
        drop_layout = QVBoxLayout(self.drop_card)
        drop_layout.setContentsMargins(28, 24, 28, 24)
        drop_layout.setAlignment(Qt.AlignCenter)
        drop_layout.setSpacing(10)

        lbl_drop_icon = QLabel("📂")
        lbl_drop_icon.setFont(QFont("Segoe UI Emoji", 36))
        lbl_drop_icon.setAlignment(Qt.AlignCenter)

        lbl_drop_text = QLabel("Trascina e rilascia qui il tuo file <b>.p7m</b>")
        lbl_drop_text.setObjectName("DropZoneTitle")
        lbl_drop_text.setAlignment(Qt.AlignCenter)

        lbl_drop_sub = QLabel("Oppure seleziona un file firmato dal tuo computer")
        lbl_drop_sub.setObjectName("DropZoneSub")
        lbl_drop_sub.setAlignment(Qt.AlignCenter)

        btn_browse = QPushButton("Sfoglia File .p7m")
        btn_browse.setObjectName("PrimaryPillBtn")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self.open_file_dialog)

        drop_layout.addWidget(lbl_drop_icon)
        drop_layout.addWidget(lbl_drop_text)
        drop_layout.addWidget(lbl_drop_sub)
        drop_layout.addSpacing(4)
        drop_layout.addWidget(btn_browse, alignment=Qt.AlignCenter)

        layout.addWidget(self.drop_card)

        # Recent Files Dashboard Section
        recent_section = QVBoxLayout()
        recent_section.setSpacing(10)

        recent_header = QHBoxLayout()
        lbl_recent_title = QLabel("🕒 File Aperti di Recente")
        lbl_recent_title.setObjectName("RecentSectionHeader")

        self.btn_clear_recent_dash = QPushButton("🗑️ Svuota Cronologia")
        self.btn_clear_recent_dash.setObjectName("GhostBtn")
        self.btn_clear_recent_dash.setCursor(Qt.PointingHandCursor)
        self.btn_clear_recent_dash.clicked.connect(self.clear_recent_files)

        recent_header.addWidget(lbl_recent_title)
        recent_header.addStretch()
        recent_header.addWidget(self.btn_clear_recent_dash)

        recent_section.addLayout(recent_header)

        # Container Widget for Recent Cards
        self.recent_cards_container = QWidget()
        self.recent_cards_layout = QVBoxLayout(self.recent_cards_container)
        self.recent_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_cards_layout.setSpacing(8)

        recent_section.addWidget(self.recent_cards_container)
        layout.addLayout(recent_section)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _refresh_welcome_recent_list(self):
        # Clear previous widgets
        while self.recent_cards_layout.count():
            item = self.recent_cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        recent_files = self.get_recent_files()

        if not recent_files:
            self.btn_clear_recent_dash.setVisible(False)
            empty_card = QFrame()
            empty_card.setObjectName("EmptyRecentCard")
            empty_layout = QHBoxLayout(empty_card)
            empty_layout.setContentsMargins(16, 12, 16, 12)
            lbl_empty = QLabel("Nessun file aperto di recente. I file aperti verranno memorizzati qui per un accesso rapido.")
            lbl_empty.setObjectName("EmptyRecentText")
            empty_layout.addWidget(lbl_empty)
            self.recent_cards_layout.addWidget(empty_card)
            return

        self.btn_clear_recent_dash.setVisible(True)

        for filepath in recent_files:
            filename = os.path.basename(filepath)

            card = QFrame()
            card.setObjectName("RecentFileCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(12)

            file_icon = QLabel("📄")
            file_icon.setFont(QFont("Segoe UI Emoji", 16))

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)

            lbl_name = QLabel(filename)
            lbl_name.setObjectName("RecentFileName")

            lbl_path = QLabel(filepath)
            lbl_path.setObjectName("RecentFilePath")
            lbl_path.setWordWrap(False)

            info_layout.addWidget(lbl_name)
            info_layout.addWidget(lbl_path)

            btn_open_this = QPushButton("Apri File")
            btn_open_this.setObjectName("RecentCardBtn")
            btn_open_this.setCursor(Qt.PointingHandCursor)
            btn_open_this.clicked.connect(lambda checked=False, path=filepath: self.load_file(path))

            card_layout.addWidget(file_icon)
            card_layout.addLayout(info_layout, stretch=1)
            card_layout.addWidget(btn_open_this)

            self.recent_cards_layout.addWidget(card)

    # --- FILE DRAG & DROP & OPEN LOGIC ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if os.path.isfile(filepath):
                self.load_file(filepath)
                break

    def open_file_dialog(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona File Firmato (CAdES / PAdES) o Documento",
            "",
            "File Firmati e Documenti (*.p7m *.p7s *.p7c *.p7b *.pdf *.xml *.txt *.png *.jpg);;Tutti i file (*.*)"
        )
        if filepath:
            self.load_file(filepath)

    def load_file(self, filepath: str):
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "File non trovato", f"Impossibile trovare il file:\n{filepath}")
            self.add_recent_file(filepath)
            return

        self.lbl_status_msg.setText(f"Caricamento {os.path.basename(filepath)}...")
        res = P7MDecoder.decode_file(filepath)

        if not res["success"]:
            QMessageBox.critical(self, "Errore Decodifica P7M", f"Impossibile aprire il file:\n{res.get('error')}")
            self.lbl_status_msg.setText("Errore nell'apertura del file.")
            return

        self.current_data = res
        self.add_recent_file(filepath)

        self.btn_export.setEnabled(True)
        self.act_export.setEnabled(True)

        signer = res["signer_info"]
        if signer.get('is_expired'):
            self.status_badge.setObjectName("StatusBadgeWarning")
            self.lbl_badge_text.setText("⚠️ CERTIFICATO SCADUTO")
            self.lbl_badge_sub.setText("Certificato di firma non più valido alla data odierna")
        else:
            self.status_badge.setObjectName("StatusBadgeSuccess")
            self.lbl_badge_text.setText("✅ FIRMA STRUTTURALMENTE VALIDA")
            self.lbl_badge_sub.setText("Busta CAdES/PKCS#7 estratta correttamente")
        
        self.status_badge.setStyle(self.status_badge.style())

        self.val_signer.setText(signer['signer_name'])
        self.val_taxcode.setText(signer['tax_code'] or "Non specificato")
        self.val_org.setText(signer['organization'] or "Non specificato")
        self.val_issuer.setText(signer['issuer'] or "CA Sconosciuta")
        self.val_validity.setText(f"{signer['valid_from']}\n➔ {signer['valid_to']}")

        self.val_inner_name.setText(res['suggested_filename'])
        self.val_mime.setText(f"{res['ext'].upper()} ({res['mime_type']})")
        self.val_size.setText(f"{res['payload_size']:,} bytes")
        self.val_hash.setText(res['sha256'])

        mime = res["mime_type"]
        payload = res["payload"]

        if mime == "application/pdf" and HAS_QTPDF:
            self._render_pdf(payload)
        elif mime in ("text/xml", "application/xml") or res["ext"] == ".xml":
            self._render_xml(payload)
        elif mime.startswith("image/"):
            self._render_image(payload)
        elif mime in ("text/plain", "application/json", "text/html") or mime.startswith("text/"):
            self._render_text(payload, mime)
        else:
            self._render_binary(res)

        self.lbl_status_msg.setText(f"Documento aperto: {res['suggested_filename']}")

    # --- RENDERERS ---
    def _render_pdf(self, payload: bytes):
        if self.temp_pdf_file and os.path.exists(self.temp_pdf_file):
            try:
                os.remove(self.temp_pdf_file)
            except Exception:
                pass

        fd, self.temp_pdf_file = tempfile.mkstemp(suffix=".pdf")
        os.write(fd, payload)
        os.close(fd)

        self.pdf_document.load(self.temp_pdf_file)
        self.view_stack.setCurrentWidget(self.pdf_page)
        self._fit_pdf()

    def _zoom_pdf(self, factor: float):
        if HAS_QTPDF and hasattr(self, 'pdf_view'):
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            current = self.pdf_view.zoomFactor()
            new_zoom = max(0.2, min(5.0, current * factor))
            self.pdf_view.setZoomFactor(new_zoom)

    def _fit_pdf(self):
        if HAS_QTPDF and hasattr(self, 'pdf_view'):
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def print_current_document(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Stampa Documento")
        if dialog.exec() != QPrintDialog.Accepted:
            return

        current_w = self.view_stack.currentWidget()

        if current_w == self.pdf_page and HAS_QTPDF and hasattr(self, 'pdf_document') and self.pdf_document.pageCount() > 0:
            painter = QPainter(printer)
            num_pages = self.pdf_document.pageCount()
            for i in range(num_pages):
                if i > 0:
                    printer.newPage()
                page_size_pts = self.pdf_document.pagePointSize(i)
                img = self.pdf_document.render(i, QSize(int(page_size_pts.width() * 3), int(page_size_pts.height() * 3)))
                page_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
                scaled_img = img.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                target_rect = QRect(
                    page_rect.left() + (page_rect.width() - scaled_img.width()) // 2,
                    page_rect.top() + (page_rect.height() - scaled_img.height()) // 2,
                    scaled_img.width(),
                    scaled_img.height()
                )
                painter.drawImage(target_rect, scaled_img)
            painter.end()
            self.lbl_status_msg.setText("Stampa PDF inviata alla stampante.")
        elif current_w == self.xml_page:
            self.xml_text_edit.print_(printer)
            self.lbl_status_msg.setText("Stampa XML inviata alla stampante.")
        elif current_w == self.txt_page:
            self.txt_edit.print_(printer)
            self.lbl_status_msg.setText("Stampa Testo inviata alla stampante.")
        elif current_w == self.img_page:
            pixmap = self.img_label.pixmap()
            if pixmap and not pixmap.isNull():
                painter = QPainter(printer)
                page_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
                scaled = pixmap.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(page_rect.left(), page_rect.top(), scaled)
                painter.end()
                self.lbl_status_msg.setText("Stampa Immagine inviata alla stampante.")
        else:
            QMessageBox.information(self, "Stampa non disponibile", "Nessun documento aperto da stampare.")

    def _render_xml(self, payload: bytes):
        try:
            xml_text = payload.decode('utf-8')
        except Exception:
            xml_text = payload.decode('latin-1', errors='replace')

        try:
            elem = ET.fromstring(xml_text)
            ET.indent(elem, space="  ")
            pretty_text = ET.tostring(elem, encoding="unicode")
        except Exception:
            pretty_text = xml_text

        self.xml_text_edit.setPlainText(pretty_text)

        self.xml_tree.clear()
        try:
            root = ET.fromstring(xml_text)
            root_item = QTreeWidgetItem([self._strip_xml_ns(root.tag), root.text.strip() if root.text else ""])
            self._populate_xml_tree(root, root_item)
            self.xml_tree.addTopLevelItem(root_item)
            self.xml_tree.expandItem(root_item)
        except Exception:
            pass

        self.view_stack.setCurrentWidget(self.xml_page)

    def _strip_xml_ns(self, tag: str) -> str:
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag

    def _populate_xml_tree(self, element: ET.Element, parent_item: QTreeWidgetItem):
        is_dark = (self._get_effective_theme() == "dark")
        attr_color = QColor("#f472b6") if is_dark else QColor("#d946ef")

        for k, v in element.attrib.items():
            attr_item = QTreeWidgetItem([f"@{k}", str(v)])
            attr_item.setForeground(0, attr_color)
            parent_item.addChild(attr_item)

        for child in element:
            text = child.text.strip() if child.text else ""
            child_item = QTreeWidgetItem([self._strip_xml_ns(child.tag), text])
            parent_item.addChild(child_item)
            self._populate_xml_tree(child, child_item)

    def _render_text(self, payload: bytes, mime: str):
        try:
            text = payload.decode('utf-8')
        except Exception:
            text = payload.decode('latin-1', errors='replace')

        if mime == "application/json":
            try:
                import json
                obj = json.loads(text)
                text = json.dumps(obj, indent=2, ensure_ascii=False)
            except Exception:
                pass

        self.txt_edit.setPlainText(text)
        self.view_stack.setCurrentWidget(self.txt_page)

    def _render_image(self, payload: bytes):
        pixmap = QPixmap()
        pixmap.loadFromData(payload)
        self.img_label.setPixmap(pixmap)
        self.view_stack.setCurrentWidget(self.img_page)

    def _render_binary(self, res: Dict[str, Any]):
        self.lbl_binary_info.setText(
            f"📦 <b>{res['suggested_filename']}</b><br><br>"
            f"Formato: <b>{res['mime_type']}</b> ({res['payload_size']:,} bytes)<br><br>"
            f"Questo tipo di file non prevede un'anteprima di testo diretta.<br>"
            f"Puoi salvarlo oppure aprirlo direttamente con l'applicazione di sistema."
        )
        self.view_stack.setCurrentWidget(self.binary_page)

    # --- ACTIONS & DIALOGS ---
    def export_payload(self):
        if not self.current_data:
            return
        
        default_name = self.current_data["suggested_filename"]
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Esporta Contenuto Estratto",
            default_name,
            "Tutti i file (*.*)"
        )
        if filepath:
            try:
                with open(filepath, "wb") as f:
                    f.write(self.current_data["payload"])
                QMessageBox.information(self, "Esportazione Completata", f"File salvato con successo in:\n{filepath}")
                self.lbl_status_msg.setText(f"File salvato: {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Errore di Salvataggio", f"Impossibile salvare il file:\n{e}")

    def open_payload_externally(self):
        if not self.current_data:
            return

        fd, temp_path = tempfile.mkstemp(suffix=self.current_data["ext"])
        os.write(fd, self.current_data["payload"])
        os.close(fd)

        try:
            os.startfile(temp_path)
            self.lbl_status_msg.setText(f"Aperto con app predefinita: {temp_path}")
        except Exception as e:
            QMessageBox.warning(self, "Impossibile aprire", f"Errore nell'apertura dell'applicazione predefinita:\n{e}")

    def register_association(self):
        try:
            python_exe = sys.executable
            main_script = os.path.abspath(sys.argv[0])
            cmd = f'"{python_exe}" "{main_script}" "%1"'

            key_ext = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.p7m")
            winreg.SetValue(key_ext, "", winreg.REG_SZ, "P7MViewer.Document")
            winreg.CloseKey(key_ext)

            key_doc = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\P7MViewer.Document")
            winreg.SetValue(key_doc, "", winreg.REG_SZ, "Documento Firmato Digitalmente P7M")
            winreg.CloseKey(key_doc)

            key_shell = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\P7MViewer.Document\shell\open\command")
            winreg.SetValue(key_shell, "", winreg.REG_SZ, cmd)
            winreg.CloseKey(key_shell)

            QMessageBox.information(
                self,
                "Associazione Riuscita",
                "L'estensione .p7m è stata associata a P7M Viewer per l'utente corrente!\n\n"
                "Facendo doppio clic su un file .p7m in Windows Explorer si aprirà automaticamente questo programma."
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore Associazione", f"Impossibile registrare l'estensione nel Registro di Windows:\n{e}")

    # --- UPDATE CHECKING ---
    def check_for_updates(self, manual: bool = False):
        if self.update_checker and self.update_checker.isRunning():
            if manual:
                QMessageBox.information(self, "Controllo in Corso", "Il controllo degli aggiornamenti è già in corso...")
            return

        if manual:
            self.lbl_status_msg.setText("🔍 Controllo aggiornamenti su GitHub...")

        self.update_checker = UpdateCheckerThread(APP_VERSION, self)
        self.update_checker.update_found.connect(lambda ver, url, notes: self._on_update_found(ver, url, notes, manual))
        self.update_checker.no_update_found.connect(lambda ver: self._on_no_update_found(ver, manual))
        self.update_checker.check_failed.connect(lambda err: self._on_update_check_failed(err, manual))
        self.update_checker.start()

    def _on_update_found(self, version: str, url: str, notes: str, manual: bool):
        self.lbl_status_msg.setText(f"🚀 Nuova versione {version} disponibile su GitHub!")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("🚀 Aggiornamento Disponibile")
        msg_box.setIcon(QMessageBox.Information)

        body_text = f"<h3>È disponibile una nuova versione di P7M Viewer PA!</h3>"
        body_text += f"<p><b>Versione attuale:</b> v{APP_VERSION}<br><b>Nuova versione:</b> {version}</p>"
        if notes:
            clean_notes = notes[:400] + "..." if len(notes) > 400 else notes
            body_text += f"<p><b>Note di rilascio:</b><br>{clean_notes}</p>"
        body_text += "<p>Desideri aprire la pagina delle Release su GitHub per scaricare il nuovo installer?</p>"

        msg_box.setText(body_text)
        btn_download = msg_box.addButton("🌐 Scarica Ora (GitHub)", QMessageBox.AcceptRole)
        btn_later = msg_box.addButton("Più Tardi", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_download)

        msg_box.exec()
        if msg_box.clickedButton() == btn_download:
            QDesktopServices.openUrl(QUrl(url))

    def _on_no_update_found(self, version: str, manual: bool):
        if manual:
            self.lbl_status_msg.setText(f"Stai usando l'ultima versione (v{APP_VERSION}).")
            QMessageBox.information(
                self,
                "Nessun Aggiornamento",
                f"<b>P7M Viewer PA è aggiornato!</b><br><br>"
                f"Stai già utilizzando l'ultima versione disponibile (<b>v{APP_VERSION}</b>)."
            )
        else:
            self.lbl_status_msg.setText(f"Pronto — P7M Viewer PA v{APP_VERSION}")

    def _on_update_check_failed(self, error: str, manual: bool):
        if manual:
            self.lbl_status_msg.setText("Errore durante il controllo degli aggiornamenti.")
            QMessageBox.warning(
                self,
                "Errore Controllo Aggiornamenti",
                "Impossibile verificare la presenza di nuovi aggiornamenti su GitHub.<br><br>"
                "Verifica che la tua connessione ad Internet sia attiva."
            )
        else:
            self.lbl_status_msg.setText("Pronto")

    def show_info_dialog(self):
        msg = (
            f"<h2>🛡️ P7M Viewer PA — v{APP_VERSION}</h2>"
            "<p>Software Gratuito per la visualizzazione rapida ed immediata di file firmati digitalmente (.p7m / .p7s).</p>"
            "<p><b>Sviluppato da:</b> Vincenzo Curia</p>"
            "<p><b>Repository GitHub:</b> <a href='https://github.com/vincenzocuria/P7m_Gratis'>https://github.com/vincenzocuria/P7m_Gratis</a></p>"
            "<hr>"
            "<p><b>Funzionalità:</b> Interfaccia Material Design 3 Expressive, Supporto Temi Chiaro/Scuro/Automatico, Gestione File Recenti, Estrazione busta CAdES/PKCS#7, Controllo Aggiornamenti, anteprima PDF vettoriale, XML formattato ad albero, testi ed immagini.</p>"
            "<p style='color: #fbbf24;'><b>Nota Legale:</b> Strumento a solo scopo informativo ed estrattivo del contenuto. Non costituisce né sostituisce una verifica di validità legale formale (verificare CRL/OCSP presso le CA accreditate AgID).</p>"
        )
        QMessageBox.about(self, "Informazioni su P7M Viewer PA", msg)

    def show_legal_disclaimer(self):
        msg = (
            "<h3>⚖️ Avviso di Non Validità Legale</h3>"
            "<p>P7M Viewer PA estrae ed esamina la struttura sintattica del contenitore PKCS#7 / CAdES e ne mostra il contenuto originale ed i metadati del certificato.</p>"
            "<p>Questo software <b>NON possiede valore di giudizio legale formale</b> ai sensi del CAD (Codice dell'Amministrazione Digitale), in quanto non interroga in tempo reale i servizi di verifica della revoca (CRL / OCSP) delle Autorità di Certificazione (CA) accreditate né le marche temporali per la validità con valore di prova legale.</p>"
            "<p>Per le verifiche con valore legale formale si raccomanda l'uso dei software accreditati (ArubaSign, Dike, FirmaOK, ecc.).</p>"
        )
        QMessageBox.warning(self, "Avviso di Non Validità Legale", msg)

    def closeEvent(self, event):
        if self.temp_pdf_file and os.path.exists(self.temp_pdf_file):
            try:
                os.remove(self.temp_pdf_file)
            except Exception:
                pass
        super().closeEvent(event)

    # --- COMPLETE HIGH-CONTRAST MATERIAL DESIGN 3 THEMES (LIGHT & DARK) ---
    def _apply_theme(self):
        eff_theme = self._get_effective_theme()
        is_dark = (eff_theme == "dark")

        if hasattr(self, 'highlighter'):
            self.highlighter.update_colors(is_dark)

        if is_dark:
            c = {
                "window_bg": "#0b0f19",
                "menubar_bg": "#121826",
                "menubar_fg": "#e2e8f0",
                "menubar_border": "#1e293b",
                "menubar_item_sel": "#1e293b",
                "menubar_item_sel_fg": "#38bdf8",
                "menu_bg": "#161e2e",
                "menu_fg": "#e2e8f0",
                "menu_border": "#293548",
                "menu_sel_bg": "#2563eb",
                "menu_sel_fg": "#ffffff",
                "menu_sep": "#293548",
                "topbar_bg": "#121826",
                "topbar_border": "#1e293b",
                "brand_title": "#f8fafc",
                "chip_bg": "#1e293b",
                "chip_fg": "#38bdf8",
                "chip_border": "#334155",
                "separator": "#1e293b",
                "btn_primary_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6)",
                "btn_primary_fg": "#ffffff",
                "btn_primary_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb)",
                "btn_primary_disabled_bg": "#1e293b",
                "btn_primary_disabled_fg": "#64748b",
                "btn_pill_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #4f46e5)",
                "btn_pill_fg": "#ffffff",
                "btn_pill_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #4338ca)",
                "btn_sec_bg": "#1e293b",
                "btn_sec_fg": "#e2e8f0",
                "btn_sec_border": "#334155",
                "btn_sec_hover_bg": "#334155",
                "btn_sec_hover_fg": "#ffffff",
                "btn_sec_disabled_bg": "#0f172a",
                "btn_sec_disabled_fg": "#475569",
                "btn_sec_disabled_border": "#1e293b",
                "author_bg": "#161e2e",
                "author_fg": "#94a3b8",
                "author_border": "#293548",
                "btn_ctrl_bg": "#1e293b",
                "btn_ctrl_fg": "#cbd5e1",
                "btn_ctrl_border": "#334155",
                "btn_ctrl_hover_bg": "#2563eb",
                "btn_ctrl_hover_fg": "#ffffff",
                "btn_ghost_fg": "#94a3b8",
                "btn_ghost_hover_bg": "#1e293b",
                "btn_ghost_hover_fg": "#f8fafc",
                "sidebar_bg": "#0b0f19",
                "sidebar_border": "#1e293b",
                "badge_neutral_bg": "#121826",
                "badge_neutral_border": "#1e293b",
                "badge_neutral_title": "#f8fafc",
                "badge_neutral_sub": "#94a3b8",
                "badge_success_bg": "#064e3b",
                "badge_success_border": "#10b981",
                "badge_success_title": "#34d399",
                "badge_success_sub": "#a7f3d0",
                "badge_warning_bg": "#78350f",
                "badge_warning_border": "#f59e0b",
                "badge_warning_title": "#fbbf24",
                "badge_warning_sub": "#fde68a",
                "card_bg": "#121826",
                "card_border": "#1e293b",
                "disclaimer_bg": "#1e1b4b",
                "disclaimer_border": "#4338ca",
                "disclaimer_fg": "#c7d2fe",
                "section_hdr": "#38bdf8",
                "preview_hdr": "#f8fafc",
                "field_lbl": "#94a3b8",
                "field_val": "#e2e8f0",
                "field_val_bold": "#ffffff",
                "field_val_mono": "#38bdf8",
                "field_val_tag_bg": "#1d4ed8",
                "field_val_tag_fg": "#ffffff",
                "hash_fg": "#64748b",
                "welcome_bg": "#0b0f19",
                "hero_title": "#f8fafc",
                "hero_sub": "#94a3b8",
                "drop_bg": "#121826",
                "drop_border": "#2563eb",
                "drop_hover_bg": "#161e2e",
                "drop_hover_border": "#38bdf8",
                "drop_title": "#f8fafc",
                "drop_sub": "#94a3b8",
                "recent_hdr": "#f8fafc",
                "recent_card_bg": "#121826",
                "recent_card_border": "#1e293b",
                "recent_card_hover_bg": "#161e2e",
                "recent_card_hover_border": "#334155",
                "recent_name": "#f8fafc",
                "recent_path": "#64748b",
                "recent_btn_bg": "#1e293b",
                "recent_btn_fg": "#38bdf8",
                "recent_btn_border": "#334155",
                "recent_btn_hover_bg": "#2563eb",
                "recent_btn_hover_fg": "#ffffff",
                "empty_card_bg": "#121826",
                "empty_card_border": "#1e293b",
                "empty_text": "#64748b",
                "binary_title": "#f8fafc",
                "editor_bg": "#0b0f19",
                "editor_fg": "#f1f5f9",
                "editor_border": "#1e293b",
                "tree_item_sel_bg": "#2563eb",
                "tree_item_sel_fg": "#ffffff",
                "header_bg": "#121826",
                "header_fg": "#94a3b8",
                "header_border": "#1e293b",
                "tab_pane_border": "#1e293b",
                "tab_pane_bg": "#0b0f19",
                "tab_bg": "#121826",
                "tab_fg": "#94a3b8",
                "tab_sel_bg": "#2563eb",
                "tab_sel_fg": "#ffffff",
                "footer_bg": "#121826",
                "footer_border": "#1e293b",
                "footer_status": "#38bdf8",
                "footer_credits": "#94a3b8",
                "theme_btn_bg": "#1e293b",
                "theme_btn_fg": "#e2e8f0",
                "theme_btn_border": "#334155",
                "theme_btn_hover_bg": "#334155",
            }
        else:
            c = {
                "window_bg": "#f8fafc",
                "menubar_bg": "#ffffff",
                "menubar_fg": "#0f172a",
                "menubar_border": "#e2e8f0",
                "menubar_item_sel": "#f1f5f9",
                "menubar_item_sel_fg": "#0284c7",
                "menu_bg": "#ffffff",
                "menu_fg": "#0f172a",
                "menu_border": "#cbd5e1",
                "menu_sel_bg": "#2563eb",
                "menu_sel_fg": "#ffffff",
                "menu_sep": "#e2e8f0",
                "topbar_bg": "#ffffff",
                "topbar_border": "#cbd5e1",
                "brand_title": "#0f172a",
                "chip_bg": "#e0f2fe",
                "chip_fg": "#0284c7",
                "chip_border": "#bae6fd",
                "separator": "#cbd5e1",
                "btn_primary_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #1d4ed8)",
                "btn_primary_fg": "#ffffff",
                "btn_primary_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #1e40af)",
                "btn_primary_disabled_bg": "#e2e8f0",
                "btn_primary_disabled_fg": "#94a3b8",
                "btn_pill_bg": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #4338ca)",
                "btn_pill_fg": "#ffffff",
                "btn_pill_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3730a3)",
                "btn_sec_bg": "#f1f5f9",
                "btn_sec_fg": "#1e293b",
                "btn_sec_border": "#cbd5e1",
                "btn_sec_hover_bg": "#e2e8f0",
                "btn_sec_hover_fg": "#0f172a",
                "btn_sec_disabled_bg": "#f8fafc",
                "btn_sec_disabled_fg": "#cbd5e1",
                "btn_sec_disabled_border": "#e2e8f0",
                "author_bg": "#f1f5f9",
                "author_fg": "#475569",
                "author_border": "#cbd5e1",
                "btn_ctrl_bg": "#f1f5f9",
                "btn_ctrl_fg": "#334155",
                "btn_ctrl_border": "#cbd5e1",
                "btn_ctrl_hover_bg": "#2563eb",
                "btn_ctrl_hover_fg": "#ffffff",
                "btn_ghost_fg": "#64748b",
                "btn_ghost_hover_bg": "#f1f5f9",
                "btn_ghost_hover_fg": "#0f172a",
                "sidebar_bg": "#f8fafc",
                "sidebar_border": "#e2e8f0",
                "badge_neutral_bg": "#ffffff",
                "badge_neutral_border": "#cbd5e1",
                "badge_neutral_title": "#0f172a",
                "badge_neutral_sub": "#64748b",
                "badge_success_bg": "#ecfdf5",
                "badge_success_border": "#a7f3d0",
                "badge_success_title": "#047857",
                "badge_success_sub": "#065f46",
                "badge_warning_bg": "#fffbeb",
                "badge_warning_border": "#fde68a",
                "badge_warning_title": "#b45309",
                "badge_warning_sub": "#92400e",
                "card_bg": "#ffffff",
                "card_border": "#cbd5e1",
                "disclaimer_bg": "#e0e7ff",
                "disclaimer_border": "#a5b4fc",
                "disclaimer_fg": "#3730a3",
                "section_hdr": "#0284c7",
                "preview_hdr": "#0f172a",
                "field_lbl": "#64748b",
                "field_val": "#334155",
                "field_val_bold": "#0f172a",
                "field_val_mono": "#0284c7",
                "field_val_tag_bg": "#2563eb",
                "field_val_tag_fg": "#ffffff",
                "hash_fg": "#64748b",
                "welcome_bg": "#f8fafc",
                "hero_title": "#0f172a",
                "hero_sub": "#475569",
                "drop_bg": "#ffffff",
                "drop_border": "#2563eb",
                "drop_hover_bg": "#f1f5f9",
                "drop_hover_border": "#0284c7",
                "drop_title": "#0f172a",
                "drop_sub": "#64748b",
                "recent_hdr": "#0f172a",
                "recent_card_bg": "#ffffff",
                "recent_card_border": "#cbd5e1",
                "recent_card_hover_bg": "#f1f5f9",
                "recent_card_hover_border": "#94a3b8",
                "recent_name": "#0f172a",
                "recent_path": "#64748b",
                "recent_btn_bg": "#f1f5f9",
                "recent_btn_fg": "#0284c7",
                "recent_btn_border": "#cbd5e1",
                "recent_btn_hover_bg": "#2563eb",
                "recent_btn_hover_fg": "#ffffff",
                "empty_card_bg": "#ffffff",
                "empty_card_border": "#cbd5e1",
                "empty_text": "#64748b",
                "binary_title": "#0f172a",
                "editor_bg": "#ffffff",
                "editor_fg": "#0f172a",
                "editor_border": "#cbd5e1",
                "tree_item_sel_bg": "#2563eb",
                "tree_item_sel_fg": "#ffffff",
                "header_bg": "#f1f5f9",
                "header_fg": "#475569",
                "header_border": "#cbd5e1",
                "tab_pane_border": "#cbd5e1",
                "tab_pane_bg": "#ffffff",
                "tab_bg": "#f1f5f9",
                "tab_fg": "#64748b",
                "tab_sel_bg": "#2563eb",
                "tab_sel_fg": "#ffffff",
                "footer_bg": "#f1f5f9",
                "footer_border": "#cbd5e1",
                "footer_status": "#0284c7",
                "footer_credits": "#64748b",
                "theme_btn_bg": "#f1f5f9",
                "theme_btn_fg": "#1e293b",
                "theme_btn_border": "#cbd5e1",
                "theme_btn_hover_bg": "#e2e8f0",
            }

        qss = f"""
            QMainWindow {{
                background-color: {c['window_bg']};
            }}
            
            QMenuBar {{
                background-color: {c['menubar_bg']};
                color: {c['menubar_fg']};
                font-size: 13px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                border-bottom: 1px solid {c['menubar_border']};
                padding: 2px 6px;
            }}
            QMenuBar::item {{
                background-color: transparent;
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QMenuBar::item:selected {{
                background-color: {c['menubar_item_sel']};
                color: {c['menubar_item_sel_fg']};
            }}
            
            QMenu {{
                background-color: {c['menu_bg']};
                color: {c['menu_fg']};
                border: 1px solid {c['menu_border']};
                border-radius: 10px;
                padding: 6px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background-color: {c['menu_sel_bg']};
                color: {c['menu_sel_fg']};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {c['menu_sep']};
                margin: 4px 6px;
            }}

            #TopBar {{
                background-color: {c['topbar_bg']};
                border: 1px solid {c['topbar_border']};
                border-radius: 14px;
            }}
            #BrandTitle {{
                color: {c['brand_title']};
                font-size: 15px;
                font-weight: 700;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            #M3VersionChip {{
                background-color: {c['chip_bg']};
                color: {c['chip_fg']};
                border: 1px solid {c['chip_border']};
                border-radius: 9px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 600;
            }}
            #VerticalSeparator {{
                color: {c['separator']};
                margin: 4px 0px;
            }}
            #HorizontalSeparator {{
                color: {c['separator']};
                margin: 4px 0px;
            }}

            #PrimaryBtn {{
                background: {c['btn_primary_bg']};
                color: {c['btn_primary_fg']};
                border: none;
                border-radius: 16px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 13px;
            }}
            #PrimaryBtn:hover {{
                background: {c['btn_primary_hover']};
            }}
            #PrimaryBtn:disabled {{
                background-color: {c['btn_primary_disabled_bg']};
                color: {c['btn_primary_disabled_fg']};
            }}

            #PrimaryPillBtn {{
                background: {c['btn_pill_bg']};
                color: {c['btn_pill_fg']};
                border: none;
                border-radius: 18px;
                padding: 9px 24px;
                font-weight: 700;
                font-size: 14px;
            }}
            #PrimaryPillBtn:hover {{
                background: {c['btn_pill_hover']};
            }}

            #SecondaryBtn {{
                background-color: {c['btn_sec_bg']};
                color: {c['btn_sec_fg']};
                border: 1px solid {c['btn_sec_border']};
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            #SecondaryBtn:hover {{
                background-color: {c['btn_sec_hover_bg']};
                color: {c['btn_sec_hover_fg']};
            }}
            #SecondaryBtn:disabled {{
                background-color: {c['btn_sec_disabled_bg']};
                color: {c['btn_sec_disabled_fg']};
                border-color: {c['btn_sec_disabled_border']};
            }}

            #ThemeToolBtn {{
                background-color: {c['theme_btn_bg']};
                color: {c['theme_btn_fg']};
                border: 1px solid {c['theme_btn_border']};
                border-radius: 14px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            #ThemeToolBtn:hover {{
                background-color: {c['theme_btn_hover_bg']};
            }}

            #AuthorBadge {{
                background-color: {c['author_bg']};
                color: {c['author_fg']};
                border: 1px solid {c['author_border']};
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}

            #ControlBtn {{
                background-color: {c['btn_ctrl_bg']};
                color: {c['btn_ctrl_fg']};
                border: 1px solid {c['btn_ctrl_border']};
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            #ControlBtn:hover {{
                background-color: {c['btn_ctrl_hover_bg']};
                color: {c['btn_ctrl_hover_fg']};
                border-color: {c['btn_ctrl_hover_bg']};
            }}

            #GhostBtn {{
                background-color: transparent;
                color: {c['btn_ghost_fg']};
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 3px 8px;
                font-size: 12px;
            }}
            #GhostBtn:hover {{
                background-color: {c['btn_ghost_hover_bg']};
                color: {c['btn_ghost_hover_fg']};
            }}

            /* Sidebar & Material Cards */
            #SidebarWidget {{
                background-color: {c['sidebar_bg']};
                border-right: 1px solid {c['sidebar_border']};
            }}

            #StatusBadgeNeutral {{
                background-color: {c['badge_neutral_bg']};
                border: 1px solid {c['badge_neutral_border']};
                border-radius: 14px;
            }}
            #StatusBadgeSuccess {{
                background-color: {c['badge_success_bg']};
                border: 1px solid {c['badge_success_border']};
                border-radius: 14px;
            }}
            #StatusBadgeWarning {{
                background-color: {c['badge_warning_bg']};
                border: 1px solid {c['badge_warning_border']};
                border-radius: 14px;
            }}
            
            #BadgeTitle {{
                color: {c['badge_neutral_title']};
                font-size: 13px;
                font-weight: 700;
            }}
            #StatusBadgeSuccess #BadgeTitle {{ color: {c['badge_success_title']}; }}
            #StatusBadgeWarning #BadgeTitle {{ color: {c['badge_warning_title']}; }}

            #BadgeSubtitle {{
                color: {c['badge_neutral_sub']};
                font-size: 11px;
            }}
            #StatusBadgeSuccess #BadgeSubtitle {{ color: {c['badge_success_sub']}; }}
            #StatusBadgeWarning #BadgeSubtitle {{ color: {c['badge_warning_sub']}; }}

            #InfoCard {{
                background-color: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 14px;
            }}
            #LegalDisclaimer {{
                background-color: {c['disclaimer_bg']};
                border: 1px solid {c['disclaimer_border']};
                border-radius: 12px;
            }}
            #DisclaimerText {{
                color: {c['disclaimer_fg']};
                font-size: 11px;
                line-height: 1.4;
            }}
            #SectionHeader {{
                color: {c['section_hdr']};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}
            #PreviewHeader {{
                color: {c['preview_hdr']};
                font-size: 13px;
                font-weight: 700;
            }}
            #FieldLabel {{
                color: {c['field_lbl']};
                font-size: 11px;
            }}
            #FieldValue {{
                color: {c['field_val']};
                font-size: 11px;
            }}
            #FieldValueBold {{
                color: {c['field_val_bold']};
                font-size: 12px;
                font-weight: 700;
            }}
            #FieldValueMono {{
                color: {c['field_val_mono']};
                font-family: Consolas, 'Fira Code', monospace;
                font-size: 11px;
                font-weight: 700;
            }}
            #FieldValueTag {{
                background-color: {c['field_val_tag_bg']};
                color: {c['field_val_tag_fg']};
                border-radius: 5px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 700;
            }}
            #HashText {{
                color: {c['hash_fg']};
                font-family: Consolas, monospace;
                font-size: 10px;
            }}

            /* Welcome Page & Dashboard */
            #WelcomeScrollArea {{
                background-color: {c['welcome_bg']};
                border: none;
            }}
            #WelcomeContainer {{
                background-color: {c['welcome_bg']};
            }}
            #HeroTitle {{
                color: {c['hero_title']};
                font-size: 24px;
                font-weight: 800;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            #HeroSubtitle {{
                color: {c['hero_sub']};
                font-size: 13px;
                line-height: 1.4;
            }}

            /* Drag & Drop Zone Material Card */
            #DropZoneCard {{
                background-color: {c['drop_bg']};
                border: 2px dashed {c['drop_border']};
                border-radius: 20px;
            }}
            #DropZoneCard:hover {{
                background-color: {c['drop_hover_bg']};
                border-color: {c['drop_hover_border']};
            }}
            #DropZoneTitle {{
                color: {c['drop_title']};
                font-size: 17px;
                font-weight: 700;
            }}
            #DropZoneSub {{
                color: {c['drop_sub']};
                font-size: 12px;
            }}

            /* Recent Files Cards */
            #RecentSectionHeader {{
                color: {c['recent_hdr']};
                font-size: 15px;
                font-weight: 700;
            }}
            #RecentFileCard {{
                background-color: {c['recent_card_bg']};
                border: 1px solid {c['recent_card_border']};
                border-radius: 12px;
            }}
            #RecentFileCard:hover {{
                background-color: {c['recent_card_hover_bg']};
                border-color: {c['recent_card_hover_border']};
            }}
            #RecentFileName {{
                color: {c['recent_name']};
                font-size: 13px;
                font-weight: 700;
            }}
            #RecentFilePath {{
                color: {c['recent_path']};
                font-size: 11px;
            }}
            #RecentCardBtn {{
                background-color: {c['recent_btn_bg']};
                color: {c['recent_btn_fg']};
                border: 1px solid {c['recent_btn_border']};
                border-radius: 10px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            #RecentCardBtn:hover {{
                background-color: {c['recent_btn_hover_bg']};
                color: {c['recent_btn_hover_fg']};
                border-color: {c['recent_btn_hover_bg']};
            }}

            #EmptyRecentCard {{
                background-color: {c['empty_card_bg']};
                border: 1px solid {c['empty_card_border']};
                border-radius: 12px;
            }}
            #EmptyRecentText {{
                color: {c['empty_text']};
                font-size: 12px;
            }}

            /* Viewers & Editors */
            #BinaryTitle {{
                color: {c['binary_title']};
                font-size: 15px;
                font-weight: 600;
            }}
            QTreeWidget, QTextEdit, QScrollArea {{
                background-color: {c['editor_bg']};
                color: {c['editor_fg']};
                border: 1px solid {c['editor_border']};
                border-radius: 10px;
            }}
            QTreeWidget::item {{
                padding: 4px;
            }}
            QTreeWidget::item:selected {{
                background-color: {c['tree_item_sel_bg']};
                color: {c['tree_item_sel_fg']};
                border-radius: 4px;
            }}
            QHeaderView::section {{
                background-color: {c['header_bg']};
                color: {c['header_fg']};
                font-weight: 700;
                border: none;
                border-bottom: 1px solid {c['header_border']};
                padding: 5px 8px;
            }}

            QTabWidget::pane {{
                border: 1px solid {c['tab_pane_border']};
                border-radius: 10px;
                background-color: {c['tab_pane_bg']};
            }}
            QTabBar::tab {{
                background-color: {c['tab_bg']};
                color: {c['tab_fg']};
                padding: 6px 14px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {c['tab_sel_bg']};
                color: {c['tab_sel_fg']};
            }}

            /* Minimal Single-Line Footer Bar */
            #FooterBar {{
                background-color: {c['footer_bg']};
                border-top: 1px solid {c['footer_border']};
                border-radius: 0px;
            }}
            #FooterStatus {{
                color: {c['footer_status']};
                font-size: 11px;
                font-weight: 600;
            }}
            #FooterCredits {{
                color: {c['footer_credits']};
                font-size: 10px;
            }}
        """
        self.setStyleSheet(qss)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("P7M Viewer PA")
    app.setOrganizationName("Antigravity PA")

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
