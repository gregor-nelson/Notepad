"""
XML Viewer module for Notepad--
Provides comprehensive XML preview functionality with tree view and formatted display
"""

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout,
    QTabWidget, QLabel, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import html
import re
from typing import Optional, Dict, List, Tuple
from components.base_preview_viewer import BasePreviewViewer, BasePreviewWidget

class XMLTreeWidget(QTreeWidget):
    """Tree view widget for XML structure visualization"""
    
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.setup_style()
        
        # Configure tree
        self.setHeaderLabels(['Element', 'Attributes', 'Text Content'])
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(False)
        
        # Configure header
        header = self.header()
        header.setStretchLastSection(True)
        header.setDefaultSectionSize(200)
        header.resizeSection(0, 200)  # Element column
        header.resizeSection(1, 250)  # Attributes column
        
    def setup_style(self):
        """Apply VS Code-inspired styling to the tree view"""
        style = f"""
            QTreeWidget {{
                background-color: {self.colors["black"]};
                color: {self.colors["white"]};
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                outline: none;
                alternate-background-color: {self.colors["gray1"]};
                gridline-color: {self.colors["gray3"]};
                show-decoration-selected: 1;
            }}
            
            QTreeWidget::item {{
                padding: 4px 6px;
                border: none;
                height: 20px;
                color: {self.colors["white"]};
            }}
            
            QTreeWidget::item:alternate {{
                background-color: {self.colors["gray1"]};
                color: {self.colors["white"]};
            }}
            
            QTreeWidget::item:hover {{
                background-color: {self.colors["hover"]};
                color: {self.colors["white"]};
            }}
            
            QTreeWidget::item:selected {{
                background-color: {self.colors["selection"]};
                color: {self.colors["white"]};
            }}
            
            QTreeWidget::item:selected:hover {{
                background-color: {self.colors["selection"]};
                color: {self.colors["white"]};
            }}
            
            QTreeWidget::branch:has-siblings:!adjoins-item {{
                border-image: none;
                border: none;
            }}
            
            QTreeWidget::branch:has-siblings:adjoins-item {{
                border-image: none;
                border: none;
            }}
            
            QTreeWidget::branch:!has-children:!has-siblings:adjoins-item {{
                border-image: none;
                border: none;
            }}
            
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {{
                image: none;
                border-image: none;
            }}
            
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {{
                image: none;
                border-image: none;
            }}
            
            QHeaderView::section {{
                background-color: {self.colors["gray2"]};
                color: {self.colors["white"]};
                padding: 8px 6px;
                border: none;
                border-right: 1px solid {self.colors["gray3"]};
                border-bottom: 1px solid {self.colors["gray3"]};
                font-weight: bold;
                font-size: 12px;
            }}
            
            QHeaderView::section:hover {{
                background-color: {self.colors["gray3"]};
            }}
            
            QScrollBar:vertical {{
                background: {self.colors["black"]};
                width: 14px;
                border: none;
                border-radius: 2px;
            }}
            
            QScrollBar::handle:vertical {{
                background: {self.colors["gray3"]};
                min-height: 30px;
                border: none;
                border-radius: 2px;
                margin: 2px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: {self.colors["gray4"]};
            }}
            
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                background: none;
                border: none;
                height: 0px;
            }}
            
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """
        self.setStyleSheet(style)
    
    def populate_from_element(self, element: ET.Element, parent_item: Optional[QTreeWidgetItem] = None):
        """Recursively populate tree from XML element"""
        # Create tree item
        if parent_item is None:
            item = QTreeWidgetItem(self)
        else:
            item = QTreeWidgetItem(parent_item)
        
        # Set element name with color
        item.setText(0, element.tag)
        item.setForeground(0, QBrush(QColor(self.colors["blue"])))
        
        # Set attributes
        if element.attrib:
            if len(element.attrib) == 1:
                # Single attribute - show inline
                key, value = next(iter(element.attrib.items()))
                item.setText(1, f'{key}="{value}"')
            elif len(element.attrib) <= 3:
                # Few attributes - show on one line
                attrs = []
                for key, value in element.attrib.items():
                    attrs.append(f'{key}="{value}"')
                item.setText(1, ' '.join(attrs))
            else:
                # Many attributes - show count
                item.setText(1, f'{len(element.attrib)} attributes')
            item.setForeground(1, QBrush(QColor(self.colors["green"])))
        
        # Set text content
        if element.text and element.text.strip():
            text_preview = element.text.strip()
            # Replace newlines and tabs with spaces for display
            text_preview = ' '.join(text_preview.split())
            if len(text_preview) > 60:
                text_preview = text_preview[:60] + "..."
            item.setText(2, text_preview)
            item.setForeground(2, QBrush(QColor(self.colors["white"])))
        elif len(list(element)) == 0:
            # Empty element
            item.setText(2, "〈empty〉")
            item.setForeground(2, QBrush(QColor(self.colors["gray4"])))
        
        # Add icon based on element type
        if len(list(element)):  # Has children
            item.setExpanded(True)
        
        # Recursively add children
        for child in element:
            self.populate_from_element(child, item)
        
        return item
    
    def clear_tree(self):
        """Clear all items from the tree"""
        self.clear()


class XMLFormattedView(BasePreviewViewer):
    """Formatted XML text view with syntax highlighting"""
    
    def __init__(self, colors):
        super().__init__(colors)
        self.setOpenExternalLinks(False)
    
    def setup_custom_style(self):
        """Apply XML-specific styling"""
        style = f"""
            body {{
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
                padding: 10px;
                margin: 0;
            }}
            
            /* XML syntax highlighting */
            .xml-tag {{
                color: {self.colors["blue"]};
            }}
            
            .xml-attribute {{
                color: {self.colors["green"]};
            }}
            
            .xml-value {{
                color: {self.colors["green"]};  /* One Dark string color */
            }}
            
            .xml-text {{
                color: {self.colors["white"]};
            }}
            
            .xml-comment {{
                color: {self.colors["gray4"]};  /* One Dark comment color */
                font-style: italic;
            }}
            
            .xml-cdata {{
                color: {self.colors["orange"]};  /* One Dark preprocessor color */
                background-color: {self.colors["gray2"]};
                padding: 2px 4px;
                border-radius: 2px;
            }}
            
            .xml-declaration {{
                color: {self.colors["purple"]};  /* One Dark keyword color */
            }}
            
            pre {{
                margin: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
        """
        
        self.document().setDefaultStyleSheet(style)
    
    def update_content(self, xml_text: str):
        """Display XML with syntax highlighting"""
        if not xml_text.strip():
            self.show_empty_message("XML")
            return
            
        try:
            # Parse to validate
            root = ET.fromstring(xml_text)
            
            # Pretty print the XML
            dom = minidom.parseString(xml_text)
            pretty_xml = dom.toprettyxml(indent="  ")
            
            # Remove extra blank lines that minidom adds
            pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
            
            # Apply syntax highlighting
            highlighted = self._highlight_xml(pretty_xml)
            
            # Wrap in HTML
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
            </head>
            <body>
                <pre>{highlighted}</pre>
            </body>
            </html>
            """
            
            self.preserve_scroll_position(lambda: self.setHtml(html_content))
            
        except ET.ParseError as e:
            self.show_error(f"XML Parse Error: {str(e)}", "XML Parse Error")
        except Exception as e:
            self.show_error(f"Error: {str(e)}", "XML Error")
    
    def _highlight_xml(self, xml_text: str) -> str:
        """Apply syntax highlighting to XML text"""
        # Escape HTML first
        xml_text = html.escape(xml_text)
        
        # XML declaration
        xml_text = re.sub(
            r'(&lt;\?xml.*?\?&gt;)',
            r'<span class="xml-declaration">\1</span>',
            xml_text,
            flags=re.DOTALL
        )
        
        # Comments
        xml_text = re.sub(
            r'(&lt;!--.*?--&gt;)',
            r'<span class="xml-comment">\1</span>',
            xml_text,
            flags=re.DOTALL
        )
        
        # CDATA sections
        xml_text = re.sub(
            r'(&lt;!\[CDATA\[.*?\]\]&gt;)',
            r'<span class="xml-cdata">\1</span>',
            xml_text,
            flags=re.DOTALL
        )
        
        # Tags with attributes
        def highlight_tag(match):
            full_tag = match.group(0)
            tag_start = match.group(1)  # < or </
            tag_name = match.group(2)   # tag name
            attributes = match.group(3)  # attributes
            tag_end = match.group(4)    # > or />
            
            # Highlight attributes
            if attributes:
                attributes = re.sub(
                    r'(\w+)(=)(&quot;[^&]*&quot;|&#39;[^&]*&#39;)',
                    r'<span class="xml-attribute">\1</span>\2<span class="xml-value">\3</span>',
                    attributes
                )
            
            return f'<span class="xml-tag">{tag_start}{tag_name}</span>{attributes}<span class="xml-tag">{tag_end}</span>'
        
        # Match opening and closing tags
        xml_text = re.sub(
            r'(&lt;/?)([\w:.-]+)([^&gt;]*?)(/&gt;|&gt;)',
            highlight_tag,
            xml_text
        )
        
        return xml_text


class XMLViewer(QWidget):
    """Combined XML viewer with tree and formatted views"""
    
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.current_xml = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tab widget for different views
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        
        # Tree view tab
        self.tree_view = XMLTreeWidget(self.colors)
        self.tab_widget.addTab(self.tree_view, "Tree View")
        
        # Formatted view tab
        self.formatted_view = XMLFormattedView(self.colors)
        self.tab_widget.addTab(self.formatted_view, "Formatted")
        
        # Stats bar
        self.stats_widget = QWidget()
        stats_layout = QHBoxLayout(self.stats_widget)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        
        self.stats_label = QLabel("No XML loaded")
        self.stats_label.setStyleSheet(f"color: {self.colors['gray4']}; font-size: 12px;")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {self.colors['red']}; font-size: 12px;")
        stats_layout.addWidget(self.error_label)
        
        # Add widgets to layout
        layout.addWidget(self.tab_widget)
        layout.addWidget(self.stats_widget)
        
        # Style the tab widget
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {self.colors["gray3"]};
                border-top: none;
                background-color: {self.colors["black"]};
            }}
            
            QTabBar::tab {{
                background-color: {self.colors["gray2"]};
                color: {self.colors["gray4"]};
                padding: 8px 16px;
                margin-right: 1px;
                border: 1px solid {self.colors["gray3"]};
                border-bottom: none;
                border-top-left-radius: 2px;
                border-top-right-radius: 2px;
                min-width: 80px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {self.colors["black"]};
                color: {self.colors["white"]};
                border-bottom: 1px solid {self.colors["black"]};
            }}
            
            QTabBar::tab:hover:!selected {{
                background-color: {self.colors["hover"]};
                color: {self.colors["white"]};
            }}
            
            QTabBar::tab:first {{
                margin-left: 0px;
            }}
        """)
    
    def update_xml(self, xml_text: str):
        """Update all views with new XML content"""
        self.current_xml = xml_text
        self.error_label.clear()
        
        if not xml_text.strip():
            self.tree_view.clear_tree()
            self.formatted_view.setHtml(f"<p style='color: {self.colors['gray4']};'>Start typing XML to see the preview...</p>")
            self.stats_label.setText("No XML loaded")
            return
        
        try:
            # Parse XML
            root = ET.fromstring(xml_text)
            
            # Update tree view
            self.tree_view.clear_tree()
            self.tree_view.populate_from_element(root)
            
            # Update formatted view
            self.formatted_view.update_content(xml_text)
            
            # Update stats
            self._update_stats(root)
            
        except ET.ParseError as e:
            # Show error in formatted view
            self.formatted_view.show_error(str(e), "XML Parse Error")
            self.tree_view.clear_tree()
            
            # Show brief error in status
            line_match = re.search(r'line (\d+)', str(e))
            if line_match:
                self.error_label.setText(f"Error on line {line_match.group(1)}")
            else:
                self.error_label.setText("Invalid XML")
            
            self.stats_label.setText("Parse error")
        
        except Exception as e:
            self.formatted_view.show_error(f"Unexpected error: {str(e)}", "XML Error")
            self.tree_view.clear_tree()
            self.error_label.setText("Error")
            self.stats_label.setText("Error")
    
    def _update_stats(self, root: ET.Element):
        """Update statistics about the XML"""
        # Count elements
        element_count = len(list(root.iter()))
        
        # Count attributes
        attr_count = sum(len(elem.attrib) for elem in root.iter())
        
        # Get root info
        root_name = root.tag
        
        stats_text = f"{element_count} elements, {attr_count} attributes | Root: <{root_name}>"
        self.stats_label.setText(stats_text)


class XMLPreviewWidget(BasePreviewWidget):
    """Combined widget with splitter for editor and preview"""
    
    def __init__(self, text_edit, colors):
        super().__init__(text_edit, colors, XMLViewer)
    
    def _do_update_preview(self):
        """Actually perform the preview update - override for XML's custom method"""
        self.viewer.update_xml(self.text_edit.toPlainText())


def integrate_xml_viewer(main_window):
    """
    Integration function to add XML viewer to existing Notepad app
    Call this from the main app after initialization
    """
    # Check if we already have a preview widget (from markdown viewer)
    if hasattr(main_window, 'preview_widget'):
        # We need to handle multiple preview types
        # For now, we'll add a check for file type
        original_toggle = main_window.preview_widget.toggle_preview
        
        def smart_toggle_preview():
            # Check if current file is XML
            if main_window.current_file and main_window.current_file.lower().endswith('.xml'):
                # Switch to XML viewer if needed
                if not hasattr(main_window, 'xml_preview_widget'):
                    setup_xml_viewer(main_window)
                
                # Hide markdown preview if visible
                if hasattr(main_window, 'preview_widget') and main_window.preview_widget.preview_visible:
                    main_window.preview_widget.toggle_preview()
                
                # Show XML preview
                return main_window.xml_preview_widget.toggle_preview()
            else:
                # Use markdown preview for other files
                if hasattr(main_window, 'xml_preview_widget') and main_window.xml_preview_widget.preview_visible:
                    main_window.xml_preview_widget.toggle_preview()
                return original_toggle()
        
        # Override the preview action
        main_window.preview_action.triggered.disconnect()
        main_window.preview_action.triggered.connect(lambda: toggle_preview_callback_xml(main_window))
    else:
        # No markdown viewer, set up XML viewer directly
        setup_xml_viewer(main_window)
        add_xml_menu_items(main_window)


def setup_xml_viewer(main_window):
    """Set up the XML viewer widget"""
    # Get current central widget
    current_central = main_window.centralWidget()
    
    # Create XML preview widget
    xml_preview_widget = XMLPreviewWidget(main_window.text_edit, main_window.colors)
    main_window.xml_preview_widget = xml_preview_widget
    
    # Don't replace central widget yet - we'll switch dynamically


def add_xml_menu_items(main_window):
    """Add XML-specific menu items"""
    view_menu = None
    for action in main_window.menuBar().actions():
        if action.text() == '&View':
            view_menu = action.menu()
            break
    
    if view_menu:
        # Find where to insert (after markdown preview items if they exist)
        insert_pos = None
        for i, action in enumerate(view_menu.actions()):
            if action.text() in ['&Refresh Preview', '&Live Preview']:
                insert_pos = i + 1
                break
        
        if insert_pos is None:
            view_menu.addSeparator()
        
        # XML Validation action
        validate_action = main_window.add_menu_action(
            view_menu,
            '&Validate XML',
            lambda: validate_xml_callback(main_window),
            'Ctrl+Shift+V'
        )
        
        if insert_pos:
            view_menu.insertAction(view_menu.actions()[insert_pos], validate_action)


def toggle_preview_callback_xml(main_window):
    """Smart preview toggle that switches between markdown and XML based on file type"""
    is_xml = main_window.current_file and main_window.current_file.lower().endswith('.xml')
    
    if is_xml:
        # Ensure XML viewer exists
        if not hasattr(main_window, 'xml_preview_widget'):
            setup_xml_viewer(main_window)
        
        # Switch central widget to XML preview if needed
        if main_window.centralWidget() != main_window.xml_preview_widget:
            # Hide other previews
            if hasattr(main_window, 'preview_widget') and main_window.preview_widget.preview_visible:
                main_window.preview_widget.toggle_preview()
            
            # Set XML preview as central
            main_window.setCentralWidget(main_window.xml_preview_widget)
        
        # Toggle XML preview
        is_visible = main_window.xml_preview_widget.toggle_preview()
        main_window.preview_action.setChecked(is_visible)
        
        # Update live preview connection
        if hasattr(main_window, 'live_preview_action') and main_window.live_preview_action.isChecked():
            main_window.xml_preview_widget.set_live_preview(is_visible)
    else:
        # Use markdown preview for non-XML files
        if hasattr(main_window, 'preview_widget'):
            # Switch back to markdown preview widget
            if main_window.centralWidget() != main_window.preview_widget:
                if hasattr(main_window, 'xml_preview_widget') and main_window.xml_preview_widget.preview_visible:
                    main_window.xml_preview_widget.toggle_preview()
                main_window.setCentralWidget(main_window.preview_widget)
            
            is_visible = main_window.preview_widget.toggle_preview()
            main_window.preview_action.setChecked(is_visible)
            
            if hasattr(main_window, 'live_preview_action') and main_window.live_preview_action.isChecked():
                main_window.preview_widget.set_live_preview(is_visible)


def validate_xml_callback(main_window):
    """Validate current XML content"""
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