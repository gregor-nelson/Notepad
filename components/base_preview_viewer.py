"""
Base Preview Viewer module for Notepad--
Provides standardized interface and common functionality for all preview viewers
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QTextBrowser
from PyQt6.QtCore import Qt, QTimer


class BasePreviewViewer(QTextBrowser):
    """
    Abstract base class for preview viewers.
    Provides common interface and styling functionality.
    """
    
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.setOpenExternalLinks(True)
        self.setup_base_style()
        self.setup_custom_style()
    
    def setup_base_style(self):
        """Apply common base styling to all viewers"""
        base_style = f"""
            QTextBrowser {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                font-size: 14px;
                line-height: 1.6;
                color: {self.colors["white"]};
                background-color: {self.colors["black"]};
                border: none;
                padding: 20px;
            }}
            
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
        """
        self.setStyleSheet(base_style)
    
    def setup_custom_style(self):
        """Setup viewer-specific CSS styling - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement setup_custom_style()")
    
    def update_content(self, text: str):
        """Update the preview with new content - must be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement update_content()")
    
    def show_empty_message(self, file_type: str):
        """Show standardized empty state message"""
        message = f"<p style='color: #858585;'>Start typing {file_type} to see the preview...</p>"
        self.setHtml(message)
    
    def show_error(self, error_message: str, error_type: str = "Error"):
        """Show standardized error message"""
        error_html = f"""
        <div style="color: {self.colors['red']}; background-color: rgba(244, 135, 113, 0.1); 
                    padding: 10px; border-radius: 2px; font-family: 'Segoe UI', sans-serif;">
            <h3>⚠ {error_type}</h3>
            <p>{error_message}</p>
        </div>
        """
        self.setHtml(error_html)
    
    def preserve_scroll_position(self, update_func):
        """Preserve scroll position during content updates"""
        scrollbar = self.verticalScrollBar()
        scroll_pos = scrollbar.value()
        
        update_func()
        
        # Restore scroll position after a small delay
        QTimer.singleShot(10, lambda: scrollbar.setValue(scroll_pos))


class BasePreviewWidget(QWidget):
    """
    Base class for preview widgets with splitter layout.
    Provides common layout and behavior for all preview types.
    """
    
    def __init__(self, text_edit, colors, viewer_class):
        super().__init__()
        self.text_edit = text_edit
        self.colors = colors
        self.viewer_class = viewer_class
        
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
        """Setup common UI layout with splitter"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Add text editor to splitter
        self.splitter.addWidget(self.text_edit)
        
        # Create and add viewer
        self.viewer = self.viewer_class(self.colors)
        self.splitter.addWidget(self.viewer)
        
        # Set initial sizes (50/50 split)
        self.splitter.setSizes([400, 400])
        
        # Apply common splitter styling
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