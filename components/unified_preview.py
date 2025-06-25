"""
Unified Preview System for Notepad--
Save this as unified_preview.py in your project directory
"""

import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

# Preview type registry
PREVIEW_TYPES = {
    '.md': ('Markdown', 'markdown'),
    '.markdown': ('Markdown', 'markdown'),
    '.xml': ('XML', 'xml'),
    '.html': ('HTML', 'html'),
    '.htm': ('HTML', 'html'),
}

class UnifiedPreviewManager:
    """Manages all preview types and switching between them"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_preview_type = None
        self.preview_widgets = {}
        self.preview_visible = False
        
        # Store original text edit widget
        self.original_text_edit = main_window.text_edit
        
        # Create wrapper widget that will hold either standalone editor or preview split
        self.wrapper_widget = QWidget()
        self.wrapper_layout = QVBoxLayout(self.wrapper_widget)
        self.wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.wrapper_layout.addWidget(self.original_text_edit)
        
        # Set wrapper as central widget
        main_window.setCentralWidget(self.wrapper_widget)
        
        # Create preview action
        self.create_preview_action()
    
    def create_preview_action(self):
        """Create the preview menu action"""
        view_menu = None
        for action in self.main_window.menuBar().actions():
            if action.text() == '&View':
                view_menu = action.menu()
                break
        
        if view_menu:
            view_menu.addSeparator()
            
            # Toggle preview action
            self.preview_action = self.main_window.add_menu_action(
                view_menu, 
                '&Preview', 
                self.toggle_preview,
                'Ctrl+Shift+P'
            )
            self.preview_action.setCheckable(True)
            self.main_window.preview_action = self.preview_action
            
            # Live preview action
            self.live_preview_action = self.main_window.add_menu_action(
                view_menu,
                '&Live Preview',
                self.toggle_live_preview,
                checkable=True,
                checked=True
            )
            self.main_window.live_preview_action = self.live_preview_action
            
            # Refresh preview action
            self.main_window.add_menu_action(
                view_menu,
                '&Refresh Preview',
                self.refresh_preview,
                'F5'
            )
    
    def get_preview_type(self, file_path):
        """Get preview type for a file"""
        if not file_path:
            return None, None
        
        ext = os.path.splitext(file_path)[1].lower()
        return PREVIEW_TYPES.get(ext, (None, None))
    
    def update_preview_action_text(self):
        """Update the preview action text based on current file"""
        display_name, preview_type = self.get_preview_type(self.main_window.current_file)
        
        if display_name:
            self.preview_action.setText(f'{display_name} &Preview')
            self.preview_action.setEnabled(True)
        else:
            self.preview_action.setText('&Preview')
            self.preview_action.setEnabled(False)
            # Hide preview if no preview available
            if self.preview_visible:
                self.toggle_preview()
    
    def get_or_create_preview_widget(self, preview_type):
        """Get existing or create new preview widget for type"""
        if preview_type not in self.preview_widgets:
            if preview_type == 'markdown':
                # Import and create markdown preview
                import components.modules.markdown_viewer as markdown_viewer
                preview_widget = markdown_viewer.MarkdownPreviewWidget(
                    self.original_text_edit, 
                    self.main_window.colors
                )
            elif preview_type == 'xml':
                # Import and create XML preview
                import components.modules.xml_viewer as xml_viewer
                preview_widget = xml_viewer.XMLPreviewWidget(
                    self.original_text_edit,
                    self.main_window.colors
                )
            elif preview_type == 'html':
                # Import and create the new, separate HTML preview
                import components.modules.html_viewer as html_viewer
                preview_widget = html_viewer.HTMLPreviewWidget(
                    self.original_text_edit,
                    self.main_window.colors
                )
            else:
                return None
            
            self.preview_widgets[preview_type] = preview_widget
        
        return self.preview_widgets[preview_type]
    
    def toggle_preview(self):
        """Toggle preview visibility"""
        display_name, preview_type = self.get_preview_type(self.main_window.current_file)
        
        if not preview_type:
            self.preview_action.setChecked(False)
            return
        
        # Get or create preview widget
        preview_widget = self.get_or_create_preview_widget(preview_type)
        if not preview_widget:
            self.preview_action.setChecked(False)
            return
        
        # Hide current preview if different type
        if self.current_preview_type and self.current_preview_type != preview_type:
            current_widget = self.preview_widgets.get(self.current_preview_type)
            if current_widget and current_widget.preview_visible:
                current_widget.toggle_preview()
        
        # Switch to the correct preview widget
        # Remove all widgets from wrapper layout
        while self.wrapper_layout.count():
            child = self.wrapper_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Add the new preview widget
        self.wrapper_layout.addWidget(preview_widget)
        
        # Toggle preview
        self.preview_visible = preview_widget.toggle_preview()
        self.current_preview_type = preview_type if self.preview_visible else None
        
        # Update action state
        self.preview_action.setChecked(self.preview_visible)
        
        # Update live preview
        if self.live_preview_action.isChecked():
            preview_widget.set_live_preview(self.preview_visible)
    
    def toggle_live_preview(self):
        """Toggle live preview mode"""
        enabled = self.live_preview_action.isChecked()
        
        if self.current_preview_type:
            preview_widget = self.preview_widgets.get(self.current_preview_type)
            if preview_widget:
                preview_widget.set_live_preview(enabled)
                
                # Update preview if enabled and visible
                if enabled and preview_widget.preview_visible:
                    preview_widget.update_preview()
    
    def refresh_preview(self):
        """Manually refresh the preview"""
        if self.current_preview_type:
            preview_widget = self.preview_widgets.get(self.current_preview_type)
            if preview_widget and preview_widget.preview_visible:
                preview_widget._do_update_preview()
    
    def on_file_changed(self):
        """Called when a new file is opened or file type changes"""
        self.update_preview_action_text()
        
        # If preview is visible and file type changed, update preview
        if self.preview_visible:
            display_name, new_preview_type = self.get_preview_type(self.main_window.current_file)
            
            if new_preview_type != self.current_preview_type:
                # Toggle off current preview and toggle on new one
                self.toggle_preview()  # Hide current
                if new_preview_type:  # Show new if available
                    self.toggle_preview()


def integrate_unified_preview(main_window):
    """
    Integration function to add unified preview system to Notepad app
    Call this instead of individual viewer integrations
    """
    # Create preview manager
    main_window.preview_manager = UnifiedPreviewManager(main_window)
    
    # Hook into file operations to update preview action text
    original_new_file = main_window.new_file
    original_on_file_loaded = main_window.on_file_loaded
    original_on_file_saved = main_window.on_file_saved
    
    def new_file_with_preview():
        original_new_file()
        main_window.preview_manager.on_file_changed()
    
    def on_file_loaded_with_preview(content, encoding):
        original_on_file_loaded(content, encoding)
        main_window.preview_manager.on_file_changed()
    
    def on_file_saved_with_preview(file_path, encoding):
        original_on_file_saved(file_path, encoding)
        main_window.preview_manager.on_file_changed()
    
    # Replace methods
    main_window.new_file = new_file_with_preview
    main_window.on_file_loaded = on_file_loaded_with_preview
    main_window.on_file_saved = on_file_saved_with_preview
    
    # Initial update
    main_window.preview_manager.update_preview_action_text()


def validate_xml_unified(main_window):
    """Validate current XML content (works with unified preview)"""
    import xml.etree.ElementTree as ET
    import re
    
    xml_text = main_window.text_edit.toPlainText()
    
    if not xml_text.strip():
        main_window.status_bar.showMessage("No XML content to validate", 3000)
        return
    
    try:
        ET.fromstring(xml_text)
        main_window.status_bar.showMessage("✓ Valid XML", 3000)
    except ET.ParseError as e:
        line_match = re.search(r'line (\d+)', str(e))
        if line_match:
            main_window.status_bar.showMessage(f"✗ XML Error on line {line_match.group(1)}: {str(e)}", 5000)
        else:
            main_window.status_bar.showMessage(f"✗ XML Error: {str(e)}", 5000)


def add_xml_validation_menu(main_window):
    """Add XML validation menu item"""
    view_menu = None
    for action in main_window.menuBar().actions():
        if action.text() == '&View':
            view_menu = action.menu()
            break
    
    if view_menu:
        # Add at the end of view menu
        view_menu.addSeparator()
        
        validate_action = main_window.add_menu_action(
            view_menu,
            '&Validate XML',
            lambda: validate_xml_unified(main_window),
            'Ctrl+Shift+V'
        )
        
        # Store reference
        main_window.validate_xml_action = validate_action