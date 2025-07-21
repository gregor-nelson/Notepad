"""
HTML Viewer module for Notepad--
Provides live HTML preview functionality using QWebEngineView.
"""

from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
import html
import tempfile
import os
from components.base_preview_viewer import BasePreviewWidget

class HTMLViewer(QWebEngineView):
    """
    A QWebEngineView that renders HTML content with full CSS and JavaScript support.
    """
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.temp_file = None
        self.setup_styling()

    def setup_styling(self):
        """
        Apply styling to the web engine view.
        """
        # Web engine view styling
        self.setStyleSheet(f"""
            QWebEngineView {{
                background-color: {self.colors["black"]};
                border: none;
            }}
        """)

    def update_content(self, html_text: str):
        """
        Updates the viewer with new HTML content by creating a temporary file.
        """
        if not html_text.strip():
            self.show_empty_message("HTML")
            return

        try:
            # Clean up previous temp file
            if self.temp_file and os.path.exists(self.temp_file):
                os.unlink(self.temp_file)
            
            # Create new temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                # Add dark theme CSS if the HTML doesn't contain a complete document
                if not html_text.strip().lower().startswith('<!doctype') and '<html' not in html_text.lower():
                    enhanced_html = self._wrap_with_dark_theme(html_text)
                    f.write(enhanced_html)
                else:
                    f.write(html_text)
                self.temp_file = f.name
            
            # Load the temporary file
            self.load(QUrl.fromLocalFile(self.temp_file))
            
        except Exception as e:
            self.show_error(html.escape(str(e)), "HTML Rendering Error")
    
    def _wrap_with_dark_theme(self, html_content: str) -> str:
        """
        Wraps HTML content with a complete document structure and dark theme.
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: {self.colors["white"]};
                    background-color: {self.colors["black"]};
                    margin: 20px;
                    padding: 0;
                }}
                a {{
                    color: {self.colors["blue"]};
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                pre, code {{
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    background-color: {self.colors["gray2"]};
                    color: {self.colors["green"]};
                    padding: 2px 4px;
                    border-radius: 2px;
                    font-size: 0.9em;
                }}
                pre {{
                    padding: 16px;
                    overflow-x: auto;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: {self.colors["white"]};
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}
                th, td {{
                    border: 1px solid {self.colors["gray3"]};
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: {self.colors["gray2"]};
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
    
    def show_empty_message(self, file_type: str):
        """
        Show standardized empty state message.
        """
        message_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                    color: #858585;
                    background-color: {self.colors["black"]};
                    margin: 20px;
                    text-align: center;
                    padding-top: 50px;
                }}
            </style>
        </head>
        <body>
            <p>Start typing {file_type} to see the preview...</p>
        </body>
        </html>
        """
        self.setHtml(message_html)
    
    def show_error(self, error_message: str, error_type: str = "Error"):
        """
        Show standardized error message.
        """
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                    background-color: {self.colors["black"]};
                    margin: 20px;
                    color: {self.colors["white"]};
                }}
                .error {{
                    color: {self.colors["red"]};
                    background-color: rgba(244, 135, 113, 0.1);
                    padding: 10px;
                    border-radius: 2px;
                }}
            </style>
        </head>
        <body>
            <div class="error">
                <h3>⚠ {error_type}</h3>
                <p>{error_message}</p>
            </div>
        </body>
        </html>
        """
        self.setHtml(error_html)
    
    def __del__(self):
        """
        Clean up temporary file when the viewer is destroyed.
        """
        if hasattr(self, 'temp_file') and self.temp_file and os.path.exists(self.temp_file):
            try:
                os.unlink(self.temp_file)
            except:
                pass

class HTMLPreviewWidget(QWidget):
    """
    A widget that combines the text editor and the HTML viewer in a splitter.
    """
    def __init__(self, text_edit, colors):
        super().__init__()
        self.text_edit = text_edit
        self.colors = colors
        
        # Common settings
        self.update_delay = 300  # milliseconds
        self.preview_visible = False
        self.live_preview_enabled = True
        
        # Debounce timer for live preview
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._do_update_preview)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI layout with splitter"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Add text editor to splitter
        self.splitter.addWidget(self.text_edit)
        
        # Create and add viewer
        self.viewer = HTMLViewer(self.colors)
        self.splitter.addWidget(self.viewer)
        
        # Set initial sizes (50/50 split)
        self.splitter.setSizes([400, 400])
        
        # Apply splitter styling
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {self.colors["gray3"]};
                width: 1px;
            }}
            QSplitter::handle:hover {{
                background-color: {self.colors["blue"]};
            }}
        """)
        
        layout.addWidget(self.splitter)
        
        # Initially hide the preview
        self.viewer.hide()
    
    def toggle_preview(self):
        """Toggle the preview visibility"""
        self.preview_visible = not self.preview_visible
        self.viewer.setVisible(self.preview_visible)
        
        if self.preview_visible:
            # Update preview with current text
            self.update_preview()
            # Set reasonable split sizes
            total_width = self.splitter.width()
            self.splitter.setSizes([total_width // 2, total_width // 2])
        
        return self.preview_visible
    
    def update_preview(self):
        """Update the preview with debouncing for performance"""
        if self.preview_visible:
            if self.live_preview_enabled:
                # Cancel any pending update and start timer
                self.update_timer.stop()
                self.update_timer.start(self.update_delay)
            else:
                # Immediate update when not in live mode
                self._do_update_preview()
    
    def _do_update_preview(self):
        """Actually perform the preview update"""
        self.viewer.update_content(self.text_edit.toPlainText())
    
    def set_live_preview(self, enabled):
        """Enable/disable live preview updates"""
        self.live_preview_enabled = enabled
        
        if enabled and self.preview_visible:
            try:
                self.text_edit.textChanged.disconnect(self.update_preview)
            except TypeError:
                pass  # Not connected
            self.text_edit.textChanged.connect(self.update_preview)
        else:
            try:
                self.text_edit.textChanged.disconnect(self.update_preview)
            except TypeError:
                pass  # Not connected
            # Cancel any pending updates
            self.update_timer.stop()
    
    def set_update_delay(self, delay_ms):
        """Set the debounce delay for live preview updates"""
        self.update_delay = delay_ms