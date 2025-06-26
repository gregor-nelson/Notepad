import sys
import os
import platform
import time
import logging
import codecs
from datetime import datetime
from pathlib import Path
from functools import partial
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QFileDialog, QMessageBox, QStatusBar,
    QVBoxLayout, QWidget, QMenuBar, QMenu, QFontDialog, QLabel, QDialog,
    QPushButton, QLineEdit, QCheckBox, QGridLayout, QPlainTextEdit,
    QInputDialog, QDialogButtonBox, QSizePolicy, QSpacerItem, QColorDialog,
)
from PyQt6.QtGui import (
    QAction, QFont, QColor, QPalette, QFontMetrics, QKeySequence, QPainter,
    QTextFormat, QTextCursor, QTextDocument, QIcon, QDesktopServices, QActionGroup,
    QPageLayout, QPen, QPixmap, QBrush
)
from PyQt6.QtCore import (
    Qt, QSize, QSettings, QTimer, QThread, QObject, pyqtSignal, QRect, QPoint,
    QFileInfo, QDir, QUrl, QStandardPaths, QFile, QTextStream, QIODevice, QChar,
    QMarginsF
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtSvg import QSvgRenderer

import utils.syntax_highlighter as syntax_highlighter
import components.unified_preview as unified_preview
import components.modules.markdown_viewer as markdown_viewer
import components.modules.xml_viewer as xml_viewer



# --- Configuration ---
APP_NAME = "Notepad --"
ORG_NAME = "InterMoor"
BACKUP_INTERVAL_MS = 30_000
AUTOSAVE_INTERVAL_MS = 300_000
STATS_UPDATE_INTERVAL_MS = 400
MAX_RECENT_FILES = 10
DEFAULT_ENCODING = 'utf-8'
BACKUP_DIR_NAME = "backups"
CHUNK_SIZE = 1024 * 1024  # 1MB for file operations
MAX_TEXT_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Common text file extensions
TEXT_EXTENSIONS = {
    '.txt', '.py', '.pyw', '.md', '.json', '.xml', '.html', '.htm', '.css', '.js',
    '.jsx', '.mjs', '.cjs', '.csv', '.log', '.ini', '.yaml', '.yml', '.sh', '.bat',
    '.c', '.h', '.cpp', '.hpp', '.java', '.cs', '.go', '.php', '.rb', '.pl', '.ts',
    '.tsx', '.conf', '.cfg', '.rc', ''
}

# --- Icon System ---
class Icons:
    """Minimal icon system using inline SVG with caching."""
    
    def __init__(self):
        self._icon_cache = {}
    
    def get_icon(self, svg_str, color="#d4d7dd"):
        """Get cached icon or create new one."""
        cache_key = f"{svg_str}_{color}"
        
        if cache_key not in self._icon_cache:
            self._icon_cache[cache_key] = self._create_icon(svg_str, color)
        
        return self._icon_cache[cache_key]
    
    @staticmethod
    def _create_icon(svg_str, color="#d4d7dd"):
        """Create QIcon from SVG string."""
        svg_data = svg_str.replace("currentColor", color).encode('utf-8')
        
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        renderer = QSvgRenderer(svg_data)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        
        return QIcon(pixmap)
    
    # Icon definitions
    NEW_FILE = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M9 1H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V6L9 1zm0 1.5L12.5 6H9V2.5zM3 14V2h5v5h5v7H3z"/>
    </svg>'''
    
    OPEN_FILE = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M1.5 3.5A1.5 1.5 0 0 1 3 2h4l1.5 1.5H13a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 13 14H3a1.5 1.5 0 0 1-1.5-1.5v-9zm12 1.5H8L6.5 3.5H3v9h10v-7.5z"/>
    </svg>'''
    
    SAVE = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M11 1H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V4L11 1zM3 14V2h7v3h3v9H3zm3-7h4v4H6V7z"/>
    </svg>'''
    
    CUT = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M9.5 2l-1 1L11 5.5 8.5 8l1 1L12 6.5 14 8.5V2H9.5zM3 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm10 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM6 8l2 2-2 2 4 4h4v-6l-4-4L6 8z"/>
    </svg>'''
    
    COPY = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M4 2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1H4zm0 1h6v8H4V3zm2 10v1h6a1 1 0 0 0 1-1V5h-1v8H6z"/>
    </svg>'''
    
    PASTE = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M9 2H7a1 1 0 0 0-1 1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1h-2a1 1 0 0 0-1-1zM7 3h2v1H7V3zm-3 2h8v9H4V5z"/>
    </svg>'''
    
    FIND = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M10.5 7a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0zm-.8 3.7a5 5 0 1 1 1-1l3.3 3.3-1 1-3.3-3.3z"/>
    </svg>'''
    
    UNDO = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M3 7h6a3 3 0 0 1 3 3v1a3 3 0 0 1-3 3H7v-1.5h2a1.5 1.5 0 0 0 1.5-1.5v-1A1.5 1.5 0 0 0 9 8.5H3V11L0 7.5 3 4v3z"/>
    </svg>'''
    
    REDO = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M13 7H7a3 3 0 0 0-3 3v1a3 3 0 0 0 3 3h2v-1.5H7A1.5 1.5 0 0 1 5.5 11v-1A1.5 1.5 0 0 1 7 8.5h6V11l3-3.5L13 4v3z"/>
    </svg>'''
    
    PRINT = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M4 2h8v3H4V2zm-2 4h12a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-2v-3H4v3H2a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm10 2a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM5 10h6v4H5v-4z"/>
    </svg>'''
    
    FONT = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M6.5 2L2 14h2l1-3h4l1 3h2L7.5 2h-1zM5.5 9L7 4.5 8.5 9h-3zm8.5-4h-2l-2 9h2l2-9z"/>
    </svg>'''
    
    REPLACE = '''<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path fill="currentColor" d="M3 4h7v2l3-3-3-3v2H2v5h1V4zm10 5h-1v3H5v-2l-3 3 3 3v-2h8V9z"/>
    </svg>'''
    
    # Checkbox icons for menu items
    CHECK_CHECKED = '''<svg width="13" height="13" viewBox="0 0 13 13" xmlns="http://www.w3.org/2000/svg">
        <line x1="3" y1="6.5" x2="10" y2="6.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2,1"/>
    </svg>'''
    
    CHECK_UNCHECKED = '''<svg width="13" height="13" viewBox="0 0 13 13" xmlns="http://www.w3.org/2000/svg">
        <rect x="1" y="1" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3"/>
    </svg>'''
    
    @staticmethod
    def get_svg_data_url(svg_str, color="#d4d7dd"):
        """Create data URL for SVG to use in CSS background-image."""
        import base64
        svg_data = svg_str.replace("currentColor", color)
        # Encode SVG as data URL
        encoded = base64.b64encode(svg_data.encode('utf-8')).decode('utf-8')
        return f"data:image/svg+xml;base64,{encoded}"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def get_backup_dir():
    """Gets the application-specific backup directory."""
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    backup_path = os.path.join(path, BACKUP_DIR_NAME)
    os.makedirs(backup_path, exist_ok=True)
    return backup_path

def get_backup_filename(original_path=None):
    """Generates a unique backup filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = os.path.basename(original_path) if original_path else "untitled"
    return os.path.join(get_backup_dir(), f"{base_name}.{timestamp}.backup")

def detect_encoding_with_bom(filepath):
    """Detects encoding based on BOM (Byte Order Mark)."""
    try:
        with open(filepath, 'rb') as f:
            bom = f.read(4)
    except IOError:
        return None

    # Check BOMs in order of specificity
    bom_map = {
        codecs.BOM_UTF32_LE: 'utf-32-le',
        codecs.BOM_UTF32_BE: 'utf-32-be',
        codecs.BOM_UTF16_LE: 'utf-16-le',
        codecs.BOM_UTF16_BE: 'utf-16-be',
        codecs.BOM_UTF8: 'utf-8-sig',
    }
    
    for bom_marker, encoding in bom_map.items():
        if bom.startswith(bom_marker):
            return encoding
    return None

# --- File Worker for Background Operations ---
class FileWorker(QObject):
    finished = pyqtSignal(str, str)  # content, encoding
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, file_path, encoding=DEFAULT_ENCODING, content_to_save=None):
        super().__init__()
        self.file_path = file_path
        self.encoding = encoding
        self.content_to_save = content_to_save
        self._is_running = True

    def run(self):
        try:
            if self.content_to_save is not None:
                self._save_file()
            else:
                self._load_file()
        except Exception as e:
            logging.exception(f"File operation error: {e}")
            self.error.emit(str(e))

    def _save_file(self):
        """Saves content to file with progress reporting."""
        logging.info(f"Saving '{self.file_path}' with encoding '{self.encoding}'")
        
        # Pre-calculate total size for progress
        total_bytes = len(self.content_to_save.encode(self.encoding, errors='replace'))
        bytes_written = 0
        
        with open(self.file_path, 'w', encoding=self.encoding, errors='replace') as f:
            for i in range(0, len(self.content_to_save), CHUNK_SIZE):
                if not self._is_running:
                    raise InterruptedError("Save cancelled")
                    
                chunk = self.content_to_save[i:i + CHUNK_SIZE]
                f.write(chunk)
                bytes_written += len(chunk.encode(self.encoding, errors='replace'))
                
                progress = int((bytes_written / total_bytes) * 100) if total_bytes > 0 else 100
                self.progress.emit(progress)
        
        self.finished.emit("", self.encoding)

    def _load_file(self):
        """Loads content from file with progress reporting."""
        logging.info(f"Loading '{self.file_path}' with encoding '{self.encoding}'")
        
        file_size = os.path.getsize(self.file_path)
        content = []
        bytes_read = 0
        
        with open(self.file_path, 'r', encoding=self.encoding, errors='replace') as f:
            while True:
                if not self._is_running:
                    raise InterruptedError("Load cancelled")
                    
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                    
                content.append(chunk)
                bytes_read += len(chunk.encode(self.encoding, errors='replace'))
                
                progress = int((bytes_read / file_size) * 100) if file_size > 0 else 100
                self.progress.emit(progress)
        
        self.finished.emit(''.join(content), self.encoding)

    def stop(self):
        self._is_running = False

# --- Line Number Area Widget ---
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.calculate_width(), 0)

    def calculate_width(self):
        digits = len(str(max(1, self.editor.blockCount())))
        # Extra space for modified indicator
        return self.fontMetrics().horizontalAdvance('9' * digits) + 30

    def paintEvent(self, event):
        painter = QPainter(self)
        # VS Code style line number background
        painter.fillRect(event.rect(), QColor("#1e1e1e"))
        
        # Draw modified indicator
        if self.editor.document().isModified():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f48771"))  # VS Code orange-red
            painter.drawEllipse(6, 6, 4, 4)  # Smaller, more subtle
        
        block = self.editor.firstVisibleBlock()
        top = int(self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        # Current line highlighting
        current_line = self.editor.textCursor().blockNumber()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block.blockNumber() + 1)
                
                # VS Code style current line highlighting
                if block.blockNumber() == current_line:
                    painter.setPen(QColor("#c6c6c6"))  # Bright gray for current line
                    painter.setFont(self.font())  # No bold font
                else:
                    painter.setPen(QColor("#858585"))  # Muted gray for other lines
                    painter.setFont(self.font())
                
                painter.drawText(0, top, self.width() - 8, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())

class TextEditWithLineNumbers(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.lineNumberArea = LineNumberArea(self)
        self.line_number_color = QColor(Qt.GlobalColor.gray)
        
        # Enable smooth scrolling by adjusting scroll bar
        self.verticalScrollBar().setSingleStep(20)
        
        self.blockCountChanged.connect(self.update_line_numbers)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        
        self.update_line_numbers()
        self.highlight_current_line()

    def update_line_numbers(self):
        self.setViewportMargins(self.lineNumberArea.calculate_width(), 0, 0, 0)
        self.lineNumberArea.setFixedWidth(self.lineNumberArea.calculate_width())

    def update_line_number_area(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), 
                                             self.lineNumberArea.width(), cr.height()))

    def highlight_current_line(self):
        selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            # One Dark style current line highlight - very subtle
            lineColor = QColor("#2c313c")  # Slightly lighter than background
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)
        self.setExtraSelections(selections)


    def showLineNumbers(self, show):
        self.lineNumberArea.setVisible(show)
        self.update_line_numbers() if show else self.setViewportMargins(0, 0, 0, 0)

# --- Main Application ---
class Notepad(QMainWindow):
    # Add signals for file operations
    fileOpened = pyqtSignal(str, str)  # filepath, encoding
    fileSaved = pyqtSignal(str, str)   # filepath, encoding  
    fileNew = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.current_file = None
        self.current_encoding = DEFAULT_ENCODING
        self.backup_file_path = None
        self.last_save_content = ""
        self.file_thread = None
        self.file_worker = None
        self._is_busy = False
        self.current_highlighter = None
        self._last_find_params = {}
        
        # Cache for file info to avoid repeated I/O
        self._cached_file_size = None
        self._cached_file_path = None
        
        # Atom One Dark theme color scheme
        self.colors = {
            "black": "#282c34",      # One Dark background
            "black2": "#21252b",     # Darker background variant
            "white": "#abb2bf",      # One Dark main text color
            "gray1": "#1e2125",      # Darker than background
            "gray2": "#2c313c",      # One Dark sidebar/UI color
            "gray3": "#3e4451",      # One Dark border/inactive color
            "gray4": "#5c6370",      # One Dark comment/muted text
            "blue": "#61afef",       # One Dark blue
            "blue2": "#528bff",      # One Dark bright blue accent
            "green": "#98c379",      # One Dark green
            "red": "#e06c75",        # One Dark red
            "orange": "#d19a66",     # One Dark orange/numbers
            "yellow": "#e5c07b",     # One Dark yellow
            "purple": "#c678dd",     # One Dark purple/keywords
            "cyan": "#56b6c2",       # One Dark cyan/built-ins
            "selection": "#3e4451",  # One Dark selection color
            "hover": "#353b45",      # One Dark hover background
            "border": "#3e4451",     # One Dark border color
            "icon": "#abb2bf",       # One Dark icon color
        }
        
        # Initialize icons with caching
        self.icons = Icons()
        
        self.initUI()

        unified_preview.integrate_unified_preview(self)
        unified_preview.add_xml_validation_menu(self)
      

        self.setupTimers()
        self.loadSettings()
        
        self.checkForRecovery()
        self.setAcceptDrops(True)
    def initUI(self):
        self.setWindowTitle(f"Untitled - {APP_NAME}")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Text editor
        self.text_edit = TextEditWithLineNumbers()
        self.text_edit.setFrameStyle(0)
        layout.addWidget(self.text_edit)
        
        # Status bar with clean styling
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Create labels
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.encoding_label = QLabel("UTF-8")
        self.file_type_label = QLabel("Plain Text")
        self.stats_label = QLabel("0 words")
        
        # Add labels with spacing (no borders)
        self.status_bar.addWidget(self.stats_label)
        self.status_bar.addWidget(self.file_type_label)
        
        # Add stretch to push items to the right
        self.status_bar.addWidget(QLabel(), 1)  # Spacer with stretch
        
        self.status_bar.addWidget(self.encoding_label)
        self.status_bar.addWidget(self.cursor_label)
        
        # Connections
        self.text_edit.cursorPositionChanged.connect(self.update_cursor_position)
        self.text_edit.textChanged.connect(self.on_text_changed)
        self.text_edit.document().modificationChanged.connect(self.update_title)
        
        self.createMenus()
        self.setupTheme()
        
        # Default font
        default_font = QFont('Consolas' if platform.system() == 'Windows' else 'Menlo', 10)
        self.text_edit.setFont(default_font)


    def createMenus(self):
        menu_bar = self.menuBar()
        
        # File menu with cached icons
        file_menu = menu_bar.addMenu('&File')
        
        new_action = self.add_menu_action(file_menu, '&New', self.new_file, 
                                         QKeySequence.StandardKey.New)
        new_action.setIcon(self.icons.get_icon(Icons.NEW_FILE, self.colors["icon"]))
        
        open_action = self.add_menu_action(file_menu, '&Open...', self.open_file, 
                                          QKeySequence.StandardKey.Open)
        open_action.setIcon(self.icons.get_icon(Icons.OPEN_FILE, self.colors["icon"]))
        
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self.populate_recent_files)
        
        file_menu.addSeparator()
        
        self.save_action = self.add_menu_action(file_menu, '&Save', self.save_file, 
                                               QKeySequence.StandardKey.Save)
        self.save_action.setIcon(self.icons.get_icon(Icons.SAVE, self.colors["icon"]))
        
        save_as_action = self.add_menu_action(file_menu, 'Save &As...', self.save_file_as, 
                                             QKeySequence.StandardKey.SaveAs)
        save_as_action.setIcon(self.icons.get_icon(Icons.SAVE, self.colors["icon"]))
        
        file_menu.addSeparator()
        
        self.autosave_action = QAction('&Auto Save', self, checkable=True)
        self.autosave_action.triggered.connect(self.toggle_autosave)
        file_menu.addAction(self.autosave_action)
        
        file_menu.addSeparator()
        
        print_action = self.add_menu_action(file_menu, '&Print...', self.print_document, 
                                           QKeySequence.StandardKey.Print)
        print_action.setIcon(self.icons.get_icon(Icons.PRINT, self.colors["icon"]))
        
        file_menu.addSeparator()
        self.add_menu_action(file_menu, 'E&xit', self.close, QKeySequence.StandardKey.Quit)
        
        # Edit menu with cached icons
        edit_menu = menu_bar.addMenu('&Edit')
        
        undo_action = self.add_menu_action(edit_menu, '&Undo', self.text_edit.undo, 
                                          QKeySequence.StandardKey.Undo)
        undo_action.setIcon(self.icons.get_icon(Icons.UNDO, self.colors["icon"]))
        
        redo_action = self.add_menu_action(edit_menu, '&Redo', self.text_edit.redo, 
                                          QKeySequence.StandardKey.Redo)
        redo_action.setIcon(self.icons.get_icon(Icons.REDO, self.colors["icon"]))
        
        edit_menu.addSeparator()
        
        cut_action = self.add_menu_action(edit_menu, 'Cu&t', self.text_edit.cut, 
                                         QKeySequence.StandardKey.Cut)
        cut_action.setIcon(self.icons.get_icon(Icons.CUT, self.colors["icon"]))
        
        copy_action = self.add_menu_action(edit_menu, '&Copy', self.text_edit.copy, 
                                          QKeySequence.StandardKey.Copy)
        copy_action.setIcon(self.icons.get_icon(Icons.COPY, self.colors["icon"]))
        
        paste_action = self.add_menu_action(edit_menu, '&Paste', self.text_edit.paste, 
                                           QKeySequence.StandardKey.Paste)
        paste_action.setIcon(self.icons.get_icon(Icons.PASTE, self.colors["icon"]))
        
        edit_menu.addSeparator()
        
        find_action = self.add_menu_action(edit_menu, '&Find...', self.show_find_dialog, 
                                          QKeySequence.StandardKey.Find)
        find_action.setIcon(self.icons.get_icon(Icons.FIND, self.colors["icon"]))
        
        replace_action = self.add_menu_action(edit_menu, '&Replace...', self.show_replace_dialog, 
                                             QKeySequence.StandardKey.Replace)
        replace_action.setIcon(self.icons.get_icon(Icons.REPLACE, self.colors["icon"]))
        
        edit_menu.addSeparator()
        self.add_menu_action(edit_menu, 'Select &All', self.text_edit.selectAll, 
                            QKeySequence.StandardKey.SelectAll)
        
        # Format menu
        format_menu = menu_bar.addMenu('F&ormat')
        self.wrap_action = self.add_menu_action(format_menu, '&Word Wrap', 
                                               self.toggle_word_wrap, checkable=True)
        
        font_action = self.add_menu_action(format_menu, '&Font...', self.choose_font)
        font_action.setIcon(self.icons.get_icon(Icons.FONT, self.colors["icon"]))
        
        format_menu.addSeparator()
        self.syntax_action = self.add_menu_action(format_menu, 'S&yntax Highlighting', 
                                                 self.toggle_syntax, checkable=True, 
                                                 checked=True)
        
        # View menu
        view_menu = menu_bar.addMenu('&View')
        self.lines_action = self.add_menu_action(view_menu, 'Show &Line Numbers', 
                                                self.toggle_line_numbers, 
                                                checkable=True, checked=True)
        view_menu.addSeparator()
        self.add_menu_action(view_menu, 'Zoom &In', self.zoom_in, 
                            QKeySequence.StandardKey.ZoomIn)
        self.add_menu_action(view_menu, 'Zoom &Out', self.zoom_out, 
                            QKeySequence.StandardKey.ZoomOut)
        self.add_menu_action(view_menu, '&Reset Zoom', self.reset_zoom, 
                            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_0))
        view_menu.addSeparator()
        self.status_action = self.add_menu_action(view_menu, 'Show &Status Bar', 
                                                 self.toggle_status_bar, 
                                                 checkable=True, checked=True)
        
        # Encoding menu
        encoding_menu = menu_bar.addMenu('&Encoding')
        self.encoding_group = QActionGroup(self)
        
        encodings = [('UTF-8', 'utf-8'), ('UTF-8 with BOM', 'utf-8-sig'), 
                    ('UTF-16', 'utf-16'), ('Latin-1', 'latin-1')]
        
        for display, codec in encodings:
            action = QAction(display, self, checkable=True)
            action.setData(codec)
            action.triggered.connect(lambda checked, c=codec: self.change_encoding(c) if checked else None)
            encoding_menu.addAction(action)
            self.encoding_group.addAction(action)
            if codec == self.current_encoding:
                action.setChecked(True)
        
        encoding_menu.addSeparator()
        self.add_menu_action(encoding_menu, 'Reopen with Encoding...', self.reopen_with_encoding)
        
        # Help menu
        help_menu = menu_bar.addMenu('&Help')
        self.add_menu_action(help_menu, '&About', self.show_about)

    def add_menu_action(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def setupTheme(self):
        """Apply VS Code-inspired dark theme."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.colors["black"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self.colors["white"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(self.colors["black"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(self.colors["white"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(self.colors["gray2"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(self.colors["white"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(self.colors["selection"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(self.colors["white"]))
        
        QApplication.instance().setPalette(palette)
        
        # VS Code-inspired stylesheet
        style = f"""
            QMainWindow {{
                background-color: {self.colors["black"]};
            }}
            
            /* Text Editor */
            QPlainTextEdit {{
                background-color: {self.colors["black2"]};
                color: {self.colors["white"]};
                border: none;
                padding: 4px;
                selection-background-color: {self.colors["selection"]};
                selection-color: {self.colors["white"]};
                font-family: 'Consolas', 'Courier New', monospace;
            }}
            
            /* Menu Bar */
            QMenuBar {{
                background-color: {self.colors["gray2"]};
                border-bottom: 1px solid {self.colors["border"]};
                padding: 2px;
                spacing: 0px;
            }}
            QMenuBar::item {{
                padding: 4px 12px;
                background-color: transparent;
                color: {self.colors["white"]};
            }}
            QMenuBar::item:selected {{
                background-color: {self.colors["hover"]};
            }}
            QMenuBar::item:pressed {{
                background-color: {self.colors["gray3"]};
            }}
            
            /* Menus */
            QMenu {{
                background-color: {self.colors["gray2"]};
                border: 1px solid {self.colors["border"]};
                padding: 4px 0px;
            }}
            QMenu::item {{
                padding: 4px 30px 4px 20px;
                background-color: transparent;
                color: {self.colors["white"]};
            }}
            QMenu::item:selected {{
                background-color: {self.colors["hover"]};
            }}
            QMenu::separator {{
                height: 1px;
                background: {self.colors["border"]};
                margin: 4px 10px;
            }}
            QMenu::icon {{
                margin-left: 4px;
            }}
            QMenu::indicator {{
                width: 13px;
                height: 13px;
                margin-left: 4px;
                background-image: url({Icons.get_svg_data_url(Icons.CHECK_UNCHECKED, self.colors["icon"])});
                background-repeat: no-repeat;
                background-position: center;
            }}
            QMenu::indicator:checked {{
                background-image: url({Icons.get_svg_data_url(Icons.CHECK_CHECKED, self.colors["icon"])});
                background-repeat: no-repeat;
                background-position: center;
            }}
            
            /* Status Bar - Clean modern style */
            QStatusBar {{
                background-color: {self.colors["gray2"]};
                border: none;
                border-top: 1px solid {self.colors["gray3"]};
                padding: 0px;
                min-height: 22px;
                max-height: 22px;
            }}
            QStatusBar::item {{
                border: none;
            }}
            QStatusBar QLabel {{
                color: {self.colors["gray4"]};
                padding: 3px 16px;
                border: none;
                background-color: transparent;
                font-size: 12px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            QStatusBar QLabel:hover {{
                color: {self.colors["white"]};
            }}
            
            /* Dialogs */
            QDialog {{
                background-color: {self.colors["gray2"]};
                color: {self.colors["white"]};
            }}
            QPushButton {{
                background-color: {self.colors["blue"]};
                border: none;
                color: white;
                padding: 6px 14px;
                font-weight: normal;
                min-width: 60px;
            }}
            QPushButton:hover {{
                background-color: {self.colors["blue2"]};
            }}
            QPushButton:pressed {{
                background-color: {self.colors["gray3"]};
            }}
            QPushButton:default {{
                background-color: {self.colors["blue"]};
            }}
            
            /* Input fields */
            QLineEdit {{
                background-color: {self.colors["gray3"]};
                border: 1px solid {self.colors["border"]};
                color: {self.colors["white"]};
                padding: 4px 8px;
                selection-background-color: {self.colors["selection"]};
                selection-color: {self.colors["white"]};
            }}
            QLineEdit:focus {{
                border-color: {self.colors["blue"]};
                outline: none;
            }}
            
            /* Check boxes */
            QCheckBox {{
                color: {self.colors["white"]};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
                background-color: {self.colors["gray3"]};
                border: 1px solid {self.colors["border"]};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.colors["blue"]};
                border-color: {self.colors["blue"]};
            }}
            
            /* Scrollbars */
            QScrollBar:vertical {{
                background: {self.colors["black"]};
                width: 14px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {self.colors["gray3"]};
                min-height: 30px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {self.colors["gray4"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
                border: none;
            }}
            
            QScrollBar:horizontal {{
                background: {self.colors["black"]};
                height: 14px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {self.colors["gray3"]};
                min-width: 30px;
                border: none;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {self.colors["gray4"]};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
                border: none;
            }}
            
            /* Message boxes */
            QMessageBox {{
                background-color: {self.colors["gray2"]};
                color: {self.colors["white"]};
            }}
            QMessageBox QPushButton {{
                min-width: 70px;
                padding: 5px 15px;
            }}
        """
        QApplication.instance().setStyleSheet(style)
        
    def setupTimers(self):
        # Backup timer
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self.backup_if_needed)
        self.backup_timer.start(BACKUP_INTERVAL_MS)
        
        # Autosave timer
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        
        # Stats update timer - Fixed to prevent multiple timers
        self.stats_timer = QTimer(self)
        self.stats_timer.setSingleShot(True)
        self.stats_timer.timeout.connect(self.update_stats)

    # --- File Operations ---
    def new_file(self):
        if self.maybe_save():
            self.text_edit.clear()
            self.current_file = None
            self.current_encoding = DEFAULT_ENCODING
            self._cached_file_size = None
            self._cached_file_path = None
            self.text_edit.document().setModified(False)
            self.update_title()
            self.file_type_label.setText("Plain Text")
            self.update_menu_visibility()  # Update menu visibility for new file
            self.fileNew.emit()

    def open_file(self):
        if self.maybe_save():
            file_path, _ = QFileDialog.getOpenFileName(self, "Open File", 
                                                      self.get_last_dir("open"), 
                                                      "All Files (*)")
            if file_path:
                self.save_last_dir("open", file_path)
                encoding = detect_encoding_with_bom(file_path) or DEFAULT_ENCODING
                self.load_file(file_path, encoding)

    def save_file(self):
        if self.current_file:
            return self.save_to_file(self.current_file, self.current_encoding)
        else:
            return self.save_file_as()

    def save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save As", 
                                                  self.get_last_dir("save"), 
                                                  "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.save_last_dir("save", file_path)
            return self.save_to_file(file_path, self.current_encoding)
        return False

    def load_file(self, file_path, encoding):
        if self._is_busy:
            return
        
        self._is_busy = True
        self.text_edit.setReadOnly(True)
        self.status_bar.showMessage(f"Loading {os.path.basename(file_path)}...")
        
        # Subtle loading state
        self.text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {self.colors["black"]};
                color: {self.colors["gray4"]};
            }}
        """)

        self.text_edit.setPlainText("Loading...")
        
        self.file_thread = QThread()
        self.file_worker = FileWorker(file_path, encoding)
        self.file_worker.moveToThread(self.file_thread)
        
        # Connect signals
        self.file_worker.finished.connect(self.on_file_loaded)
        self.file_worker.error.connect(self.on_file_error)
        self.file_worker.progress.connect(lambda p: self.status_bar.showMessage(f"Loading... {p}%"))
        
        # Cleanup connections
        self.file_worker.finished.connect(self.cleanup_file_operation)
        self.file_worker.error.connect(self.cleanup_file_operation)
        
        self.file_thread.started.connect(self.file_worker.run)
        self.file_thread.start()

    def save_to_file(self, file_path, encoding):
        if self._is_busy:
            return False
        
        self._is_busy = True
        self.status_bar.showMessage(f"Saving {os.path.basename(file_path)}...")
        
        content = self.text_edit.toPlainText()
        
        self.file_thread = QThread()
        self.file_worker = FileWorker(file_path, encoding, content)
        self.file_worker.moveToThread(self.file_thread)
        
        # Connect signals
        self.file_worker.finished.connect(lambda: self.on_file_saved(file_path, encoding))
        self.file_worker.error.connect(self.on_file_error)
        self.file_worker.progress.connect(lambda p: self.status_bar.showMessage(f"Saving... {p}%"))
        
        # Cleanup connections
        self.file_worker.finished.connect(self.cleanup_file_operation)
        self.file_worker.error.connect(self.cleanup_file_operation)
        
        self.file_thread.started.connect(self.file_worker.run)
        self.file_thread.start()
        
        return True

    def on_file_loaded(self, content, encoding):
        # Reset stylesheet
        self.text_edit.setStyleSheet("")
        
        self.text_edit.setPlainText(content)
        self.current_file = self.file_worker.file_path
        self.current_encoding = encoding
        self._cached_file_path = self.current_file
        self._cached_file_size = os.path.getsize(self.current_file)
        self.text_edit.document().setModified(False)
        self.update_title()
        self.update_recent_files(self.current_file)
        self.apply_syntax_highlighting()
        self.update_file_type()
        self.status_bar.showMessage(f"Loaded {os.path.basename(self.current_file)}", 3000)
        self.fileOpened.emit(self.current_file, encoding)

    def on_file_saved(self, file_path, encoding):
        self.current_file = file_path
        self.current_encoding = encoding
        self._cached_file_path = file_path
        self._cached_file_size = os.path.getsize(file_path)
        self.text_edit.document().setModified(False)
        self.last_save_content = self.text_edit.toPlainText()
        self.clear_backup()
        self.update_title()
        self.update_recent_files(file_path)
        self.update_file_type()
        self.status_bar.showMessage(f"Saved {os.path.basename(file_path)}", 3000)
        self.fileSaved.emit(file_path, encoding)

    def on_file_error(self, error_msg):
        # Reset stylesheet
        self.text_edit.setStyleSheet("")
        QMessageBox.critical(self, "Error", error_msg)
        self.status_bar.showMessage("Operation failed", 3000)

    def cleanup_file_operation(self):
        """Improved cleanup with proper signal disconnection"""
        self._is_busy = False
        self.text_edit.setReadOnly(False)
        
        # Disconnect all signals before cleanup
        if self.file_worker:
            try:
                self.file_worker.finished.disconnect()
                self.file_worker.error.disconnect()
                self.file_worker.progress.disconnect()
            except TypeError:
                pass  # Already disconnected
            
            self.file_worker.stop()
        
        if self.file_thread and self.file_thread.isRunning():
            self.file_thread.quit()
            if not self.file_thread.wait(5000):  # 5 second timeout
                self.file_thread.terminate()
                self.file_thread.wait()
        
        self.file_thread = None
        self.file_worker = None

    def maybe_save(self):
        if not self.text_edit.document().isModified():
            return True
        
        reply = QMessageBox.question(self, APP_NAME, 
                                   "The document has been modified.\nDo you want to save your changes?",
                                   QMessageBox.StandardButton.Save | 
                                   QMessageBox.StandardButton.Discard | 
                                   QMessageBox.StandardButton.Cancel)
        
        if reply == QMessageBox.StandardButton.Save:
            return self.save_file()
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    # --- Backup and Recovery ---
    def backup_if_needed(self):
        if self.text_edit.document().isModified() and not self._is_busy:
            current_content = self.text_edit.toPlainText()
            if current_content != self.last_save_content:
                if not self.backup_file_path:
                    self.backup_file_path = get_backup_filename(self.current_file)
                
                try:
                    with open(self.backup_file_path, 'w', encoding=DEFAULT_ENCODING) as f:
                        f.write(current_content)
                except Exception as e:
                    logging.error(f"Backup failed: {e}")

    def clear_backup(self):
        if self.backup_file_path and os.path.exists(self.backup_file_path):
            try:
                os.remove(self.backup_file_path)
            except OSError:
                pass
        self.backup_file_path = None

    def checkForRecovery(self):
        backup_dir = get_backup_dir()
        try:
            backup_files = [f for f in os.listdir(backup_dir) if f.endswith('.backup')]
            if backup_files:
                backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)), 
                                 reverse=True)
                latest = os.path.join(backup_dir, backup_files[0])
                
                reply = QMessageBox.question(self, "Recover File?", 
                                           "An unsaved file was found.\nDo you want to recover it?",
                                           QMessageBox.StandardButton.Yes | 
                                           QMessageBox.StandardButton.No)
                
                if reply == QMessageBox.StandardButton.Yes:
                    with open(latest, 'r', encoding=DEFAULT_ENCODING) as f:
                        self.text_edit.setPlainText(f.read())
                    self.text_edit.document().setModified(True)
                    self.backup_file_path = latest
                    self.update_title()
                else:
                    os.remove(latest)
        except Exception as e:
            logging.error(f"Recovery check failed: {e}")

    # --- Settings ---
    def loadSettings(self):
        # Window geometry
        if geom := self.settings.value("geometry"):
            self.restoreGeometry(geom)
        
        # Window state
        if state := self.settings.value("windowState"):
            self.setWindowState(Qt.WindowState(int(state)))
        
        # Font
        font_family = self.settings.value("font/family", "Consolas")
        font_size = self.settings.value("font/size", 10, type=int)
        self.text_edit.setFont(QFont(font_family, font_size))
        
        # Options
        self.wrap_action.setChecked(self.settings.value("wordWrap", False, type=bool))
        self.toggle_word_wrap()
        
        self.lines_action.setChecked(self.settings.value("showLineNumbers", True, type=bool))
        self.toggle_line_numbers()
        
        self.status_action.setChecked(self.settings.value("showStatusBar", True, type=bool))
        self.toggle_status_bar()
        
        self.autosave_action.setChecked(self.settings.value("autoSave", False, type=bool))
        self.toggle_autosave()

    def saveSettings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", int(self.windowState()))
        
        font = self.text_edit.font()
        self.settings.setValue("font/family", font.family())
        self.settings.setValue("font/size", font.pointSize())
        
        self.settings.setValue("wordWrap", self.wrap_action.isChecked())
        self.settings.setValue("showLineNumbers", self.lines_action.isChecked())
        self.settings.setValue("showStatusBar", self.status_action.isChecked())
        self.settings.setValue("autoSave", self.autosave_action.isChecked())

    # --- UI Updates ---
    def update_title(self):
        """Optimized to avoid repeated file I/O"""
        modified = "● " if self.text_edit.document().isModified() else ""  # Dot indicator
        name = os.path.basename(self.current_file) if self.current_file else "Untitled"
        
        # Only get file size if file changed or not cached
        size_info = ""
        if self.current_file and self.current_file == self._cached_file_path:
            # Use cached size
            if self._cached_file_size is not None:
                if self._cached_file_size < 1024:
                    size_info = f" ({self._cached_file_size} B)"
                elif self._cached_file_size < 1024 * 1024:
                    size_info = f" ({self._cached_file_size / 1024:.1f} KB)"
                else:
                    size_info = f" ({self._cached_file_size / 1024 / 1024:.1f} MB)"
        elif self.current_file and os.path.exists(self.current_file):
            # Update cache
            self._cached_file_size = os.path.getsize(self.current_file)
            self._cached_file_path = self.current_file
            
            if self._cached_file_size < 1024:
                size_info = f" ({self._cached_file_size} B)"
            elif self._cached_file_size < 1024 * 1024:
                size_info = f" ({self._cached_file_size / 1024:.1f} KB)"
            else:
                size_info = f" ({self._cached_file_size / 1024 / 1024:.1f} MB)"
        
        self.setWindowTitle(f"{modified}{name}{size_info} - {APP_NAME}")
        self.save_action.setEnabled(self.text_edit.document().isModified())

    def update_cursor_position(self):
        cursor = self.text_edit.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self.cursor_label.setText(f"Ln {line}, Col {col}")

    def update_stats(self):
        text = self.text_edit.toPlainText()
        words = len(text.split()) if text else 0
        chars = len(text)
        self.stats_label.setText(f"{words:,} words")

    def update_file_type(self):
        if self.current_file:
            ext = os.path.splitext(self.current_file)[1].lower()
            file_types = {
                '.py': 'Python', '.js': 'JavaScript', '.html': 'HTML', '.css': 'CSS',
                '.cpp': 'C++', '.c': 'C', '.java': 'Java', '.cs': 'C#', '.go': 'Go',
                '.rs': 'Rust', '.php': 'PHP', '.rb': 'Ruby', '.md': 'Markdown',
                '.json': 'JSON', '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
                '.sh': 'Shell', '.bat': 'Batch', '.ini': 'INI', '.toml': 'TOML'
            }
            self.file_type_label.setText(file_types.get(ext, 'Plain Text'))
        else:
            self.file_type_label.setText('Plain Text')
        
        # Update menu visibility based on file type
        self.update_menu_visibility()

    def get_current_file_extension(self):
        """Get the current file extension"""
        if self.current_file:
            return os.path.splitext(self.current_file)[1].lower()
        return None

    def is_xml_file(self):
        """Check if current file is XML"""
        ext = self.get_current_file_extension()
        return ext == '.xml'

    def supports_preview(self):
        """Check if current file supports preview"""
        ext = self.get_current_file_extension()
        if not ext:
            return False
        
        # Import preview types from unified_preview
        from components.unified_preview import PREVIEW_TYPES
        return ext in PREVIEW_TYPES

    def update_menu_visibility(self):
        """Update menu item visibility based on current file type"""
        # Update XML validation menu visibility
        if hasattr(self, 'validate_xml_action'):
            self.validate_xml_action.setVisible(self.is_xml_file())
        
        # Update preview menu visibility
        supports_preview = self.supports_preview()
        if hasattr(self, 'preview_action'):
            self.preview_action.setVisible(supports_preview)
        
        if hasattr(self, 'live_preview_action'):
            self.live_preview_action.setVisible(supports_preview)
            
        if hasattr(self, 'refresh_preview_action'):
            self.refresh_preview_action.setVisible(supports_preview)

    def change_encoding(self, encoding):
        """Fixed to avoid duplicate updates"""
        self.current_encoding = encoding
        # Clean display - only update label once
        display_name = encoding.upper().replace('-SIG', ' BOM')
        self.encoding_label.setText(display_name)
        self.text_edit.document().setModified(True)
        
        # Update encoding menu check state
        for action in self.encoding_group.actions():
            if action.data() == encoding:
                action.setChecked(True)
                break

    def on_text_changed(self):
        """Fixed to cancel previous timer before starting new one"""
        self.stats_timer.stop()  # Cancel any pending update
        self.stats_timer.start(STATS_UPDATE_INTERVAL_MS)

    # --- Features ---
    def toggle_word_wrap(self):
        wrap = self.wrap_action.isChecked()
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap 
                                      else QPlainTextEdit.LineWrapMode.NoWrap)

    def toggle_line_numbers(self):
        self.text_edit.showLineNumbers(self.lines_action.isChecked())

    def toggle_status_bar(self):
        self.status_bar.setVisible(self.status_action.isChecked())

    def toggle_autosave(self):
        if self.autosave_action.isChecked():
            self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)
        else:
            self.autosave_timer.stop()

    def autosave(self):
        if self.current_file and self.text_edit.document().isModified():
            self.save_file()

    def toggle_syntax(self):
        if self.syntax_action.isChecked():
            self.apply_syntax_highlighting()
        else:
            if self.current_highlighter:
                self.current_highlighter.setDocument(None)
                self.current_highlighter = None

    def apply_syntax_highlighting(self):
        if self.current_highlighter:
            self.current_highlighter.setDocument(None)
            self.current_highlighter = None
        
        if self.syntax_action.isChecked() and self.current_file:
            highlighter = syntax_highlighter.get_highlighter_for_file(
                self.current_file, self.text_edit.document(), self.colors)
            if highlighter:
                self.current_highlighter = highlighter

    def choose_font(self):
        font, ok = QFontDialog.getFont(self.text_edit.font(), self)
        if ok:
            self.text_edit.setFont(font)

    def zoom_in(self):
        font = self.text_edit.font()
        font.setPointSize(min(font.pointSize() + 1, 48))
        self.text_edit.setFont(font)

    def zoom_out(self):
        font = self.text_edit.font()
        font.setPointSize(max(font.pointSize() - 1, 6))
        self.text_edit.setFont(font)

    def reset_zoom(self):
        font_family = self.settings.value("font/family", "Consolas")
        font_size = self.settings.value("font/size", 10, type=int)
        self.text_edit.setFont(QFont(font_family, font_size))

    def reopen_with_encoding(self):
        if self.current_file and self.maybe_save():
            encodings = ['utf-8', 'utf-8-sig', 'utf-16', 'latin-1', 'windows-1252']
            encoding, ok = QInputDialog.getItem(self, "Reopen with Encoding", 
                                              "Choose encoding:", encodings, 0, False)
            if ok:
                self.load_file(self.current_file, encoding)

    def print_document(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.text_edit.print_(printer)

    def show_find_dialog(self):
        text, ok = QInputDialog.getText(self, "Find", "Find text:")
        if ok and text:
            self._last_find_params = {'text': text}
            self.find_text(text)

    def show_replace_dialog(self):
        # Simplified replace - just find and replace all
        find_text, ok = QInputDialog.getText(self, "Replace", "Find text:")
        if ok and find_text:
            replace_text, ok = QInputDialog.getText(self, "Replace", "Replace with:")
            if ok:
                content = self.text_edit.toPlainText()
                new_content = content.replace(find_text, replace_text)
                if new_content != content:
                    self.text_edit.setPlainText(new_content)
                    self.text_edit.document().setModified(True)

    def find_text(self, text):
        cursor = self.text_edit.textCursor()
        found = self.text_edit.find(text)
        if not found:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.find(text)

    def show_about(self):
        about_text = f"""
        <div style="font-family: Segoe UI, Arial, sans-serif; line-height: 1.4;">
        <h2 style="color: #61afef; margin: 0 0 15px 0;">{APP_NAME}</h2>
    
    
        <h3 style="color: #98c379; margin: 20px 0 10px 0;">Shortcuts</h3>
        <table style="border-collapse: collapse; width: 100%;">
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+N</b></td><td>New file</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+O</b></td><td>Open file</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+S</b></td><td>Save file</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+F</b></td><td>Find text</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+H</b></td><td>Find & Replace</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+ +/-</b></td><td>Zoom in/out</td></tr>
            <tr><td style="padding: 2px 10px 2px 0;"><b>Ctrl+0</b></td><td>Reset zoom</td></tr>
        </table>
        
        <h3 style="color: #98c379; margin: 20px 0 10px 0;">Getting Started</h3>
        <ol style="margin: 0 0 15px 20px; padding: 0;">
            <li><b>Create:</b> Use File → New or Ctrl+N for a new document</li>
            <li><b>Open:</b> Drag files directly into the editor or use File → Open</li>
            <li><b>Edit:</b> Start typing - syntax highlighting activates automatically</li>
            <li><b>Preview:</b> For HTML/Markdown/XML files, use View menu for live preview</li>
            <li><b>Customize:</b> Format menu for fonts, word wrap, and theme options</li>
        </ol>
        
        <h3 style="color: #c678dd; margin: 20px 0 10px 0;">Tips</h3>
        <ul style="margin: 0 0 15px 20px; padding: 0;">
            <li>Enable <b>Auto Save</b> in File menu for automatic saving</li>
            <li>Use <b>Recent Files</b> to quickly access your work</li>
            <li>XML files support validation - check Format menu</li>
            <li>Backup files auto-recover on restart after unexpected closure</li>
            <li>Status bar shows word count, encoding, and cursor position</li>
        </ul>
        
        <h3 style="color: #98c379; margin: 20px 0 10px 0;">Supported File Types</h3>
        <p style="margin: 0 0 10px 0;"><b>Programming:</b> Python, JavaScript, TypeScript, HTML, CSS, JSON, XML, C/C++, Java, C#, Go, Rust, PHP, Ruby</p>
        <p style="margin: 0 0 20px 0;"><b>Documents:</b> Markdown, Plain Text, Configuration files (INI, YAML, TOML), Shell scripts</p>
        
        <p style="color: #5c6370; font-size: 12px; margin: 20px 0 0 0; text-align: center;">
            Built with PyQt6 | © 2025 G.L.K.N | Version 1.0
        </p>
        </div>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle(f"About {APP_NAME}")
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    # --- Recent Files ---
    def get_recent_files(self):
        return self.settings.value("recentFiles", [], type=list)[:MAX_RECENT_FILES]

    def update_recent_files(self, file_path):
        recent = self.get_recent_files()
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        self.settings.setValue("recentFiles", recent[:MAX_RECENT_FILES])

    def populate_recent_files(self):
        """Simplified with partial instead of lambdas"""
        self.recent_menu.clear()
        recent = self.get_recent_files()
        
        if not recent:
            action = self.recent_menu.addAction("No Recent Files")
            action.setEnabled(False)
            return
        
        for i, file_path in enumerate(recent):
            action = self.recent_menu.addAction(f"&{i+1} {os.path.basename(file_path)}")
            action.setData(file_path)
            # Use partial instead of lambda to avoid reference issues
            action.triggered.connect(partial(self.open_recent_file, file_path))
        
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Clear Recent Files", self.clear_recent_files)

    def open_recent_file(self, file_path):
        if os.path.exists(file_path):
            if self.maybe_save():
                encoding = detect_encoding_with_bom(file_path) or DEFAULT_ENCODING
                self.load_file(file_path, encoding)
        else:
            QMessageBox.warning(self, "File Not Found", f"File not found:\n{file_path}")
            recent = self.get_recent_files()
            if file_path in recent:
                recent.remove(file_path)
                self.settings.setValue("recentFiles", recent)

    def clear_recent_files(self):
        self.settings.setValue("recentFiles", [])

    # --- Helpers ---
    def get_last_dir(self, key):
        return self.settings.value(f"lastDir/{key}", QDir.homePath())

    def save_last_dir(self, key, file_path):
        self.settings.setValue(f"lastDir/{key}", os.path.dirname(file_path))

    # --- Drag and Drop ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(self.is_text_file(url.toLocalFile()) for url in urls if url.isLocalFile()):
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if self.is_text_file(file_path) and self.maybe_save():
                    encoding = detect_encoding_with_bom(file_path) or DEFAULT_ENCODING
                    self.load_file(file_path, encoding)
                    break

    def is_text_file(self, file_path):
        if not os.path.isfile(file_path):
            return False
        
        # Check extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext in TEXT_EXTENSIONS:
            return True
        
        # Check file size
        if os.path.getsize(file_path) > MAX_TEXT_FILE_SIZE:
            return False
        
        # Sample content
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(1024)
                if b'\x00' in sample:  # Binary file marker
                    return False
                sample.decode('utf-8')
                return True
        except Exception:
            return False

    # --- Events ---
    def closeEvent(self, event):
        if self._is_busy:
            reply = QMessageBox.question(self, "Operation in Progress",
                                       "A file operation is in progress. Exit anyway?",
                                       QMessageBox.StandardButton.Yes | 
                                       QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        
        if self.maybe_save():
            self.backup_timer.stop()
            self.autosave_timer.stop()
            self.stats_timer.stop()  # Ensure stats timer is stopped
            self.saveSettings()
            
            # Clean up backups
            backup_dir = get_backup_dir()
            try:
                for f in os.listdir(backup_dir):
                    if f.endswith('.backup'):
                        os.remove(os.path.join(backup_dir, f))
            except Exception:
                pass
            
            event.accept()
        else:
            event.ignore()

def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    
    notepad = Notepad()
    notepad.show()
    
    # Handle command line file
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        encoding = detect_encoding_with_bom(sys.argv[1]) or DEFAULT_ENCODING
        QTimer.singleShot(100, lambda: notepad.load_file(sys.argv[1], encoding))
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()