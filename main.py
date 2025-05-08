import sys
import os
import platform
import time
import logging
import codecs # For BOM detection
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QFileDialog, QMessageBox, QStatusBar,
    QVBoxLayout, QWidget, QMenuBar, QMenu, QFontDialog, QLabel, QDialog,
    QPushButton, QLineEdit, QCheckBox, QGridLayout, QPlainTextEdit,
    QInputDialog, QDialogButtonBox, QSizePolicy, QSpacerItem, QColorDialog,
)
from PyQt6.QtGui import (
    QAction, QFont, QColor, QPalette, QFontMetrics, QKeySequence, QPainter,
    QTextFormat, QTextCursor, QTextDocument, QIcon, QDesktopServices, QActionGroup, QPageLayout
)
from PyQt6.QtCore import (
    Qt, QSize, QSettings, QTimer, QThread, QObject, pyqtSignal, QRect, QPoint,
    QFileInfo, QDir, QUrl, QStandardPaths, QFile, QTextStream, QIODevice,QChar,QMarginsF,
    QMarginsF
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

# Import the syntax highlighting module
import syntax_highlighter

# --- Configuration ---
APP_NAME = "Notepad --"
ORG_NAME = "InterMoor"  # <<< CHANGE THIS FOR DISTRIBUTION >>>
BACKUP_INTERVAL_MS = 30 * 1000  # 30 seconds for backup check
AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000 # 5 minutes for autosave
STATS_UPDATE_INTERVAL_MS = 400  # Update stats when idle for 400ms
MAX_RECENT_FILES = 10
DEFAULT_ENCODING = 'utf-8' # Used if BOM/user doesn't specify
BACKUP_DIR_NAME = "backups"

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
    if original_path:
        base_name = os.path.basename(original_path)
        # Sanitize base_name slightly in case of unusual chars? Maybe not necessary for backup.
        return os.path.join(get_backup_dir(), f"{base_name}.{timestamp}.backup")
    else:
        return os.path.join(get_backup_dir(), f"untitled.{timestamp}.backup")

def detect_encoding_with_bom(filepath):
    """
    Detects encoding based on BOM (Byte Order Mark).
    Returns the detected encoding name (lowercase string) or None if no BOM found.
    """
    try:
        with open(filepath, 'rb') as f:
            bom = f.read(4) # Read first 4 bytes
    except IOError:
        return None # Cannot read file

    # Check common BOMs
    if bom.startswith(codecs.BOM_UTF8):
        return 'utf-8-sig' # Special variant recognizing the BOM
    elif bom.startswith(codecs.BOM_UTF32_LE):
        return 'utf-32-le'
    elif bom.startswith(codecs.BOM_UTF32_BE):
        return 'utf-32-be'
    elif bom.startswith(codecs.BOM_UTF16_LE):
        return 'utf-16-le'
    elif bom.startswith(codecs.BOM_UTF16_BE):
        return 'utf-16-be'
    # Python's built-in open() with utf-8 often handles utf-8-sig correctly,
    # but detecting it explicitly can be useful. For consistency, let's
    # usually just return 'utf-8' if utf-8-sig is found.
    if bom.startswith(codecs.BOM_UTF8):
        return 'utf-8'

    # No known BOM detected
    return None

# --- Worker for Background Tasks ---
class FileWorker(QObject):
    finished = pyqtSignal(str, str) # Emits content and detected/used encoding on success
    error = pyqtSignal(str)         # Emits error message on failure
    progress = pyqtSignal(int)      # Emits progress percentage

    def __init__(self, file_path, encoding=DEFAULT_ENCODING, content_to_save=None):
        super().__init__()
        self.file_path = file_path
        self.requested_encoding = encoding # Encoding user/detection suggested
        self.content_to_save = content_to_save
        self._is_running = True

    def run(self):
        effective_encoding = self.requested_encoding
        if not effective_encoding: effective_encoding = DEFAULT_ENCODING # Fallback

        try:
            if self.content_to_save is not None:
                # --- Saving ---
                logging.info(f"Saving file '{self.file_path}' with encoding '{effective_encoding}' in background.")
                # Add BOM for UTF variants if specified (Python adds automatically for utf-*-sig)
                # Note: PyQt handles this often, but explicit can be safer. Let's stick to standard names for now.
                write_encoding = effective_encoding
                if effective_encoding.lower() == 'utf-8-sig':
                    write_encoding = 'utf-8-sig' # Ensure BOM is written for UTF-8 if requested
                # Python's 'utf-16' implies native byte order + BOM. utf-16-le/be avoid BOM by default.
                # Be explicit if you need LE/BE *without* BOM, or use utf-16-sig if needed.
                # Let's keep requested encoding name for now.

                total_size = len(self.content_to_save) # Approximate, actual bytes may vary
                bytes_written = 0
                chunk_size = 1024 * 1024 # 1MB chunks

                with open(self.file_path, 'w', encoding=write_encoding, errors='replace') as f:
                    start_index = 0
                    while start_index < total_size:
                        if not self._is_running:
                            raise InterruptedError("Save operation cancelled.")
                        # This is an approximation for progress based on characters
                        end_index = min(start_index + chunk_size, total_size)
                        chunk = self.content_to_save[start_index:end_index]
                        written_bytes_in_chunk = len(chunk.encode(write_encoding, errors='replace'))
                        f.write(chunk)
                        bytes_written += written_bytes_in_chunk # More accurate byte count
                        progress_percent = int((bytes_written / len(self.content_to_save.encode(write_encoding, errors='replace'))) * 100) if total_size > 0 else 100
                        self.progress.emit(progress_percent)
                        start_index = end_index

                if self._is_running:
                    self.finished.emit("", effective_encoding) # Pass back encoding used
                else:
                    try: os.remove(self.file_path)
                    except OSError: pass
                    self.error.emit("Save cancelled.")

            else:
                # --- Loading ---
                logging.info(f"Loading file '{self.file_path}' with encoding '{effective_encoding}' in background.")
                file_size = os.path.getsize(self.file_path)
                read_bytes = 0
                content = ""
                chunk_size = 1024 * 1024

                try:
                    with open(self.file_path, 'r', encoding=effective_encoding, errors='replace') as f:
                        while True:
                            if not self._is_running:
                                raise InterruptedError("Load operation cancelled.")
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            content += chunk
                            read_bytes += len(chunk.encode(effective_encoding, errors='replace'))
                            progress_percent = int((read_bytes / file_size) * 100) if file_size > 0 else 100
                            self.progress.emit(progress_percent)
                    final_encoding = effective_encoding # If read succeeded, this encoding worked
                except UnicodeDecodeError as e:
                    # If the initial encoding failed, maybe try a common fallback?
                    # For simplicity, we now rely on BOM detection + user choice first.
                    # We will emit an error.
                    logging.error(f"Encoding error reading file {self.file_path} with {effective_encoding}: {e}")
                    self.error.emit(f"Encoding Error: Could not decode file with {effective_encoding.upper()}.\nTry reopening with a different encoding.\nDetails: {e}")
                    return # Don't proceed
                except Exception as e_inner: # Catch other IOErrors during read loop
                    raise e_inner # Re-raise to outer handler

                if self._is_running:
                    self.finished.emit(content, final_encoding) # Return content and used encoding
                else:
                    self.error.emit("Load cancelled.")

        except FileNotFoundError:
            logging.error(f"File not found: {self.file_path}")
            self.error.emit(f"Error: File not found\n'{self.file_path}'")
        except IOError as e:
            logging.error(f"IO Error reading/writing file {self.file_path}: {e}")
            # Provide cleaner message for common permission error
            if isinstance(e, PermissionError):
                self.error.emit(f"Error: Permission denied accessing file:\n'{self.file_path}'")
            else:
                self.error.emit(f"Error reading/writing file:\n{str(e)}")
        # UnicodeDecodeError handled inside loading block
        except InterruptedError as e:
            logging.warning(f"File operation interrupted: {e}")
            # Error emitted within the specific block
        except Exception as e:
            logging.exception(f"Unexpected error during file operation for {self.file_path}: {e}")
            self.error.emit(f"An unexpected error occurred:\n{str(e)}")

    def stop(self):
        self._is_running = False

# --- Line Number Area Widget ---
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFixedWidth(self.calculate_width()) # Initial width

    def calculate_width(self):
        line_count = max(1, self.editor.blockCount())
        digits = len(str(line_count))
        # Use FontMetrics for accurate calculation
        padding = self.editor.fontMetrics().horizontalAdvance(' ' * 2) + 6 # Adjust padding as needed
        width = self.fontMetrics().horizontalAdvance('9' * digits) + padding
        return width

    def sizeHint(self):
        return QSize(self.calculate_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)

    def update_width(self):
        # Called when line count changes significantly or font changes
        new_width = self.calculate_width()
        if new_width != self.width():
            self.setFixedWidth(new_width)
            self.editor.updateLineNumberAreaMargin() # Ensure margin updates when width does


class TextEditWithLineNumbers(QPlainTextEdit): # Using QPlainTextEdit
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_metrics = QFontMetrics(self.font())
        self.lineNumberArea = LineNumberArea(self)
        self.current_line_color = QColor(Qt.GlobalColor.darkGray).lighter(110)
        self.line_number_color = QColor(Qt.GlobalColor.gray)

        self.blockCountChanged.connect(self.lineNumberArea.update_width)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaMargin()
        self.highlightCurrentLine() # Initial highlight


    def setFont(self, font: QFont):
        """Override setFont to update font metrics and line number area."""
        super().setFont(font)
        self._font_metrics = QFontMetrics(self.font())
        self.lineNumberArea.setFont(font) # Sync line number font
        self.lineNumberArea.update_width() # Width likely changes with font

    def fontMetrics(self) -> QFontMetrics:
        """Return cached font metrics."""
        return self._font_metrics

    def set_colors(self, text_color, background_color, current_line_bg, line_num_color):
        """Sets colors for the editor and line numbers."""
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, text_color)
        palette.setColor(QPalette.ColorRole.Base, background_color)
        self.setPalette(palette)

        self.current_line_color = current_line_bg
        self.line_number_color = line_num_color
        self.lineNumberArea.update() # Repaint line numbers with new color
        self.highlightCurrentLine()  # Re-apply highlight with new color

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        bg_color = self.palette().color(QPalette.ColorRole.Base)
        painter.fillRect(event.rect(), bg_color)

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        # Use integer division for top offset calculation (more reliable)
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        width = self.lineNumberArea.width()
        height = self.fontMetrics().height() # Use cached metrics
        painter.setFont(self.lineNumberArea.font()) # Use area's font
        painter.setPen(self.line_number_color)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                # Adjusted right padding (match update_width's padding roughly)
                right_padding = self.fontMetrics().horizontalAdvance(' ') + 3
                painter.drawText(0, top, width - right_padding, height,
                                 Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            # Use int() for height addition
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def updateLineNumberAreaMargin(self):
        self.setViewportMargins(self.lineNumberArea.width(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            # Adjust update rectangle width if line numbers width has changed
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
             self.lineNumberArea.update_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberArea.width(), cr.height()))

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(self.current_line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def showLineNumbers(self, show):
        self.lineNumberArea.setVisible(show)
        if show:
            self.updateLineNumberAreaMargin()
            # Force width update when showing, font might have changed while hidden
            self.lineNumberArea.update_width()
        else:
            self.setViewportMargins(0, 0, 0, 0)

# --- Find/Replace Dialog ---
class FindReplaceDialog(QDialog):
    find_next = pyqtSignal(str, bool, bool, bool) # text, case_sensitive, whole_word, search_down
    replace_one = pyqtSignal(str, str, bool, bool, bool) # find_text, replace_text, cs, ww, sd
    replace_all = pyqtSignal(str, str, bool, bool) # find_text, replace_text, cs, ww

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find / Replace")

        # Widgets
        self.find_label = QLabel("Find:")
        self.find_edit = QLineEdit()
        self.replace_label = QLabel("Replace with:")
        self.replace_edit = QLineEdit()
        self.case_checkbox = QCheckBox("Match &case") # Added accelerator
        self.word_checkbox = QCheckBox("&Whole word")
        self.down_checkbox = QCheckBox("Search &down")
        self.down_checkbox.setChecked(True)

        self.find_button = QPushButton("&Find Next")
        self.replace_button = QPushButton("&Replace")
        self.replace_all_button = QPushButton("Replace &All")
        self.close_button = QPushButton("Close")

        # Layout
        layout = QGridLayout(self)
        layout.addWidget(self.find_label, 0, 0)
        layout.addWidget(self.find_edit, 0, 1, 1, 3)
        layout.addWidget(self.replace_label, 1, 0)
        layout.addWidget(self.replace_edit, 1, 1, 1, 3)

        checkbox_layout = QVBoxLayout()
        checkbox_layout.addWidget(self.case_checkbox)
        checkbox_layout.addWidget(self.word_checkbox)
        checkbox_layout.addWidget(self.down_checkbox)
        layout.addLayout(checkbox_layout, 2, 0, 1, 2)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.find_button)
        button_layout.addWidget(self.replace_button)
        button_layout.addWidget(self.replace_all_button)
        button_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout, 0, 4, 3, 1)

        # Connections
        self.find_button.clicked.connect(self.on_find)
        self.replace_button.clicked.connect(self.on_replace)
        self.replace_all_button.clicked.connect(self.on_replace_all)
        self.close_button.clicked.connect(self.reject)
        self.find_edit.textChanged.connect(self.update_button_state)

        # Set shortcuts for find/replace buttons if dialog focused
        # Note: This might conflict with main window shortcuts sometimes
        # QShortcut(QKeySequence.StandardKey.FindNext, self, self.on_find) # Maybe disable if problematic
        # QShortcut(QKeySequence(Qt.Modifier.SHIFT | Qt.Key.Key_F3), self, self.find_previous) # F3/Shift+F3 common

        self.update_button_state()

        # Style (Ensure parent provides colors or fallback gracefully)
        if hasattr(parent, 'colors') and parent.colors:
            try:
                 self.setStyleSheet(f"""
                     QDialog {{ background-color: {parent.colors.get('black', '#1e222a')}; color: {parent.colors.get('white', '#abb2bf')}; }}
                     QLabel, QCheckBox {{ color: {parent.colors.get('white', '#abb2bf')}; }}
                     QLineEdit {{
                         background-color: {parent.colors.get('gray2', '#2e323a')};
                         color: {parent.colors.get('white', '#abb2bf')};
                         border: 1px solid {parent.colors.get('gray3', '#545862')};
                         padding: 3px;
                     }}
                     QPushButton {{
                         background-color: {parent.colors.get('gray2', '#2e323a')}; color: {parent.colors.get('white', '#abb2bf')};
                         border: 1px solid {parent.colors.get('gray3', '#545862')}; padding: 5px; min-width: 80px;
                     }}
                     QPushButton:hover {{ background-color: {parent.colors.get('gray3', '#545862')}; }}
                     QPushButton:pressed {{ background-color: {parent.colors.get('blue', '#61afef')}; }}
                     QPushButton:disabled {{ background-color: {parent.colors.get('gray3', '#545862')}; color: {parent.colors.get('gray4', '#6d8dad')}; border-color: {parent.colors.get('gray3', '#545862')};}}
                 """)
            except Exception as e:
                 logging.warning(f"Could not apply custom styling to FindReplaceDialog: {e}")


    def update_button_state(self):
        find_text = self.find_edit.text()
        can_find = bool(find_text)
        self.find_button.setEnabled(can_find)
        self.replace_button.setEnabled(can_find)
        self.replace_all_button.setEnabled(can_find)

    def on_find(self):
        text = self.find_edit.text()
        if text:
            self.find_next.emit(
                text,
                self.case_checkbox.isChecked(),
                self.word_checkbox.isChecked(),
                self.down_checkbox.isChecked()
            )

    # Helper for Find Previous (if using Shift+F3 shortcut)
    # def find_previous(self):
    #     text = self.find_edit.text()
    #     if text:
    #         self.find_next.emit(
    #             text,
    #             self.case_checkbox.isChecked(),
    #             self.word_checkbox.isChecked(),
    #             False # Search Up
    #         )

    def on_replace(self):
        find_text = self.find_edit.text()
        replace_text = self.replace_edit.text()
        if find_text:
            self.replace_one.emit(
                find_text,
                replace_text,
                self.case_checkbox.isChecked(),
                self.word_checkbox.isChecked(),
                self.down_checkbox.isChecked()
            )

    def on_replace_all(self):
        find_text = self.find_edit.text()
        replace_text = self.replace_edit.text()
        if find_text:
            self.replace_all.emit(
                find_text,
                replace_text,
                self.case_checkbox.isChecked(),
                self.word_checkbox.isChecked()
            )

    def showEvent(self, event):
        super().showEvent(event)
        self.find_edit.selectAll()
        self.find_edit.setFocus()

    def keyPressEvent(self, event):
        # Handle Enter key to trigger "Find Next" or close?
        # Default dialog behavior is often sufficient (button shortcuts)
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

# --- Main Notepad Application ---
class Notepad(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.current_file = None
        self.current_encoding = DEFAULT_ENCODING
        self.backup_file_path = None
        self.last_save_content = "" # To check if backup is needed
        self.file_thread = None
        self.file_worker = None
        self._is_loading_or_saving = False
        self.current_highlighter = None
        self._find_replace_dialog = None # Lazily loaded

        # <<<--- Fullscreen State Fix --- >>>
        self._pre_fullscreen_state = Qt.WindowState.WindowNoState
        self._pre_fullscreen_menu_visible = True
        self._pre_fullscreen_status_visible = True
        # <<<--------------------------- >>>

        # <<<--- Stats Throttling --- >>>
        self._stats_update_timer = QTimer(self)
        self._stats_update_timer.setSingleShot(True)
        self._stats_update_timer.setInterval(STATS_UPDATE_INTERVAL_MS)
        self._stats_update_timer.timeout.connect(self._performDocumentStatsUpdate)
        # <<<------------------------ >>>

        # Color palette
        self.colors = {
            "black": "#1e222a", "white": "#abb2bf", "gray2": "#2e323a",
            "gray3": "#545862", "gray4": "#6d8dad", "blue": "#61afef",
            "green": "#7EC7A2", "red": "#e06c75", "orange": "#caaa6a",
            "yellow": "#EBCB8B", "pink": "#c678dd", "border": "#1e222a",
            "current_line_bg": "#2c313a", "line_num_color": "#636d83"
        }

        self.initUI()
        self.loadSettings() # Load settings which might restore geometry/state
        self.setupTimers()  # Start backup timer (AutoSave depends on settings)
        self.checkForRecovery()
        self.updateStatus() # Initial status update (now includes throttled stats)

        # Enable Drag and Drop
        self.setAcceptDrops(True)

        # Sync fullscreen action state AFTER settings are potentially loaded
        self.fullscreen_action.setChecked(self.isFullScreen())


    def initUI(self):
        self.setWindowTitle("Untitled - " + APP_NAME)
        # Default geometry if settings don't provide it
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = TextEditWithLineNumbers()
        self.text_edit.setFrameStyle(0) # No frame/border
        layout.addWidget(self.text_edit)

        # Status bar setup
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.cursor_pos_label = QLabel("Ln 1, Col 1")
        self.encoding_label = QLabel(f"Encoding: {self.current_encoding.upper()}")
        self.doc_stats_label = QLabel("Words: 0 Chars: 0 Lines: 1") # Initial
        self.status_bar.addPermanentWidget(self.cursor_pos_label)
        self.status_bar.addPermanentWidget(self.encoding_label)
        self.status_bar.addPermanentWidget(self.doc_stats_label)

        # Connect signals
        self.text_edit.cursorPositionChanged.connect(self.updateCursorPosition)
        self.text_edit.textChanged.connect(self.onTextChanged) # Handles modified, actions, starts stats timer
        self.text_edit.document().modificationChanged.connect(self.updateTitle) # More reliable title update

        self.createMenus()
        self.setupDarkTheme()

        # Font setup (default, overridden by loadSettings)
        default_font = QFont('Consolas', 10)
        if platform.system() == "Darwin": default_font = QFont('Menlo', 11)
        elif platform.system() != "Windows": default_font = QFont('Monospace', 10)
        self.font = default_font # Store current base font
        self.text_edit.setFont(self.font)
        # text_edit.setFont automatically updates line number font/width

        # Word wrap (default, overridden by loadSettings)
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def createMenus(self):
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu('&File')
        self.add_action(file_menu, '&New', self.newFile, QKeySequence.StandardKey.New)
        self.add_action(file_menu, '&Open...', self.openFileTrigger, QKeySequence.StandardKey.Open)
        self.recent_files_menu = file_menu.addMenu("Open Recent")
        self.recent_files_menu.aboutToShow.connect(self.populateRecentFiles)
        self.recent_files_actions = []
        self.add_action(self.recent_files_menu, "Clear Menu", self.clearRecentFiles, enabled=False) # Placeholder/End Marker
        file_menu.addSeparator()
        self.save_action = self.add_action(file_menu, '&Save', self.saveFile, QKeySequence.StandardKey.Save)
        self.save_as_action = self.add_action(file_menu, 'Save &As...', self.saveFileAsTrigger, QKeySequence.StandardKey.SaveAs) # Use standard SaveAs
        self.add_action(file_menu, 'Save Copy As...', self.saveFileCopyTrigger, 'Ctrl+Alt+S')

        self.save_copy_action = self.add_action(file_menu, 'Save Copy As...', self.saveFileCopyTrigger, 'Ctrl+Alt+S')
        file_menu.addSeparator()
        # Auto Save Action (will be populated during settings load/save if exists)
        self.auto_save_action = QAction('&Auto Save', self, checkable=True)
        self.auto_save_action.triggered.connect(self.toggleAutoSave)
        file_menu.addAction(self.auto_save_action)
        file_menu.addSeparator()
        self.add_action(file_menu, '&Print...', self.printDocument, QKeySequence.StandardKey.Print)
        file_menu.addSeparator()
        self.add_action(file_menu, 'E&xit', self.close, QKeySequence.StandardKey.Quit)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu('&Edit')
        self.undo_action = self.add_action(edit_menu, '&Undo', self.text_edit.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = self.add_action(edit_menu, '&Redo', self.text_edit.redo, QKeySequence.StandardKey.Redo)
        edit_menu.addSeparator()
        self.cut_action = self.add_action(edit_menu, 'Cu&t', self.text_edit.cut, QKeySequence.StandardKey.Cut)
        self.copy_action = self.add_action(edit_menu, '&Copy', self.text_edit.copy, QKeySequence.StandardKey.Copy)
        self.paste_action = self.add_action(edit_menu, '&Paste', self.text_edit.paste, QKeySequence.StandardKey.Paste)
        self.delete_action = self.add_action(edit_menu, '&Delete', lambda: self.text_edit.textCursor().removeSelectedText(), QKeySequence.StandardKey.Delete)
        edit_menu.addSeparator()
        self.add_action(edit_menu, '&Find...', self.showFindDialog, QKeySequence.StandardKey.Find)
        self.add_action(edit_menu, 'Find Next', self.findNext, QKeySequence.StandardKey.FindNext)
        self.add_action(edit_menu, 'Find Previous', self.findPrevious, QKeySequence.StandardKey.FindPrevious)
        self.add_action(edit_menu, '&Replace...', self.showReplaceDialog, QKeySequence.StandardKey.Replace)
        edit_menu.addSeparator()
        self.add_action(edit_menu, '&Go To Line...', self.goToLine, QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_G))
        edit_menu.addSeparator()
        self.add_action(edit_menu, 'Select &All', self.text_edit.selectAll, QKeySequence.StandardKey.SelectAll)

        # --- Format Menu ---
        format_menu = menu_bar.addMenu('F&ormat')
        self.word_wrap_action = self.add_action(format_menu, '&Word Wrap', self.toggleWordWrap, checkable=True)
        self.add_action(format_menu, '&Font...', self.chooseFont)
        format_menu.addSeparator()
        self.syntax_highlight_action = self.add_action(format_menu, 'S&yntax Highlighting',
                                                     self.toggleSyntaxHighlighting, checkable=True, checked=True) # Assume default on

        # --- View Menu ---
        view_menu = menu_bar.addMenu('&View')
        self.line_num_action = self.add_action(view_menu, 'Show &Line Numbers', self.toggleLineNumbers, checkable=True, checked=True)
        view_menu.addSeparator()
        self.add_action(view_menu, 'Zoom &In', self.zoomIn, QKeySequence.StandardKey.ZoomIn) # Ctrl+= (usually) or Ctrl++
        self.add_action(view_menu, 'Zoom &Out', self.zoomOut, QKeySequence.StandardKey.ZoomOut) # Ctrl+-
        self.add_action(view_menu, '&Restore Default Zoom', self.resetZoom, QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_0))
        view_menu.addSeparator()
        self.statusbar_action = self.add_action(view_menu, 'Show &Status Bar', self.toggleStatusBar, checkable=True, checked=True)
        # Fullscreen action needs initial state based on current window state AFTER settings load
        self.fullscreen_action = self.add_action(
            view_menu, 'Toggle &Full Screen', self.toggleFullScreen, # Corrected slot connection
            QKeySequence(Qt.Key.Key_F11), checkable=True, checked=self.isFullScreen())

        # --- Encoding Menu ---
        self.encoding_menu = menu_bar.addMenu('&Encoding')
        # Use codecs module to get a wider list of standard encodings maybe? Too complex? Stick to common.
        encodings = ['UTF-8', 'UTF-8-SIG', 'UTF-16', 'Latin-1', 'Windows-1252', 'ASCII']
        self.encoding_group = QActionGroup(self)
        self.encoding_group.setExclusive(True)

        def create_encoding_trigger(encoding_name):
            # Closure to capture encoding_name correctly for lambda
             # Try to get Python codec name robustly
            py_enc = encoding_name.lower().split('(')[0].strip()
            # Special case for utf-8-sig
            if encoding_name.upper() == 'UTF-8-SIG': py_enc = 'utf-8-sig'
            return lambda checked: self.changeEncoding(py_enc) if checked else None

        for enc in encodings:
             py_enc_lambda_safe = enc.lower().split('(')[0].strip()
             if enc.upper() == 'UTF-8-SIG': py_enc_lambda_safe = 'utf-8-sig' # Needed for setData

             action = QAction(enc, self, checkable=True)
             action.setData(py_enc_lambda_safe)
             # IMPORTANT: Use a helper function or lambda with default arg to capture encoding name correctly
             action.triggered.connect(create_encoding_trigger(enc))

             self.encoding_menu.addAction(action)
             self.encoding_group.addAction(action)
             if py_enc_lambda_safe == self.current_encoding:
                 action.setChecked(True)

        self.encoding_menu.addSeparator()
        self.add_action(self.encoding_menu, 'Reopen with Encoding...', self.reopenWithEncoding)
        self.add_action(self.encoding_menu, 'Save with Encoding...', self.saveWithEncoding)

        # --- Help Menu ---
        help_menu = menu_bar.addMenu('&Help')
        self.add_action(help_menu, '&About', self.showAboutDialog)

        self.updateActionStates() # Initial state based on empty editor

    def add_action(self, menu, text, slot, shortcut=None, checkable=False, checked=False, enabled=True, icon=None):
        action = QAction(text, self)
        if icon:
            action.setIcon(QIcon.fromTheme(icon) if isinstance(icon, str) else icon)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
        action.setEnabled(enabled)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def updateActionStates(self):
        has_selection = self.text_edit.textCursor().hasSelection()
        doc = self.text_edit.document()
        can_undo = doc.isUndoAvailable()
        can_redo = doc.isRedoAvailable()
        is_modified = doc.isModified()
        is_readonly = self.text_edit.isReadOnly()

        self.save_action.setEnabled(is_modified and not is_readonly)
        # Save As and Save Copy should be enabled even if not modified
        self.save_as_action.setEnabled(not is_readonly)
        self.save_copy_action.setEnabled(True)

        self.cut_action.setEnabled(has_selection and not is_readonly)
        self.copy_action.setEnabled(has_selection)
        self.paste_action.setEnabled(self.text_edit.canPaste()) # Use canPaste()
        self.delete_action.setEnabled(has_selection and not is_readonly)

        self.undo_action.setEnabled(can_undo and not is_readonly)
        self.redo_action.setEnabled(can_redo and not is_readonly)

        # More actions? Print maybe always enabled?
        # Find/Replace should depend only on find dialog logic mostly


    def setupDarkTheme(self):
        # Ensure colors dict is valid before proceeding
        if not self.colors or not isinstance(self.colors, dict):
            logging.error("Color dictionary is invalid. Skipping dark theme setup.")
            return

        # Helper to safely get colors with fallback
        def get_color(key, default):
             return self.colors.get(key, default)

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(get_color("black", "#1e222a")))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(get_color("white", "#abb2bf")))
        palette.setColor(QPalette.ColorRole.Base, QColor(get_color("black", "#1e222a"))) # Editor background
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(get_color("gray2", "#2e323a")))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(get_color("black", "#1e222a")))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(get_color("white", "#abb2bf")))
        palette.setColor(QPalette.ColorRole.Text, QColor(get_color("white", "#abb2bf"))) # Editor text
        palette.setColor(QPalette.ColorRole.Button, QColor(get_color("gray2", "#2e323a")))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(get_color("white", "#abb2bf")))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(get_color("red", "#e06c75")))
        palette.setColor(QPalette.ColorRole.Link, QColor(get_color("blue", "#61afef")))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(get_color("blue", "#61afef"))) # Selection background
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(get_color("black", "#1e222a"))) # Ensure selection text readable on blue
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(get_color("gray3", "#545862")))
        # Disabled states (more subtle)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(get_color("gray3", "#545862")))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(get_color("gray3", "#545862")))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(get_color("gray3", "#545862")))

        app = QApplication.instance()
        app.setPalette(palette)

        # Stylesheet (robust get_color calls)
        app_style = f"""
            QMainWindow, QWidget {{
                background-color: {get_color("black", "#1e222a")};
                color: {get_color("white", "#abb2bf")};
                border: none;
            }}
            QPlainTextEdit {{
                background-color: {get_color("black", "#1e222a")};
                color: {get_color("white", "#abb2bf")};
                selection-background-color: {get_color("blue", "#61afef")};
                selection-color: {get_color("black", "#1e222a")};
                border: none;
                padding-left: 2px;
            }}
            LineNumberArea {{ /* Specific type name */
                 background-color: {get_color("black", "#1e222a")};
                 border: none;
                 /* Text color set directly in editor method */
            }}
            QMenuBar {{
                background-color: {get_color("gray2", "#2e323a")}; /* Diff color for menu bar */
                color: {get_color("white", "#abb2bf")};
                border-bottom: 1px solid {get_color("gray3", "#545862")};
            }}
            QMenuBar::item {{
                padding: 4px 10px;
                background-color: transparent; /* Important */
            }}
            QMenuBar::item:selected {{
                background-color: {get_color("blue", "#61afef")};
                color: {get_color("black", "#1e222a")};
            }}
            QMenuBar::item:pressed {{
                 background-color: {get_color("green", "#7EC7A2")};
            }}
            QMenu {{
                background-color: {get_color("gray2", "#2e323a")};
                color: {get_color("white", "#abb2bf")};
                border: 1px solid {get_color("gray3", "#545862")};
                padding: 5px;
            }}
            QMenu::item {{
                padding: 4px 20px;
                background-color: transparent; /* Important */
            }}
            QMenu::item:selected {{ /* Covers hovered state too */
                background-color: {get_color("blue", "#61afef")};
                color: {get_color("black", "#1e222a")};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {get_color("gray3", "#545862")};
                margin: 4px 0;
            }}
            QStatusBar {{
                background-color: {get_color("black", "#1e222a")};
                color: {get_color("white", "#abb2bf")};
                border-top: 1px solid {get_color("gray3", "#545862")};
            }}
            QStatusBar QLabel {{
                color: {get_color("white", "#abb2bf")};
                padding: 0 8px;
                border: none;
                background-color: transparent;
            }}
            QStatusBar::item {{ border: none; }}

            QDialog {{
                background-color: {get_color("black", "#1e222a")};
                color: {get_color("white", "#abb2bf")};
            }}
            QPushButton {{
                background-color: {get_color("gray2", "#2e323a")};
                color: {get_color("white", "#abb2bf")};
                border: 1px solid {get_color("gray3", "#545862")};
                padding: 5px 10px; min-height: 20px; min-width: 70px;
                border-radius: 3px; /* Slightly rounded */
            }}
            QPushButton:hover {{
                background-color: {get_color("gray3", "#545862")};
                border-color: {get_color("gray4", "#6d8dad")};
            }}
            QPushButton:pressed {{ background-color: {get_color("blue", "#61afef")}; }}
            QPushButton:disabled {{
                background-color: {get_color("gray2", "#2e323a")}; /* Less contrast */
                color: {get_color("gray3", "#545862")};
                border-color: {get_color("gray3", "#545862")};
            }}

            QMessageBox {{ background-color: {get_color("black", "#1e222a")}; }}
            QMessageBox QLabel {{ color: {get_color("white", "#abb2bf")}; }}
            /* Full QFileDialog styling remains OS dependent */

            QCheckBox, QLabel, QRadioButton {{
                color: {get_color("white", "#abb2bf")};
                background-color: transparent;
            }}
            QCheckBox::indicator {{
                 width: 13px; height: 13px; border-radius: 2px;
                 border: 1px solid {get_color("gray3", "#545862")};
                 background-color: {get_color("gray2", "#2e323a")};
            }}
            QCheckBox::indicator:checked {{
                 background-color: {get_color("blue", "#61afef")};
                 border-color: {get_color("blue", "#61afef")};
                 /* Optional checkmark SVG? image: url(:/icons/check.svg); */
            }}
            QCheckBox::indicator:hover {{ border-color: {get_color("gray4", "#6d8dad")}; }}

            QLineEdit {{
                background-color: {get_color("gray2", "#2e323a")};
                color: {get_color("white", "#abb2bf")};
                border: 1px solid {get_color("gray3", "#545862")};
                padding: 3px; border-radius: 3px;
            }}
            QLineEdit:focus {{ border-color: {get_color("blue", "#61afef")}; }}

            QScrollBar:vertical {{
                border: 1px solid {get_color("gray3", "#545862")};
                background: {get_color("black", "#1e222a")};
                width: 12px; margin: 12px 0 12px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {get_color("gray3", "#545862")};
                min-height: 20px; border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {get_color("gray4", "#6d8dad")}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: {get_color("gray2", "#2e323a")};
                height: 12px; subcontrol-position: top; subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:vertical {{ subcontrol-position: bottom; }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{ height: 0px; }} /* Hide default arrows */
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

            QScrollBar:horizontal {{
                 border: 1px solid {get_color("gray3", "#545862")};
                 background: {get_color("black", "#1e222a")};
                 height: 12px; margin: 0 12px 0 12px;
            }}
            QScrollBar::handle:horizontal {{
                 background: {get_color("gray3", "#545862")};
                 min-width: 20px; border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {get_color("gray4", "#6d8dad")}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                 border: none; background: {get_color("gray2", "#2e323a")};
                 width: 12px; subcontrol-position: left; subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:horizontal {{ subcontrol-position: right; }}
            QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {{ width: 0px; }} /* Hide default arrows */
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
        """
        try:
            app.setStyleSheet(app_style)
        except Exception as e:
            logging.error(f"Error applying stylesheet: {e}")


        # Explicitly set editor colors after theme/palette setup
        self.text_edit.set_colors(QColor(get_color("white", "#abb2bf")),
                                  QColor(get_color("black", "#1e222a")),
                                  QColor(get_color("current_line_bg", "#2c313a")),
                                  QColor(get_color("line_num_color", "#636d83")))

    # --- Settings Persistence ---

    def loadSettings(self):
        try:
            logging.info("Loading settings...")
            # Window geometry
            if geom_bytes := self.settings.value("geometry"):
                self.restoreGeometry(geom_bytes)
            else:
                # Default size already set in initUI
                try:
                    screen_geometry = QApplication.primaryScreen().availableGeometry()
                    self.move(screen_geometry.center() - self.rect().center())
                except Exception as e:
                    logging.warning(f"Could not center window: {e}") # Gracefully handle if screen info fails

            # --- FIX: Robust window state loading ---
            restored_state_int = Qt.WindowState.WindowNoState.value # Default integer value
            try:
                # Try reading as an integer first (new format)
                # Provide the default integer value here as well
                value = self.settings.value("windowState", restored_state_int, type=int)

                if isinstance(value, int):
                     restored_state_int = value
                else:
                     # Handle case where it might still return non-int despite type hint (Defensive)
                     logging.warning(f"Read unexpected type {type(value)} for windowState, expected int. Using default.")
                     # Ensure default is used if type is wrong
                     restored_state_int = Qt.WindowState.WindowNoState.value

            except (TypeError, ValueError) as e:
                # This can happen if the stored value is the old byte array format or corrupted
                logging.warning(f"Could not load windowState as integer: {e}. Using default state.")
                restored_state_int = Qt.WindowState.WindowNoState.value # Use default
            except Exception as e:
                 logging.error(f"Unexpected error loading windowState: {e}. Using default state.")
                 restored_state_int = Qt.WindowState.WindowNoState.value # Use default

            # Create the WindowState enum from the verified integer
            restored_state = Qt.WindowState(restored_state_int)

            # Apply the state, handling potential fullscreen restoration issue
            if restored_state & Qt.WindowState.WindowFullScreen:
                logging.warning("Saved state was fullscreen, restoring as Maximized or Normal instead.")
                restored_state &= ~Qt.WindowState.WindowFullScreen # Remove fullscreen flag
                if restored_state & Qt.WindowState.WindowMaximized:
                    # Apply Maximized + other flags (implicitly removes fullscreen)
                    self.setWindowState(restored_state)
                else:
                    # Apply Normal state flags (implicitly removes fullscreen)
                    self.setWindowState(Qt.WindowState.WindowNoState)
            else:
                # Apply the non-fullscreen state directly
                self.setWindowState(restored_state)

            # --- End Fix ---

            # Font
            font_family = self.settings.value("font/family", self.font.family())
            font_size = self.settings.value("font/size", self.font.pointSize(), type=int)
            font_bold = self.settings.value("font/bold", self.font.bold(), type=bool)
            font_italic = self.settings.value("font/italic", self.font.italic(), type=bool)
            # Ensure font is created correctly even if settings are slightly off
            try:
                self.font = QFont(font_family, font_size if font_size > 0 else 10, QFont.Weight.Bold if font_bold else QFont.Weight.Normal, font_italic)
                self.text_edit.setFont(self.font) # Applies to editor + line numbers
            except Exception as e:
                 logging.error(f"Error applying loaded font settings: {e}. Using default.")
                 # Apply a known default font if loading fails
                 default_font = QFont('Consolas', 10)
                 if platform.system() == "Darwin": default_font = QFont('Menlo', 11)
                 elif platform.system() != "Windows": default_font = QFont('Monospace', 10)
                 self.font = default_font
                 self.text_edit.setFont(self.font)


            # Word Wrap
            wrap = self.settings.value("format/wordWrap", False, type=bool)
            self.word_wrap_action.setChecked(wrap)
            self.toggleWordWrap(wrap, save_settings=False) # Apply setting, avoid loop

            # Line Numbers
            show_lines = self.settings.value("view/showLineNumbers", True, type=bool)
            self.line_num_action.setChecked(show_lines)
            self.toggleLineNumbers(show_lines, save_settings=False)

            # Status Bar
            show_statusbar = self.settings.value("view/showStatusBar", True, type=bool)
            self.statusbar_action.setChecked(show_statusbar)
            self.toggleStatusBar(show_statusbar, save_settings=False)

            # Syntax Highlighting Enabled State
            highlight = self.settings.value("format/syntaxHighlighting", True, type=bool)
            self.syntax_highlight_action.setChecked(highlight)
            # Apply initial highlighting later based on file/setting

            # Auto Save
            enable_autosave = self.settings.value("file/autoSaveEnabled", False, type=bool)
            if self.auto_save_action: # Check if action exists
                 self.auto_save_action.setChecked(enable_autosave)
                 if enable_autosave:
                     self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)
            else:
                 logging.warning("Auto Save action not found during settings load.")


            # Recent Files loaded dynamically via populateRecentFiles

            logging.info("Settings loaded.")

        except Exception as e:
            logging.exception("Major error during settings load. Using defaults.") # Log full traceback
            # Minimal fallback state if the whole function fails badly
            self.resize(800, 600)
            try:
                 screen_geometry = QApplication.primaryScreen().availableGeometry()
                 self.move(screen_geometry.center() - self.rect().center())
            except Exception: pass # Best effort centering

    def saveSettings(self):
        """Saves window geometry, state, font, and other settings."""
        try:
            logging.info("Saving settings...")
            # Save state *only if not fullscreen*
            if not self.isFullScreen():
                 self.settings.setValue("geometry", self.saveGeometry())
                 # Save combined state (Normal/Maximized/Minimized etc)
                 # Remove fullscreen flag just in case before saving state
                 current_state_flags = self.windowState() & ~Qt.WindowState.WindowFullScreen
                 # --- FIX: Use .value to get the integer representation ---
                 self.settings.setValue("windowState", current_state_flags.value)
                 # --- End Fix ---
            else:
                # If closing while fullscreen (should be prevented by closeEvent), don't save geom/state
                logging.warning("Attempted to save settings while fullscreen. Skipping geometry/windowState save.")

            self.settings.setValue("font/family", self.font.family())
            self.settings.setValue("font/size", self.font.pointSize())
            self.settings.setValue("font/bold", self.font.bold())
            self.settings.setValue("font/italic", self.font.italic())
            self.settings.setValue("format/wordWrap", self.word_wrap_action.isChecked())
            self.settings.setValue("view/showLineNumbers", self.line_num_action.isChecked())
            self.settings.setValue("view/showStatusBar", self.statusbar_action.isChecked())
            self.settings.setValue("format/syntaxHighlighting", self.syntax_highlight_action.isChecked())

            if hasattr(self, 'auto_save_action'):
                self.settings.setValue("file/autoSaveEnabled", self.auto_save_action.isChecked())

            # Recent files are saved when added/cleared

            self.settings.sync() # Explicit sync
            logging.info("Settings saved.")
        except Exception as e:
            logging.exception("Error saving settings.") # Keep detailed logging



    # --- Timers (Backup, AutoSave, Stats Update) ---

    def setupTimers(self):
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self.backupUnsavedChanges)
        self.backup_timer.start(BACKUP_INTERVAL_MS) # Start unconditionally

        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autoSaveFile)
        # AutoSave timer started/stopped based on settings (in loadSettings/toggleAutoSave)

        # Stats timer is setup in __init__


    # --- Backup and Recovery ---

    def backupUnsavedChanges(self):
        if self.text_edit.document().isModified() and not self._is_loading_or_saving:
            current_content = self.text_edit.toPlainText()
            if current_content != self.last_save_content:
                if not self.backup_file_path:
                    self.backup_file_path = get_backup_filename(self.current_file)
                    logging.info(f"Creating initial backup file: {self.backup_file_path}")

                if not self.backup_file_path: return # Should not happen if creation works

                try:
                    temp_backup_path = self.backup_file_path + ".tmp"
                    with open(temp_backup_path, 'w', encoding=DEFAULT_ENCODING, errors='replace') as f:
                        f.write(current_content)
                    os.replace(temp_backup_path, self.backup_file_path)
                    logging.debug(f"Backed up changes to: {os.path.basename(self.backup_file_path)}")
                    # Don't update last_save_content here, only on actual file save
                except Exception as e:
                    logging.error(f"Failed to write backup file {self.backup_file_path}: {e}")
                    self.backup_file_path = None # Invalidate path if write failed


    def clearBackupFile(self):
        if self.backup_file_path and os.path.exists(self.backup_file_path):
            try:
                os.remove(self.backup_file_path)
                logging.info(f"Removed backup file: {os.path.basename(self.backup_file_path)}")
            except OSError as e:
                logging.error(f"Failed to remove backup file {self.backup_file_path}: {e}")
        self.backup_file_path = None


    def checkForRecovery(self):
        try:
            backup_dir = get_backup_dir()
            backup_files = [f for f in os.listdir(backup_dir) if f.endswith(".backup")]
            if not backup_files: return

            backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)), reverse=True)
            latest_backup = os.path.join(backup_dir, backup_files[0])

            original_filename = "Untitled"
            if ".untitled." not in backup_files[0]:
                try:
                    parts = backup_files[0].split('.')
                    if len(parts) > 2 and parts[-1] == 'backup':
                        original_filename = '.'.join(parts[:-2])
                except Exception: pass # Ignore parsing errors

            backup_mtime = datetime.fromtimestamp(os.path.getmtime(latest_backup)).strftime('%Y-%m-%d %H:%M:%S')

            reply = QMessageBox.question(
                self, "Recover Unsaved File?",
                f"An unsaved file ('{original_filename}') from a previous session was found.\n"
                f"Do you want to recover it?\n\n(Backup created: {backup_mtime})",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Discard,
                QMessageBox.StandardButton.Yes # Default to Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                try:
                    with open(latest_backup, 'r', encoding=DEFAULT_ENCODING, errors='replace') as f:
                        content = f.read()
                    self.text_edit.setPlainText(content)
                    self.text_edit.document().setModified(True)
                    self.backup_file_path = latest_backup # Keep track of this recovery backup
                    # We *don't* set current_file here, user must "Save As"
                    if original_filename != "Untitled":
                        self.setWindowTitle(f"*{original_filename} (Recovered) - {APP_NAME}")
                    else:
                        self.setWindowTitle(f"*Untitled (Recovered) - {APP_NAME}")
                    self.last_save_content = "" # Needs save/backup check
                    logging.info(f"Recovered content from {os.path.basename(latest_backup)}")
                    self.updateStatus() # Update stats for recovered content
                except Exception as e:
                    logging.error(f"Failed to read recovery file {latest_backup}: {e}")
                    QMessageBox.critical(self, "Recovery Failed", f"Could not read backup file:\n{os.path.basename(latest_backup)}\n\nError: {e}")
                    self.clearBackupFile() # Also removes path var
                    try: os.remove(latest_backup) # Attempt cleanup
                    except OSError: pass
            elif reply == QMessageBox.StandardButton.No:
                 logging.info(f"User chose not to recover {latest_backup}. File remains.")
            else: # Discard
                 self.clearBackupFile() # Also removes path var
                 try: os.remove(latest_backup)
                 except OSError as e: logging.error(f"Failed to discard backup {latest_backup}: {e}")
                 logging.info(f"Discarded backup file: {os.path.basename(latest_backup)}")
        except Exception as e:
             logging.exception("Error during backup recovery check.")


    def cleanupAllBackups(self):
        """Removes all .backup and .backup.tmp files on clean exit."""
        backup_dir = get_backup_dir()
        logging.info(f"Cleaning up backups in {backup_dir}...")
        try:
            for item in os.listdir(backup_dir):
                if item.endswith(".backup") or item.endswith(".backup.tmp"):
                    item_path = os.path.join(backup_dir, item)
                    try:
                        os.remove(item_path)
                        logging.info(f"Cleaned up backup file: {item}")
                    except OSError as e:
                        logging.error(f"Failed to clean up backup file {item_path}: {e}")
        except FileNotFoundError:
            logging.info("Backup directory not found, no cleanup needed.")
        except Exception as e:
            logging.error(f"Error during backup cleanup: {e}")


    # --- File Operations (with Background Worker) ---

    def newFile(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return
        if self.maybeSave():
            self.text_edit.clear()
            self.current_file = None
            self.current_encoding = DEFAULT_ENCODING
            doc = self.text_edit.document()
            doc.clearUndoRedoStacks() # Clear history for new file
            doc.setModified(False)
            self.clearBackupFile()
            self.last_save_content = ""

            # Clear syntax highlighting
            if self.current_highlighter:
                self.current_highlighter.setDocument(None)
                self.current_highlighter = None
            # If artifacts remain: self.text_edit.viewport().update()

            self.updateTitle()
            self.updateStatus()
            self.text_edit.setReadOnly(False)


    def openFileTrigger(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return
        if self.maybeSave():
            enc_filters = [ # Simple filter list
                "All Files (*)",
                "Text Files (*.txt)",
            ]
            last_dir = self.settings.value("paths/lastOpenDir", QDir.homePath())
            file_name, _ = QFileDialog.getOpenFileName(
                self, "Open File", last_dir, ";;".join(enc_filters)
            )
            if file_name:
                self.settings.setValue("paths/lastOpenDir", QFileInfo(file_name).absolutePath())
                # Attempt BOM detection first
                detected_encoding = detect_encoding_with_bom(file_name)
                if detected_encoding:
                     logging.info(f"BOM detected encoding: {detected_encoding}")
                     self.startFileOperation(file_name, encoding=detected_encoding, is_saving=False)
                else:
                     logging.info(f"No BOM detected, using default encoding: {DEFAULT_ENCODING}")
                     # Could add dialog here to ask user if unsure
                     self.startFileOperation(file_name, encoding=DEFAULT_ENCODING, is_saving=False)


    def saveFile(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return True # Avoid loop in maybeSave
        if self.text_edit.isReadOnly():
            QMessageBox.warning(self, "Read Only", "This document is read-only.")
            return False
        if self.current_file:
            # Use the currently associated encoding for saving
            return self.startFileOperation(self.current_file, encoding=self.current_encoding, is_saving=True)
        else:
            return self.saveFileAsTrigger()


    def saveFileAsTrigger(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return False
        # Allow "Save As" even if read-only, effectively making a copy
        return self._saveAsDialog(save_copy=False)


    def saveFileCopyTrigger(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return False
        # Always allowed
        return self._saveAsDialog(save_copy=True)


    def _saveAsDialog(self, save_copy=False):
        default_filename = os.path.basename(self.current_file) if self.current_file else "untitled.txt"
        last_dir = self.settings.value("paths/lastSaveDir", QDir.homePath())
        default_path = os.path.join(last_dir, default_filename)

        # Offer common encoding options (or use current as default filter)
        enc_filters_map = { # Display Name -> Codec Name
            f"Text ({self.current_encoding.upper()}) (*.txt)": self.current_encoding,
            "UTF-8 (*.txt)": "utf-8",
            "UTF-8 with BOM (*.txt)": "utf-8-sig",
            "UTF-16 LE (*.txt)": "utf-16-le",
            "UTF-16 BE (*.txt)": "utf-16-be",
            "Latin-1 (*.txt)": "latin-1",
            "All Files (*)": self.current_encoding # Fallback for 'All files' selection
        }
        filters_list = list(enc_filters_map.keys())
        dialog = QFileDialog(self, "Save As" if not save_copy else "Save Copy As")
        dialog.setDirectory(last_dir)
        dialog.selectFile(default_filename)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilters(filters_list)
        dialog.setDefaultSuffix("txt") # Suggest .txt

        if dialog.exec():
            file_name = dialog.selectedFiles()[0]
            selected_filter = dialog.selectedNameFilter()
            chosen_encoding = enc_filters_map.get(selected_filter, self.current_encoding) # Use selected or current

            self.settings.setValue("paths/lastSaveDir", QFileInfo(file_name).absolutePath())

            # Add '.txt' suffix if none provided and it wasn't 'All Files (*)'
            if not QFileInfo(file_name).suffix() and selected_filter != "All Files (*)":
                file_name += ".txt"
                logging.info(f"Adding .txt suffix: {file_name}")

            return self.startFileOperation(file_name, encoding=chosen_encoding, is_saving=True, is_copy=save_copy)
        return False # User cancelled


    def startFileOperation(self, file_path, encoding, is_saving, is_copy=False):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return False

        self._is_loading_or_saving = True
        # Only set editor ReadOnly during load, not save (to allow modification check etc.)
        if not is_saving:
             self.text_edit.setReadOnly(True)
        self.updateActionStates()
        action_verb = "Saving" if is_saving else "Loading"
        self.status_bar.showMessage(f"{action_verb} '{os.path.basename(file_path)}'...", 0)

        content_to_save = self.text_edit.toPlainText() if is_saving else None

        # Create worker and thread
        self.file_thread = QThread(self) # Parent thread to main window thread
        self.file_worker = FileWorker(file_path, encoding, content_to_save)
        self.file_worker.moveToThread(self.file_thread)

        # Connect signals
        self.file_worker.finished.connect(self.onFileOperationFinished)
        self.file_worker.error.connect(self.onFileOperationError)
        self.file_worker.progress.connect(self.onFileOperationProgress)
        self.file_thread.started.connect(self.file_worker.run)
        # Cleanup connections MUST happen correctly
        self.file_worker.finished.connect(self.file_thread.quit)
        self.file_worker.error.connect(self.file_thread.quit)
        self.file_thread.finished.connect(self.file_worker.deleteLater) # Worker cleans up after thread finishes
        self.file_thread.finished.connect(self.file_thread.deleteLater) # Thread cleans up itself
        # resetFileOperationState called from finished/error slots directly for immediate UI update
        self.file_worker.finished.connect(self.resetFileOperationState)
        self.file_worker.error.connect(self.resetFileOperationState)

        # Store context (ensure thread-safety if accessed outside main thread - not the case here)
        self._current_op_info = {'path': file_path, 'encoding': encoding, 'saving': is_saving, 'copy': is_copy}

        self.file_thread.start()
        return True


    def onFileOperationFinished(self, content_or_blank, used_encoding): # Worker sends back used encoding
        op_info = self._current_op_info
        if not op_info: return # Should not happen, maybe check if reset state already ran

        action_verb = 'saved' if op_info['saving'] else 'loaded'
        logging.info(f"File {action_verb}: {op_info['path']} (Encoding: {used_encoding})")
        self.status_bar.showMessage(f"File {action_verb}: {os.path.basename(op_info['path'])} ({used_encoding.upper()})", 5000)

        if op_info['saving']:
            if not op_info['copy']:
                self.current_file = op_info['path']
                self.current_encoding = used_encoding # IMPORTANT: Update based on what was used
                self.text_edit.document().setModified(False)
                self.last_save_content = self.text_edit.toPlainText() # Re-read content after successful save
                self.clearBackupFile()
                self.updateTitle()
                self.updateRecentFiles(self.current_file)
                self.updateEncodingStatus()
                # Re-apply highlighting (extension might have changed)
                self.apply_syntax_highlighting()
            else:
                 QMessageBox.information(self, "Copy Saved", f"File copy saved successfully to:\n{op_info['path']} ({used_encoding.upper()})")
                 # Do not change current file state

        else: # Loading
            self.text_edit.blockSignals(True)
            self.text_edit.document().blockSignals(True)
            try:
                self.text_edit.setPlainText(content_or_blank) # This is the loaded content
                self.current_file = op_info['path']
                self.current_encoding = used_encoding # Update based on successful load encoding
                self.text_edit.document().setModified(False)
                # Clear undo stack after loading a new file
                self.text_edit.document().clearUndoRedoStacks()
                self.clearBackupFile()
                self.last_save_content = content_or_blank # Initial content
                self.updateTitle()
                self.updateRecentFiles(self.current_file)
                self.updateEncodingStatus()
                self.text_edit.moveCursor(QTextCursor.MoveOperation.Start)
            finally:
                self.text_edit.blockSignals(False)
                self.text_edit.document().blockSignals(False)

            # Apply syntax highlighting AFTER loading and setting state
            self.apply_syntax_highlighting()
            # Update status manually after blocking signals
            self.updateStatus()

        # Note: resetFileOperationState is now connected directly to the signals


    def onFileOperationError(self, error_message):
        op_info = self._current_op_info
        if not op_info: return

        action_verb = "Save" if op_info['saving'] else "Load"
        logging.error(f"{action_verb} operation failed for {op_info['path']}: {error_message}")
        # Provide slightly more context in the dialog title
        QMessageBox.critical(self, f"{action_verb} Failed", error_message)
        self.status_bar.showMessage(f"{action_verb} failed", 5000)
        # If load failed, we might be left with a read-only editor
        # Resetting state ensures it becomes editable again.
        # Note: resetFileOperationState is now connected directly to the signals


    def onFileOperationProgress(self, percentage):
        if self._current_op_info: # Check if context exists
            op_info = self._current_op_info
            action_verb = 'Saving' if op_info['saving'] else 'Loading'
            self.status_bar.showMessage(f"{action_verb} '{os.path.basename(op_info['path'])}'... {percentage}%", 0)


    def resetFileOperationState(self):
        """Resets state flags and UI elements after a file operation completes or fails."""
        self._is_loading_or_saving = False
        # Crucially, ensure editor is editable unless loading explicitly failed in a way
        # that suggests the file *should* be readonly (e.g. permissions? Hard to tell here).
        # Generally, just make it editable.
        self.text_edit.setReadOnly(False)
        self.updateActionStates() # Refresh action enabled state
        # Status might be showing progress or success/fail, let last message persist briefly
        # If needed, clear specific progress message here:
        # self.status_bar.clearMessage() # Or update with cursor pos/encoding again
        self.updateStatus()

        self.file_thread = None # Allow GC
        self.file_worker = None
        self._current_op_info = None # Clear context
        logging.debug("File operation state reset.")


    def cancelFileOperation(self):
        if self.file_worker and self.file_thread and self.file_thread.isRunning():
            logging.info("Attempting to cancel file operation...")
            self.status_bar.showMessage("Cancelling...", 0)
            self.file_worker.stop()
            # The worker thread should quit soon after and signal error/finished
            # We rely on the cleanup connected to thread.finished


    def maybeSave(self):
        if not self.text_edit.document().isModified():
            return True
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return False

        display_name = self.getDisplayName()
        title = f"Save changes to '{display_name}'?"
        text = f"The document '{display_name}' has unsaved changes.\n" \
               "Do you want to save them before closing?"

        # Use standard button roles for better cross-platform behavior
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(APP_NAME)
        msg_box.setText(text)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        save_button = msg_box.addButton("Save", QMessageBox.ButtonRole.AcceptRole) # Or DestructiveRole?
        discard_button = msg_box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(save_button)
        msg_box.setEscapeButton(cancel_button)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()

        if clicked_button == save_button:
            return self.saveFile() # Returns True if save succeeds/starts, False if user cancels Save As
        elif clicked_button == discard_button:
            self.clearBackupFile() # User explicitly discarded
            return True
        else: # Cancelled
            return False

    # --- Auto Save ---
    def toggleAutoSave(self, checked):
        if checked:
            self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)
            logging.info(f"Auto Save enabled (Interval: {AUTOSAVE_INTERVAL_MS / 1000}s).")
            self.status_bar.showMessage("Auto Save enabled", 3000)
        else:
            self.autosave_timer.stop()
            logging.info("Auto Save disabled.")
            self.status_bar.showMessage("Auto Save disabled", 3000)
        # Save setting immediately when toggled
        self.settings.setValue("file/autoSaveEnabled", checked)
        self.settings.sync()


    def autoSaveFile(self):
        if self.text_edit.document().isModified() and self.current_file and not self._is_loading_or_saving:
            if not self.text_edit.isReadOnly():
                logging.info(f"Auto-saving file: {self.current_file}")
                # Show a subtle indicator, maybe? For now, just log.
                # self.status_bar.showMessage(f"Auto-saving '{os.path.basename(self.current_file)}'...", 2000) # Can be annoying
                self.startFileOperation(self.current_file, encoding=self.current_encoding, is_saving=True)
            else:
                 logging.warning(f"Auto-save skipped for read-only file: {self.current_file}")
        elif not self.current_file and self.text_edit.document().isModified():
             # Backup unsaved, untitled files periodically
             self.backupUnsavedChanges()

    # --- Recent Files ---

    def getRecentFiles(self):
        """Retrieves list, ensuring basic validity."""
        files = self.settings.value("recentFiles/list", [], type=list)
        # Basic filtering for non-empty strings
        return [f for f in files if isinstance(f, str) and f]

    def updateRecentFiles(self, filename):
        if not filename or not isinstance(filename, str): return
        try:
             # Normalize path separators for consistency (optional, but good)
             norm_filename = QDir.toNativeSeparators(filename)

             recent_files = self.getRecentFiles()
             # Remove existing entries (case-insensitive compare on Windows?)
             # Using normalized path helps. Let's stick to case-sensitive for now.
             if norm_filename in recent_files:
                  recent_files.remove(norm_filename)
             recent_files.insert(0, norm_filename)
             del recent_files[MAX_RECENT_FILES:]
             self.settings.setValue("recentFiles/list", recent_files)
             self.settings.sync()
             logging.debug(f"Updated recent files: Added '{os.path.basename(norm_filename)}'")
        except Exception as e:
             logging.error(f"Failed to update recent files: {e}")

    def populateRecentFiles(self):
        # Assumes 'Clear Menu' action is the last one added in createMenus
        clear_action = self.recent_files_menu.actions()[-1]

        # Clear existing file actions (items before 'Clear Menu')
        current_actions = self.recent_files_menu.actions()
        for i in range(len(current_actions) - 1): # Exclude clear_action
            action = current_actions[i]
            self.recent_files_menu.removeAction(action)
            action.deleteLater()
        self.recent_files_actions.clear() # Clear internal list too

        recent_files = self.getRecentFiles()

        if not recent_files:
            no_recent_action = QAction("No Recent Files", self)
            no_recent_action.setEnabled(False)
            self.recent_files_menu.insertAction(clear_action, no_recent_action)
            self.recent_files_actions.append(no_recent_action) # Track it
            clear_action.setEnabled(False)
            return

        clear_action.setEnabled(True)
        for i, filename in enumerate(recent_files):
            # Shorten display name if path is very long
            display_path = filename
            max_display_len = 60 # Example limit
            if len(display_path) > max_display_len:
                 # Show first part and last part, e.g., "C:/Users/.../folder/file.txt"
                 path_parts = Path(display_path).parts
                 if len(path_parts) > 3:
                      display_path = f"{path_parts[0]}{os.sep}{path_parts[1]}{os.sep}...{os.sep}{path_parts[-2]}{os.sep}{path_parts[-1]}"
                 else: # Or just truncate simply
                      display_path = "..." + display_path[-max_display_len:]


            action_text = f"&{i+1} {display_path}" # Add mnemonic
            action = QAction(action_text, self)
            action.setData(filename) # Store full, original path
            action.setToolTip(filename)
            action.triggered.connect(self.openRecentFile)
            self.recent_files_menu.insertAction(clear_action, action)
            self.recent_files_actions.append(action)


    def openRecentFile(self):
        if self._is_loading_or_saving:
            self.showBusyMessage()
            return
        sender_action = self.sender()
        if sender_action and isinstance(sender_action, QAction):
            file_path = sender_action.data()
            if file_path and isinstance(file_path, str):
                 if self.maybeSave():
                      if QFile.exists(file_path):
                          detected_encoding = detect_encoding_with_bom(file_path) or DEFAULT_ENCODING
                          self.startFileOperation(file_path, encoding=detected_encoding, is_saving=False)
                      else:
                          QMessageBox.warning(self, "File Not Found",
                                              f"The file could not be found:\n{file_path}\n\nIt may have been moved or deleted. Remove from list?")
                          self.removeRecentFile(file_path)


    def clearRecentFiles(self):
        if QMessageBox.question(self, "Clear Recent Files", "Are you sure you want to clear the recent files list?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
             self.settings.remove("recentFiles/list")
             self.settings.sync()
             # populateRecentFiles() will be called automatically when menu is shown next
             logging.info("Recent files list cleared.")

    def removeRecentFile(self, filename):
        if not filename: return
        try:
             norm_filename = QDir.toNativeSeparators(filename)
             recent_files = self.getRecentFiles()
             if norm_filename in recent_files:
                  recent_files.remove(norm_filename)
                  self.settings.setValue("recentFiles/list", recent_files)
                  self.settings.sync()
                  logging.info(f"Removed '{os.path.basename(norm_filename)}' from recent files.")
             # Update menu display if currently shown? Not strictly needed.
        except Exception as e:
             logging.error(f"Failed to remove recent file {filename}: {e}")

    # --- Editor Features ---

    def _ensure_find_replace_dialog(self):
        """Creates the find/replace dialog if it doesn't exist."""
        if self._find_replace_dialog is None:
            logging.debug("Creating FindReplaceDialog instance.")
            self._find_replace_dialog = FindReplaceDialog(self)
            self._find_replace_dialog.find_next.connect(self.findText)
            self._find_replace_dialog.replace_one.connect(self.replaceOne)
            self._find_replace_dialog.replace_all.connect(self.replaceAll)
            # Optional: Cleanup on close if preferred over keeping instance alive
            # self._find_replace_dialog.finished.connect(lambda: setattr(self, '_find_replace_dialog', None))

    def showFindDialog(self):
        self._ensure_find_replace_dialog()

        # Configure for Find mode
        self._find_replace_dialog.replace_edit.hide()
        self._find_replace_dialog.replace_label.hide()
        self._find_replace_dialog.replace_button.hide()
        self._find_replace_dialog.replace_all_button.hide()
        self._find_replace_dialog.setWindowTitle("Find")
        # Ensure minimum height is reasonable when widgets are hidden
        self._find_replace_dialog.adjustSize()


        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
             selected_text = cursor.selectedText().replace(QChar.SpecialCharacter.ParagraphSeparator, '\n').replace(QChar.SpecialCharacter.LineSeparator, '\n')
             if '\n' not in selected_text and len(selected_text) < 100: # Don't prefill multi-line or huge selections
                self._find_replace_dialog.find_edit.setText(selected_text)

        # Show non-modally
        if not self._find_replace_dialog.isVisible():
            self._find_replace_dialog.show()
        self._find_replace_dialog.activateWindow()
        self._find_replace_dialog.raise_()
        self._find_replace_dialog.find_edit.setFocus()
        self._find_replace_dialog.find_edit.selectAll()


    def showReplaceDialog(self):
        self._ensure_find_replace_dialog()

        # Configure for Replace mode
        self._find_replace_dialog.replace_edit.show()
        self._find_replace_dialog.replace_label.show()
        self._find_replace_dialog.replace_button.show()
        self._find_replace_dialog.replace_all_button.show()
        self._find_replace_dialog.setWindowTitle("Find / Replace")
        self._find_replace_dialog.adjustSize() # Adjust size now that widgets are shown


        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
             selected_text = cursor.selectedText().replace(QChar.SpecialCharacter.ParagraphSeparator, '\n').replace(QChar.SpecialCharacter.LineSeparator, '\n')
             if '\n' not in selected_text and len(selected_text) < 100:
                 self._find_replace_dialog.find_edit.setText(selected_text)

        if not self._find_replace_dialog.isVisible():
            self._find_replace_dialog.show()
        self._find_replace_dialog.activateWindow()
        self._find_replace_dialog.raise_()
        self._find_replace_dialog.find_edit.setFocus()
        self._find_replace_dialog.find_edit.selectAll()


    def findText(self, text, case_sensitive, whole_word, search_down):
        if not text: return False

        flags = QTextDocument.FindFlag(0)
        if case_sensitive: flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word: flags |= QTextDocument.FindFlag.FindWholeWords
        if not search_down: flags |= QTextDocument.FindFlag.FindBackward

        found = self.text_edit.find(text, flags)

        if not found:
            # Give feedback, maybe offer to wrap search
            self.status_bar.showMessage(f"'{text}' not found.", 3000)
            # Ask to search from beginning/end?
            cursor = self.text_edit.textCursor()
            current_pos = cursor.position()
            start_pos = 0
            end_pos = self.text_edit.document().characterCount() -1

            if (search_down and current_pos > start_pos) or (not search_down and current_pos < end_pos):
                 reply = QMessageBox.information(self, "Find",
                                              f"'{text}' not found.\nSearch from {'beginning' if search_down else 'end'}?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.Yes:
                     cursor.movePosition(QTextCursor.MoveOperation.Start if search_down else QTextCursor.MoveOperation.End)
                     self.text_edit.setTextCursor(cursor)
                     found = self.text_edit.find(text, flags) # Try again from new position
                     if not found: self.status_bar.showMessage(f"'{text}' not found.", 3000)

        # Store parameters for F3/Shift+F3
        self._last_find_params = {'text': text, 'cs': case_sensitive, 'ww': whole_word, 'down': search_down}
        return found


    def findNext(self):
        # Check if dialog is open AND has focus? Maybe not needed.
        # If dialog exists, pull latest params from it.
        if self._find_replace_dialog:
            text = self._find_replace_dialog.find_edit.text()
            cs = self._find_replace_dialog.case_checkbox.isChecked()
            ww = self._find_replace_dialog.word_checkbox.isChecked()
            down = self._find_replace_dialog.down_checkbox.isChecked()
            self.findText(text, cs, ww, down)
        elif hasattr(self, '_last_find_params') and self._last_find_params['text']:
             # Use last parameters if dialog closed or never opened
             params = self._last_find_params
             self.findText(params['text'], params['cs'], params['ww'], True) # Force search down for F3
        else:
             # No previous search, show dialog
             self.showFindDialog()


    def findPrevious(self):
        if self._find_replace_dialog:
             text = self._find_replace_dialog.find_edit.text()
             cs = self._find_replace_dialog.case_checkbox.isChecked()
             ww = self._find_replace_dialog.word_checkbox.isChecked()
             # Always search up for Find Previous (Shift+F3)
             self.findText(text, cs, ww, False) # Force search up
        elif hasattr(self, '_last_find_params') and self._last_find_params['text']:
             params = self._last_find_params
             self.findText(params['text'], params['cs'], params['ww'], False) # Force search up
        else:
             self.showFindDialog()


    def replaceOne(self, find_text, replace_text, case_sensitive, whole_word, search_down):
        if self.text_edit.isReadOnly(): return
        if not find_text: return

        cursor = self.text_edit.textCursor()
        found_match_at_cursor = False

        # Does current selection match the find criteria?
        if cursor.hasSelection():
             selected_text = cursor.selectedText().replace(QChar.SpecialCharacter.ParagraphSeparator, '\n').replace(QChar.SpecialCharacter.LineSeparator, '\n')
             compare_flags = Qt.CaseSensitivity.Sensitive if case_sensitive else Qt.CaseSensitivity.Insensitive

             if selected_text.compare(find_text, compare_flags) == 0:
                 # Optionally verify whole word here if needed (might be redundant if find() selected it)
                 is_whole_word_match = True # Assume true initially
                 if whole_word:
                      start_pos, end_pos = cursor.selectionStart(), cursor.selectionEnd()
                      if start_pos > 0 and self.text_edit.document().characterAt(start_pos - 1).isalnum(): is_whole_word_match = False
                      if end_pos < self.text_edit.document().characterCount() and self.text_edit.document().characterAt(end_pos).isalnum(): is_whole_word_match = False

                 if not whole_word or is_whole_word_match:
                     cursor.insertText(replace_text)
                     found_match_at_cursor = True

        # Find the next occurrence based on direction
        self.findText(find_text, case_sensitive, whole_word, search_down)


    def replaceAll(self, find_text, replace_text, case_sensitive, whole_word):
        if self.text_edit.isReadOnly(): return
        if not find_text: return

        flags = QTextDocument.FindFlag(0)
        if case_sensitive: flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word: flags |= QTextDocument.FindFlag.FindWholeWords

        count = 0
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock() # Start single undo block
        try:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor) # Set editor cursor to start

            while True:
                # Find next from current position
                # Use QPlainTextEdit's find function which automatically selects
                if self.text_edit.find(find_text, flags):
                     # If found, text is selected, just insert replacement
                     current_cursor = self.text_edit.textCursor() # Get the updated cursor
                     current_cursor.insertText(replace_text)
                     count += 1
                else:
                     # If find returns False, check if we wrapped around already?
                     # QPlainTextEdit.find() wraps by default? No, it doesn't. Stop here.
                     break # No more found
        finally:
            cursor.endEditBlock() # End undo block

        if count > 0:
            self.status_bar.showMessage(f"Replaced {count} occurrence(s).", 5000)
            # Document is implicitly marked modified
        else:
            self.status_bar.showMessage(f"'{find_text}' not found.", 3000)

        # Update last find params for subsequent F3 etc.
        self._last_find_params = {'text': find_text, 'cs': case_sensitive, 'ww': whole_word, 'down': True}


    def goToLine(self):
        max_lines = self.text_edit.blockCount()
        current_line = self.text_edit.textCursor().blockNumber() + 1
        line, ok = QInputDialog.getInt(
            self, "Go To Line", "Enter Line Number (1 to {}):".format(max_lines),
            value=current_line, min=1, max=max_lines
        )
        if ok and line >= 1 and line <= max_lines:
            cursor = self.text_edit.textCursor()
            target_block = self.text_edit.document().findBlockByNumber(line - 1)
            if target_block.isValid():
                cursor.setPosition(target_block.position())
                # Maybe move to start of line content?
                # cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                # while cursor.block().text().startswith((' ', '\t')): cursor.movePosition(...)
                self.text_edit.setTextCursor(cursor)
                self.text_edit.ensureCursorVisible()
                self.text_edit.setFocus() # Focus editor after dialog closes


    def printDocument(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Print Document")
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            # Get settings from printer object after dialog closes
            page_layout = printer.pageLayout()
            # Ensure reasonable margins are set (dialog defaults might be small)
            margins_mm = 15.0
            margins = QMarginsF(margins_mm, margins_mm, margins_mm, margins_mm)
            # Compare with current margins, update only if default/too small?
            # For simplicity, just set them.
            page_layout.setMargins(margins, QPageLayout.Unit.Millimeter)
            printer.setPageLayout(page_layout) # Apply updated layout

            logging.info("Sending document to printer...")
            try:
                 self.text_edit.print_(printer)
                 logging.info("Document print command sent.")
                 self.status_bar.showMessage("Printing...", 3000)
            except Exception as e:
                 logging.error(f"Error during printing: {e}")
                 QMessageBox.critical(self, "Print Error", f"Could not print document.\nError: {e}")
        else:
            logging.info("Print cancelled.")
            self.status_bar.showMessage("Print cancelled.", 3000)


    def changeEncoding(self, encoding):
        # This just sets the target for the *next save*
        if encoding != self.current_encoding:
            self.current_encoding = encoding
            logging.info(f"Set target save encoding to: {encoding}")
            self.updateEncodingStatus()
            # Mark modified, because saving *will* change bytes if encoding is different
            self.text_edit.document().setModified(True)
            QMessageBox.information(self, "Encoding Changed",
                                     f"The encoding for saving this file is now set to {encoding.upper()}.\n"
                                     "This does not change the current text view.\n"
                                     "Use 'Reopen with Encoding...' to reload if text looks incorrect.")


    def reopenWithEncoding(self):
        if self._is_loading_or_saving: self.showBusyMessage(); return
        if not self.current_file: QMessageBox.warning(self, "Reopen", "No file is currently open."); return
        if not QFile.exists(self.current_file): QMessageBox.warning(self, "Reopen", f"File not found:\n{self.current_file}"); return

        if self.maybeSave():
             # More user-friendly encoding list?
             common_encodings = ['utf-8', 'utf-16', 'latin-1', 'windows-1252', 'ascii'] # Add more if needed
             try:
                 current_index = common_encodings.index(self.current_encoding)
             except ValueError:
                 current_index = 0 # Default to UTF-8 index if current not in list

             enc, ok = QInputDialog.getItem(self, "Reopen with Encoding",
                                            "Choose encoding to reload file:", common_encodings,
                                            current_index, editable=True) # Allow custom entry
             if ok and enc:
                 enc = enc.strip().lower()
                 try:
                     ''.encode(enc) # Test if valid codec name
                     logging.info(f"Reopening '{self.current_file}' with encoding '{enc}'.")
                     # Use startFileOperation to handle reload
                     self.startFileOperation(self.current_file, encoding=enc, is_saving=False)
                 except LookupError:
                     QMessageBox.critical(self, "Invalid Encoding", f"The encoding '{enc}' is not recognized by Python.")
                 except Exception as e:
                     QMessageBox.critical(self, "Error", f"An error occurred during reopen setup: {e}")


    def saveWithEncoding(self):
        if self._is_loading_or_saving: self.showBusyMessage(); return False
        if self.text_edit.isReadOnly(): QMessageBox.warning(self, "Read Only", "Cannot save, document is read-only."); return False

        common_encodings = ['utf-8', 'utf-8-sig', 'utf-16le', 'utf-16be', 'latin-1', 'windows-1252', 'ascii'] # Offer LE/BE explicitly?
        # Make names slightly friendlier for dialog
        display_encodings = ['UTF-8', 'UTF-8 (with BOM)', 'UTF-16 LE', 'UTF-16 BE', 'Latin-1 (ISO-8859-1)', 'Windows-1252', 'ASCII']
        codec_map = dict(zip(display_encodings, common_encodings))

        # Select current in list
        current_display = ""
        for disp, codec in codec_map.items():
            if codec == self.current_encoding:
                 current_display = disp
                 break

        enc_display, ok = QInputDialog.getItem(self, "Save with Encoding",
                                          "Choose encoding for saving:", display_encodings,
                                          display_encodings.index(current_display) if current_display else 0,
                                          editable=False) # Don't allow custom here? Safer.
        if ok and enc_display:
            chosen_codec = codec_map.get(enc_display)
            if not chosen_codec: # Should not happen if editable=False
                 QMessageBox.critical(self, "Error", "Internal encoding selection error."); return False

            logging.info(f"Setting save encoding to '{chosen_codec}'.")
            self.current_encoding = chosen_codec
            self.updateEncodingStatus()
            # Now, trigger Save or Save As based on whether file exists
            if self.current_file:
                 return self.startFileOperation(self.current_file, encoding=self.current_encoding, is_saving=True)
            else:
                 return self.saveFileAsTrigger() # Will use the new current_encoding

        return False # User cancelled

    # --- Zoom ---
    def zoomIn(self):
        factor = 1.2 # Scale factor for zoom in (adjust as needed)
        current_size = self.font.pointSizeF() # Use pointSizeF for float
        new_size = max(6.0, current_size + 1.0) # Use fixed increment or factor
        # Or using factor: new_size = max(6.0, current_size * factor)
        new_font = QFont(self.font)
        new_font.setPointSizeF(new_size)
        self.font = new_font # Update base font reference
        self.text_edit.setFont(self.font) # Will update editor, metrics, line numbers
        self.saveSettings()


    def zoomOut(self):
        factor = 1 / 1.2 # Scale factor for zoom out
        current_size = self.font.pointSizeF()
        new_size = max(6.0, current_size - 1.0) # Use fixed increment
        # Or using factor: new_size = max(6.0, current_size * factor)
        new_font = QFont(self.font)
        new_font.setPointSizeF(new_size)
        self.font = new_font
        self.text_edit.setFont(self.font)
        self.saveSettings()


    def resetZoom(self):
        # Restore base font size from settings
        font_family = self.settings.value("font/family", self.font.family()) # Keep saved family
        font_size = self.settings.value("font/size", 10, type=int) # Reload original saved size
        font_bold = self.settings.value("font/bold", self.font.bold(), type=bool)
        font_italic = self.settings.value("font/italic", self.font.italic(), type=bool)
        # Create new font object with base settings
        base_font = QFont(font_family, font_size, QFont.Weight.Bold if font_bold else QFont.Weight.Normal, font_italic)
        self.font = base_font
        self.text_edit.setFont(self.font)
        # Settings will be saved automatically if font changed from current zoomed state


    # --- Syntax Highlighting ---

        # --- Syntax Highlighting ---

    def apply_syntax_highlighting(self):
        current_doc = self.text_edit.document()

        # Detach previous highlighter if exists
        if self.current_highlighter:
            self.current_highlighter.setDocument(None)
            self.current_highlighter = None

        # Only proceed if enabled and we have a file path (or maybe file type context?)
        if not self.syntax_highlight_action.isChecked():
            # If syntax highlighting is globally disabled, ensure the viewport updates
            # to remove any previous highlighting remnants.
            self.text_edit.viewport().update()
            return

        file_to_check = self.current_file
        # If no current file, but content exists, could potentially try to guess? Risky.
        # Let's only highlight based on saved file extension for now.
        if not file_to_check:
             # Ensure no previous formats persist if highlighting is enabled but no file identified
             self.text_edit.viewport().update()
             return

        # Get a new highlighter instance
        # Pass the colors dictionary to the factory/constructor
        highlighter = syntax_highlighter.get_highlighter_for_file(
            file_to_check, current_doc, self.colors
        )

        if highlighter:
            self.current_highlighter = highlighter # Store reference
            # The highlighter automatically associates with the document passed to it.
            _, ext = os.path.splitext(file_to_check)
            file_type = ext.replace('.', '').upper() if ext else "Syntax"
            logging.info(f"Applied {file_type} highlighting to {os.path.basename(file_to_check)}")
            # Initial highlight happens automatically when the document gets text or changes
            # but force a rehighlight immediately for visibility after switching files/enabling.
            self.current_highlighter.rehighlight() # Call on the highlighter instance!
        else:
             # No specific highlighter found for this file type
             # Detaching the previous highlighter (done above) is sufficient.
             # Ensure the viewport updates to reflect the plain text appearance.
             self.text_edit.viewport().update()
             logging.debug(f"No specific highlighter found for {os.path.basename(file_to_check)}")


    def toggleSyntaxHighlighting(self, checked=None):
        """
        Enables, disables, or updates syntax highlighting based on the menu toggle.
        Saves the setting and updates the editor appearance.

        Args:
            checked (bool | None): The desired state. If None, uses the action's state.
        """
        # Determine the state if not explicitly passed
        if checked is None:
            # Ensure the action exists before accessing its state
            if hasattr(self, 'syntax_highlight_action') and self.syntax_highlight_action:
                checked = self.syntax_highlight_action.isChecked()
            else:
                logging.warning("Syntax highlighting action not found. Cannot determine state.")
                return # Exit if action doesn't exist

        # Persist the setting immediately
        # Ensure settings object exists before writing
        if hasattr(self, 'settings'):
            self.settings.setValue("format/syntaxHighlighting", checked)
            # sync() often happens on close or elsewhere, so not strictly needed here unless desired
            # self.settings.sync()
        else:
            logging.warning("Settings object not found. Cannot save syntax highlighting preference.")

        # Apply the change
        if checked:
            # --- Enabling Highlighting ---
            logging.info("Syntax highlighting enabled. Applying...")
            # Show status message only if status bar exists
            if hasattr(self, 'status_bar'):
                self.status_bar.showMessage("Syntax highlighting enabled", 3000)

            # Apply the appropriate highlighter (if any) for the current file/context
            self.apply_syntax_highlighting() # This method handles finding/applying

        else:
            # --- Disabling Highlighting ---
            logging.info("Syntax highlighting disabled.")
            # Show status message only if status bar exists
            if hasattr(self, 'status_bar'):
                self.status_bar.showMessage("Syntax highlighting disabled", 3000)

            # Detach the current highlighter from the document if it exists
            if self.current_highlighter:
                # Use try-except for robustness in case current_highlighter becomes invalid somehow
                try:
                    self.current_highlighter.setDocument(None)
                except Exception as e:
                    logging.error(f"Error detaching highlighter: {e}")
                self.current_highlighter = None # Clear the reference regardless

            # Ensure the text editor repaints to remove the old formatting.
            # Ensure text_edit exists before calling methods on it.
            if hasattr(self, 'text_edit'):
                try:
                    # Calling viewport().update() is the standard way to request a repaint
                    # of the visible area, which should clear old syntax colors.
                    self.text_edit.viewport().update()
                except Exception as e:
                    logging.error(f"Error requesting viewport update: {e}")
            else:
                logging.warning("Text edit widget not found. Cannot update viewport.")


    def toggleSyntaxHighlighting(self, checked=None):
        if checked is None: checked = self.syntax_highlight_action.isChecked()

        self.settings.setValue("format/syntaxHighlighting", checked)
        # No need to sync settings here, happens elsewhere or on close

        if checked:
            # Re-apply highlighting (might find a highlighter now)
            self.apply_syntax_highlighting()
        else:
            # Remove current highlighter
            if self.current_highlighter:
                self.current_highlighter.setDocument(None)
                self.current_highlighter = None
            self.status_bar.showMessage("Syntax highlighting disabled", 3000)
            # Force rehighlight of document with no highlighter to clear colors
            self.text_edit.document().rehighlight()
            # If artifacts remain: self.text_edit.viewport().update()
            


    # --- Fullscreen Mode (Revised) ---

    def toggleFullScreen(self, go_fullscreen):
        """
        Toggles fullscreen mode, saving and restoring previous window state
        and menu/status bar visibility. Argument is the desired state (True=Enter, False=Exit).
        """
        try:
            # Current actual fullscreen state
            is_currently_fullscreen = bool(self.windowState() & Qt.WindowState.WindowFullScreen)

            if not go_fullscreen:
                # --- Exit Fullscreen ---
                if is_currently_fullscreen:
                    logging.info(f"Exiting fullscreen. Restoring state: {self._pre_fullscreen_state}, Menu: {self._pre_fullscreen_menu_visible}, Status: {self._pre_fullscreen_status_visible}")

                    # Restore bars BEFORE changing window state (might be safer)
                    self.menuBar().setVisible(self._pre_fullscreen_menu_visible)
                    self.status_bar.setVisible(self._pre_fullscreen_status_visible)

                    # --- FIX: Simplify state restoration ---
                    # Use showNormal/showMaximized directly. They handle removing the fullscreen flag.
                    if self._pre_fullscreen_state & Qt.WindowState.WindowMaximized:
                         self.showMaximized()
                    else:
                         self.showNormal()
                    # --- End Fix ---

                    # Ensure action matches state AFTER state change
                    if self.fullscreen_action.isChecked():
                        self.fullscreen_action.setChecked(False)

                else: # Request to exit but wasn't fullscreen? Odd.
                    logging.warning("Attempted to exit fullscreen, but window wasn't in fullscreen state.")
                    # Force ensure bars match settings and window is normal
                    # self.setWindowState(Qt.WindowState.WindowNoState) # showNormal does this
                    self.showNormal()
                    self.menuBar().setVisible(True) # Always show menu when normal? Or check setting? Default True.
                    self.status_bar.setVisible(self.statusbar_action.isChecked()) # Follow setting
                    if self.fullscreen_action.isChecked(): # Correct action state if needed
                        self.fullscreen_action.setChecked(False)

            else:
                # --- Enter Fullscreen ---
                 if not is_currently_fullscreen:
                    # Store state *before* changing anything
                    self._pre_fullscreen_state = self.windowState()
                    self._pre_fullscreen_menu_visible = self.menuBar().isVisible()
                    self._pre_fullscreen_status_visible = self.status_bar.isVisible()
                    logging.info(f"Entering fullscreen. Stored state: {self._pre_fullscreen_state}, Menu: {self._pre_fullscreen_menu_visible}, Status: {self._pre_fullscreen_status_visible}")

                    # Hide bars before showing fullscreen
                    self.menuBar().setVisible(False)
                    self.status_bar.setVisible(False)

                    # Show fullscreen
                    self.showFullScreen()

                    # Ensure action matches state AFTER state change
                    if not self.fullscreen_action.isChecked():
                        self.fullscreen_action.setChecked(True)
                 else: # Request to enter but was already fullscreen?
                     logging.warning("Attempted to enter fullscreen, but window was already in fullscreen state.")
                     # Correct action state if needed
                     if not self.fullscreen_action.isChecked():
                        self.fullscreen_action.setChecked(True)

            # Optional: Force layout update if needed (usually not required with showNormal/Max/FullScreen)
            # self.layout().activate()
            # QApplication.processEvents()

        except Exception as e:
            logging.exception("Error during toggleFullScreen!")
            # Attempt to recover to a usable state
            try:
                 # self.setWindowState(Qt.WindowState.WindowNoState) # showNormal does this
                 self.showNormal()
                 self.menuBar().setVisible(True)
                 self.status_bar.setVisible(self.statusbar_action.isChecked())
                 if self.fullscreen_action: self.fullscreen_action.setChecked(False)
                 logging.info("Attempted recovery from fullscreen toggle error.")
            except Exception as recovery_e:
                 logging.error(f"Error during fullscreen recovery attempt: {recovery_e}")


    # --- Drag and Drop ---

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        # Accept only local files
        if mime_data.hasUrls() and all(url.isLocalFile() for url in mime_data.urls()):
             # Check if ANY file is potentially text-like
             if any(self.isLikelyTextFile(url.toLocalFile()) for url in mime_data.urls()):
                 event.acceptProposedAction()
                 return
        logging.debug("Drag enter ignored: No local text files detected.")
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        first_text_file = None
        for url in urls:
            if url.isLocalFile():
                filepath = url.toLocalFile()
                if self.isLikelyTextFile(filepath):
                     first_text_file = filepath
                     break # Handle first text file found

        if first_text_file:
             logging.info(f"File dropped: {first_text_file}")
             if self._is_loading_or_saving:
                 self.showBusyMessage()
             elif self.maybeSave():
                 detected_encoding = detect_encoding_with_bom(first_text_file) or DEFAULT_ENCODING
                 self.startFileOperation(first_text_file, encoding=detected_encoding, is_saving=False)
                 event.acceptProposedAction()
             else: # MaybeSave cancelled
                 event.ignore()
        else:
             logging.warning("Drop event ignored: No suitable text file found.")
             event.ignore()

    def isLikelyTextFile(self, filepath):
        """Basic check if a file is likely text-based."""
        known_text_extensions = {
            '.txt', '.py', '.pyw', '.md', '.json', '.xml', '.html', '.htm', '.css', '.js', '.jsx', '.mjs', '.cjs',
            '.csv', '.log', '.ini', '.yaml', '.yml', '.sh', '.bat', '.c', '.h', '.cpp', '.hpp',
            '.java', '.cs', '.go', '.php', '.rb', '.pl', '.ts', '.tsx', '.conf', '.cfg', '.rc', '' # Allow extensionless
            }
        try:
             finfo = QFileInfo(filepath)
             if not finfo.isFile(): return False # Ignore directories, etc.
             if finfo.size() > 50 * 1024 * 1024: # Ignore very large files (> 50MB) for heuristic check? Optional.
                  logging.warning(f"Skipping content check for large file: {filepath}")
                  # Rely solely on extension for large files
                  return finfo.suffix().lower() in known_text_extensions or not finfo.suffix()

             ext = '.' + finfo.suffix().lower() # Prepend dot for set lookup consistency
             if ext in known_text_extensions:
                 return True
             if ext == '.': # Extensionless
                  pass # Proceed to content check

             # Content check (read small chunk)
             with open(filepath, 'rb') as f:
                chunk = f.read(1024)
                if b'\x00' in chunk:
                    # Allow UTF BOMs even if they contain null-like bytes
                    if chunk.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE, codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
                        return True
                    # Check percentage of null bytes? Low percentage might be okay?
                    # Simple check: if null exists (excluding BOM), assume binary.
                    return False # Contains null bytes, likely binary
                # Try decoding as UTF-8 (most common text format)
                try:
                    chunk.decode('utf-8')
                    return True # Decodes, likely text
                except UnicodeDecodeError:
                     # Could try latin-1? Often used for arbitrary byte data.
                    try:
                         chunk.decode('latin-1')
                         return True # Decodes as latin-1, possibly text or text-like binary
                    except UnicodeDecodeError:
                         return False # Cannot decode as common text encodings
        except (IOError, OSError) as e:
             logging.warning(f"Could not check file type for {filepath}: {e}")
             return False
        except Exception as e: # Catch unexpected errors during check
             logging.error(f"Unexpected error checking file type for {filepath}: {e}")
             return False


    # --- Context Menu ---

    def contextMenuEvent(self, event):
        menu = self.text_edit.createStandardContextMenu(event.pos()) # Get standard actions

        # Add custom actions
        menu.addSeparator()
        self.undo_action.setEnabled(self.text_edit.document().isUndoAvailable()) # Sync enable state
        menu.addAction(self.undo_action)
        self.redo_action.setEnabled(self.text_edit.document().isRedoAvailable())
        menu.addAction(self.redo_action)
        menu.addSeparator()
        self.cut_action.setEnabled(self.text_edit.textCursor().hasSelection())
        menu.addAction(self.cut_action)
        self.copy_action.setEnabled(self.text_edit.textCursor().hasSelection())
        menu.addAction(self.copy_action)
        self.paste_action.setEnabled(self.text_edit.canPaste())
        menu.addAction(self.paste_action)
        self.delete_action.setEnabled(self.text_edit.textCursor().hasSelection())
        menu.addAction(self.delete_action)
        menu.addSeparator()
        menu.addAction(self.text_edit.selectAll) # Add select all

        # Could add more: Go To Def, etc. if implementing LSP later

        menu.exec(event.globalPos())

    def showDocumentStatsDialog(self):
        # Get stats directly (no throttling needed for manual request)
        lines, words, chars = self._calculateDocumentStats()
        QMessageBox.information(self, "Document Statistics",
                                f"Lines: {lines}\n"
                                f"Words: {words:,}\n" # Add comma separator
                                f"Characters: {chars:,}")

    # --- Document Stats Update (Throttled) ---

    def _performDocumentStatsUpdate(self):
        """Calculates stats and updates the label."""
        if self._is_loading_or_saving: return # Avoid calculation during IO
        lines, words, chars = self._calculateDocumentStats()
        self._updateDocumentStatsDisplay(lines, words, chars)

    def _calculateDocumentStats(self) -> tuple[int, int, int]:
        """Performs the actual calculation."""
        # This can still be slow for huge files if called too often.
        # QPlainTextEdit caches blocks, so blockCount is fast.
        # toPlainText() is the slow part.
        lines = self.text_edit.blockCount()
        text = self.text_edit.toPlainText() # The expensive call
        chars = len(text)
        # Basic word count - split by whitespace
        words = len(text.split()) if text else 0
        return lines, words, chars

    def _updateDocumentStatsDisplay(self, lines, words, chars):
        """Updates the status bar label with pre-calculated stats."""
        self.doc_stats_label.setText(f"Words: {words:,} Chars: {chars:,} Lines: {lines}")


    # --- Visual Refinements ---

    def toggleLineNumbers(self, checked, save_settings=True):
        """Shows or hides the line number area."""
        self.text_edit.showLineNumbers(checked)
        if save_settings: self.saveSettings()

    def toggleStatusBar(self, checked, save_settings=True):
        """Shows or hides the status bar."""
        self.status_bar.setVisible(checked)
        if save_settings: self.saveSettings()

    def chooseFont(self):
        # Get current font from our internal reference
        font, ok = QFontDialog.getFont(self.font, self, "Select Font")
        if ok:
            # Only update if font actually changed
            if font != self.font:
                 self.font = font # Update internal reference
                 self.text_edit.setFont(self.font) # Apply to editor + line nums
                 self.saveSettings()

    # --- Event Handlers & Updates ---

    def closeEvent(self, event):
        """Handles the window close event."""
        # --- First, handle potential file operations ---
        if self._is_loading_or_saving:
             reply = QMessageBox.question(self, "Operation in Progress",
                                         "A file operation is currently in progress.\n"
                                         "Exiting now might lead to data loss.\n\n"
                                         "Do you want to stop the operation and exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.Yes:
                 self.cancelFileOperation()
                 QApplication.processEvents() # Allow events to process, including cancel signals
                 # Give a short time for the thread/worker to actually stop if needed
                 time.sleep(0.1)
                 # Let maybeSave handle remaining logic if operation is stopped
             else:
                 event.ignore() # Don't close
                 return

        # --- Second, ensure not fullscreen BEFORE maybeSave/saveSettings ---
        is_fullscreen_on_close = self.isFullScreen()
        if is_fullscreen_on_close:
            try:
                 logging.info("Exiting fullscreen automatically before closing.")
                 # --- FIX: Simplify state restoration (same as in toggleFullScreen) ---
                 # Restore bars first
                 if hasattr(self, '_pre_fullscreen_menu_visible'): # Check if attributes were set
                    self.menuBar().setVisible(self._pre_fullscreen_menu_visible)
                 if hasattr(self, '_pre_fullscreen_status_visible'):
                    self.status_bar.setVisible(self._pre_fullscreen_status_visible)

                 # Then use showNormal/showMaximized based on stored state
                 if hasattr(self, '_pre_fullscreen_state') and self._pre_fullscreen_state & Qt.WindowState.WindowMaximized:
                    self.showMaximized()
                 else:
                    self.showNormal()
                 # --- End Fix ---
                 QApplication.processEvents() # Allow state change processing
            except Exception as e:
                 logging.error(f"Error auto-exiting fullscreen on close: {e}. Attempting forced normal.")
                 try:
                     self.showNormal() # Fallback to showNormal
                     # Ensure bars are visible in fallback case
                     self.menuBar().setVisible(True)
                     self.status_bar.setVisible(self.statusbar_action.isChecked() if hasattr(self, 'statusbar_action') else True)
                     QApplication.processEvents()
                 except Exception as fallback_e:
                     logging.error(f"Error during forced normal show on close: {fallback_e}") # Best effort

        # --- Third, proceed with save checks and settings save ---
        if self.maybeSave():
             # Ensure timers are stopped before saving settings
             try: self.backup_timer.stop()
             except AttributeError: pass # Timer might not exist if init failed
             except Exception as e: logging.warning(f"Error stopping backup timer: {e}")
             try: self.autosave_timer.stop()
             except AttributeError: pass
             except Exception as e: logging.warning(f"Error stopping autosave timer: {e}")

             self.saveSettings() # Saves geometry/state AFTER potential fullscreen exit
             self.cleanupAllBackups() # Cleanup backups on clean exit
             event.accept()
             logging.info("Application closing cleanly.")
        else:
             event.ignore()
             logging.info("Application close cancelled by user.")
             # If close was cancelled, don't automatically re-enter fullscreen.
             # User might have wanted out of fullscreen anyway.
             
    def updateTitle(self, modified=None):
        if modified is None:
            modified = self.text_edit.document().isModified()
        title_prefix = "*" if modified else ""
        display_name = self.getDisplayName()
        title = f"{title_prefix}{display_name} - {APP_NAME}"
        self.setWindowTitle(title)
        # Update save action based ONLY on modified state now
        self.save_action.setEnabled(modified and not self.text_edit.isReadOnly())


    def getDisplayName(self):
        return os.path.basename(self.current_file) if self.current_file else "Untitled"


    def updateCursorPosition(self):
        cursor = self.text_edit.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.positionInBlock() # Char column, more consistent than visual
        self.cursor_pos_label.setText(f"Ln {line}, Col {column + 1}")


    def updateEncodingStatus(self):
        enc_display = self.current_encoding.upper()
        self.encoding_label.setText(f"Encoding: {enc_display}")
        # Update checked state in menu
        current_codec_name = self.current_encoding.lower()
        action_found = False
        for action in self.encoding_group.actions():
             action_codec = action.data() # Stored codec name
             if action_codec == current_codec_name:
                  if not action.isChecked(): action.setChecked(True)
                  action_found = True
                  break
        # If current encoding not in menu, uncheck all? Should not happen if changeEncoding sets valid one.
        if not action_found:
            checked_action = self.encoding_group.checkedAction()
            if checked_action: checked_action.setChecked(False)


    def updateStatus(self):
        """Updates non-throttled status elements and triggers throttled ones."""
        self.updateCursorPosition()
        self.updateEncodingStatus()
        # Trigger stats update (will happen after short delay if typing stops)
        self._stats_update_timer.start()
        # Update action states relevant to text changes etc.
        self.updateActionStates()


    def onTextChanged(self):
        """Called when text changes. Minimal updates + triggers throttled updates."""
        # updateTitle is handled by document's modificationChanged signal now
        self.updateActionStates()
        # Restart the timer for stats update
        self._stats_update_timer.start()
        # Backup timer runs independently based on modified flag


    def toggleWordWrap(self, checked=None, save_settings=True):
        if checked is None: checked = self.word_wrap_action.isChecked()
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        if self.text_edit.lineWrapMode() != mode:
            self.text_edit.setLineWrapMode(mode)
            if save_settings: self.saveSettings()


    def showBusyMessage(self):
         QMessageBox.information(self, "Busy", "Please wait for the current file operation to complete.")


    def showAboutDialog(self):
         try: from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
         except (ImportError, AttributeError): PYQT_VERSION_STR, QT_VERSION_STR = "?", "?"

         QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME}</b><br><br>"
                          "A simple enhanced text editor.<br><br>"
                          f"Python: {platform.python_version()}<br>"
                          f"PyQt: {PYQT_VERSION_STR}<br>"
                          f"Qt: {QT_VERSION_STR}<br>"
                          f"Platform: {platform.system()} {platform.release()}<br><br>"
                          f"(c) 2024 Your Name/Org") # <<< UPDATE COPYRIGHT >>>

# --- Main Execution ---
from pathlib import Path # Used in populateRecentFiles

def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    # High DPI handled automatically in Qt6

    try:
         notepad = Notepad()
         notepad.show()

         # Process command line arguments
         if len(sys.argv) > 1:
             filepath = sys.argv[1]
             if os.path.isfile(filepath):
                 logging.info(f"Opening file from command line: {filepath}")
                 # Delay load slightly
                 detected_encoding = detect_encoding_with_bom(filepath) or DEFAULT_ENCODING
                 QTimer.singleShot(100, lambda f=filepath, enc=detected_encoding: notepad.startFileOperation(f, encoding=enc, is_saving=False))
             else:
                 logging.warning(f"Command line argument is not a valid file: {filepath}")
                 QMessageBox.warning(None, "File Not Found", f"Could not open command line file:\n{filepath}")

         sys.exit(app.exec())

    except SystemExit:
         logging.info("Application exited normally.")
    except Exception as e:
         logging.exception("Unhandled exception in main application thread!")
         QMessageBox.critical(None, "Critical Error", f"A critical error occurred:\n{e}\n\nSee logs for details.")
         sys.exit(1) # Indicate error exit


if __name__ == '__main__':
    main()
