"""
HTML Viewer module for Notepad--
Provides live HTML preview functionality.
"""

from PyQt6.QtCore import QTimer
import html
from components.base_preview_viewer import BasePreviewViewer, BasePreviewWidget

class HTMLViewer(BasePreviewViewer):
    """
    A QTextBrowser subclass that renders HTML content with a dark theme style.
    """
    def __init__(self, colors):
        super().__init__(colors)

    def setup_custom_style(self):
        """
        Applies HTML-specific styling for the preview.
        """
        style = f"""
            body {{
                margin: 0;
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
        """
        self.document().setDefaultStyleSheet(style)

    def update_content(self, html_text: str):
        """
        Updates the viewer with new HTML content.
        """
        if not html_text.strip():
            self.show_empty_message("HTML")
            return

        try:
            self.preserve_scroll_position(lambda: self.setHtml(html_text))
        except Exception as e:
            self.show_error(html.escape(str(e)), "HTML Rendering Error")

class HTMLPreviewWidget(BasePreviewWidget):
    """
    A widget that combines the text editor and the HTML viewer in a splitter.
    """
    def __init__(self, text_edit, colors):
        super().__init__(text_edit, colors, HTMLViewer)