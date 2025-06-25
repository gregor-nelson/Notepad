"""
Improved Markdown Viewer module for Notepad--
Provides comprehensive markdown preview functionality with clean, robust parsing
"""

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextDocument
import re
import html
from typing import Dict, List, Tuple
from ..base_preview_viewer import BasePreviewViewer, BasePreviewWidget

class MarkdownParser:
    """Clean and robust markdown to HTML converter"""
    
    def __init__(self):
        self.reset()
        
    def reset(self):
        """Reset parser state"""
        self.footnotes = {}
        self.footnote_refs = []
        self.link_refs = {}
        self.code_blocks = {}
        self.code_counter = 0
        
    def parse(self, text: str) -> str:
        """Convert markdown text to HTML"""
        self.reset()
        
        if not text.strip():
            return "<p>Start typing to see the preview...</p>"
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Processing pipeline
        text = self._extract_reference_definitions(text)
        text = self._protect_code_blocks(text)
        text = self._process_block_elements(text)
        text = self._restore_code_blocks(text)
        
        # Add footnotes if any
        if self.footnotes and self.footnote_refs:
            text += self._generate_footnotes_html()
        
        return text
    
    def _extract_reference_definitions(self, text: str) -> str:
        """Extract link references and footnote definitions"""
        lines = []
        
        for line in text.split('\n'):
            # Link references: [ref]: url "title"
            if match := re.match(r'^\s*\[([^\]]+)\]:\s*(\S+)(?:\s+"([^"]*)")?$', line):
                ref_id = match.group(1).lower()
                self.link_refs[ref_id] = {
                    'url': match.group(2),
                    'title': match.group(3) or ''
                }
            # Footnote definitions: [^ref]: text
            elif match := re.match(r'^\[\^([^\]]+)\]:\s+(.+)$', line):
                self.footnotes[match.group(1)] = match.group(2)
            else:
                lines.append(line)
        
        return '\n'.join(lines)
    
    def _protect_code_blocks(self, text: str) -> str:
        """Extract and protect code blocks"""
        # Fenced code blocks
        def replace_fenced(match):
            lang = match.group(1) or ''
            code = html.escape(match.group(2).rstrip('\n'))
            placeholder = f'§CODE{self.code_counter}§'
            self.code_blocks[placeholder] = f'<pre><code class="language-{lang}">{code}</code></pre>'
            self.code_counter += 1
            return placeholder
        
        text = re.sub(
            r'^```(\w*)\n(.*?)\n```$',
            replace_fenced,
            text,
            flags=re.MULTILINE | re.DOTALL
        )
        
        # Indented code blocks
        lines = text.split('\n')
        result = []
        code_lines = []
        in_code = False
        
        for line in lines:
            # Check if this is already a protected code block
            if line.strip().startswith('§CODE'):
                if in_code and code_lines:
                    # Save accumulated code
                    placeholder = f'§CODE{self.code_counter}§'
                    code = html.escape('\n'.join(code_lines))
                    self.code_blocks[placeholder] = f'<pre><code>{code}</code></pre>'
                    self.code_counter += 1
                    result.append(placeholder)
                    code_lines = []
                    in_code = False
                result.append(line)
            elif line.startswith(('    ', '\t')) and line.strip():
                # Code line
                in_code = True
                code_lines.append(line[4:] if line.startswith('    ') else line[1:])
            else:
                # Not code
                if in_code and code_lines:
                    # Save accumulated code
                    placeholder = f'§CODE{self.code_counter}§'
                    code = html.escape('\n'.join(code_lines))
                    self.code_blocks[placeholder] = f'<pre><code>{code}</code></pre>'
                    self.code_counter += 1
                    result.append(placeholder)
                    code_lines = []
                    in_code = False
                result.append(line)
        
        # Handle trailing code block
        if in_code and code_lines:
            placeholder = f'§CODE{self.code_counter}§'
            code = html.escape('\n'.join(code_lines))
            self.code_blocks[placeholder] = f'<pre><code>{code}</code></pre>'
            self.code_counter += 1
            result.append(placeholder)
        
        return '\n'.join(result)
    
    def _restore_code_blocks(self, text: str) -> str:
        """Restore protected code blocks"""
        for placeholder, code in self.code_blocks.items():
            text = text.replace(placeholder, code)
        return text
    
    def _process_block_elements(self, text: str) -> str:
        """Process all block-level elements"""
        blocks = re.split(r'\n\s*\n', text)
        processed_blocks = []
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            # Skip protected code blocks
            if block.startswith('§CODE'):
                processed_blocks.append(block)
                continue
            
            # Try each block processor
            processed = (
                self._process_header(block) or
                self._process_hr(block) or
                self._process_blockquote(block) or
                self._process_list(block) or
                self._process_table(block) or
                self._process_paragraph(block)
            )
            processed_blocks.append(processed)
        
        return '\n'.join(processed_blocks)
    
    def _process_header(self, block: str) -> str:
        """Process headers"""
        lines = block.split('\n')
        
        # ATX headers
        if match := re.match(r'^(#{1,6})\s+(.+?)(?:\s+#+)?$', lines[0]):
            level = len(match.group(1))
            content = self._process_inline(html.escape(match.group(2).strip()))
            header_id = re.sub(r'[^\w\-]', '-', match.group(2).lower()).strip('-')
            return f'<h{level} id="{header_id}">{content}</h{level}>'
        
        # Setext headers
        if len(lines) >= 2:
            if re.match(r'^=+\s*$', lines[1]):
                content = self._process_inline(html.escape(lines[0]))
                header_id = re.sub(r'[^\w\-]', '-', lines[0].lower()).strip('-')
                return f'<h1 id="{header_id}">{content}</h1>'
            elif re.match(r'^-+\s*$', lines[1]):
                content = self._process_inline(html.escape(lines[0]))
                header_id = re.sub(r'[^\w\-]', '-', lines[0].lower()).strip('-')
                return f'<h2 id="{header_id}">{content}</h2>'
        
        return None
    
    def _process_hr(self, block: str) -> str:
        """Process horizontal rules"""
        if re.match(r'^[ ]{0,3}([-*_])([ ]*\1[ ]*){2,}$', block.strip()):
            return '<hr>'
        return None
    
    def _process_blockquote(self, block: str) -> str:
        """Process blockquotes"""
        lines = block.split('\n')
        if all(line.startswith('>') or not line.strip() for line in lines):
            # Extract quote content
            quote_lines = []
            for line in lines:
                if line.startswith('> '):
                    quote_lines.append(line[2:])
                elif line.startswith('>'):
                    quote_lines.append(line[1:])
                else:
                    quote_lines.append(line)
            
            # Recursively process quote content
            quote_content = '\n'.join(quote_lines)
            processed = self._process_block_elements(quote_content)
            return f'<blockquote>{processed}</blockquote>'
        
        return None
    
    def _process_list(self, block: str) -> str:
        """Process lists with proper nesting support"""
        lines = block.split('\n')
        
        # Check if this is a list
        first_line = lines[0]
        is_ordered = bool(re.match(r'^\s*\d+\.\s+', first_line))
        is_unordered = bool(re.match(r'^\s*[-*+]\s+', first_line))
        
        if not (is_ordered or is_unordered):
            return None
        
        # Parse list items with indentation levels
        items = []
        current_item = []
        base_indent = len(first_line) - len(first_line.lstrip())
        
        for line in lines:
            if is_ordered:
                match = re.match(r'^(\s*)(\d+)\.\s+(.*)$', line)
            else:
                match = re.match(r'^(\s*)[-*+]\s+(.*)$', line)
            
            if match:
                if current_item:
                    items.append((base_indent, '\n'.join(current_item)))
                    current_item = []
                
                indent = len(match.group(1))
                content = match.group(3) if is_ordered else match.group(2)
                
                # Check for task list
                task_match = re.match(r'\[([ xX])\]\s+(.*)$', content)
                if task_match:
                    checked = task_match.group(1).lower() == 'x'
                    content = ('☑' if checked else '☐') + ' ' + task_match.group(2)
                
                current_item = [content]
                base_indent = min(base_indent, indent)
            else:
                # Continuation of current item
                current_item.append(line)
        
        if current_item:
            items.append((base_indent, '\n'.join(current_item)))
        
        # Build HTML
        tag = 'ol' if is_ordered else 'ul'
        html_items = []
        
        for indent, content in items:
            # Process inline elements in content
            processed = self._process_inline(html.escape(content.strip()))
            html_items.append(f'<li>{processed}</li>')
        
        return f'<{tag}>{"".join(html_items)}</{tag}>'
    
    def _process_table(self, block: str) -> str:
        """Process tables"""
        lines = block.split('\n')
        
        # Check for table pattern
        if len(lines) < 2 or '|' not in lines[0] or '|' not in lines[1]:
            return None
        
        # Check separator line
        if not re.match(r'^[\s\-:|]+$', lines[1]):
            return None
        
        # Parse alignment
        sep_cells = [cell.strip() for cell in lines[1].split('|')]
        sep_cells = [c for c in sep_cells if c]  # Remove empty
        
        alignments = []
        for cell in sep_cells:
            if cell.startswith(':') and cell.endswith(':'):
                alignments.append(' style="text-align: center"')
            elif cell.endswith(':'):
                alignments.append(' style="text-align: right"')
            else:
                alignments.append('')
        
        # Build table
        html_parts = ['<table>', '<thead>', '<tr>']
        
        # Header row
        headers = [cell.strip() for cell in lines[0].split('|')]
        headers = [h for h in headers if h]  # Remove empty
        
        for i, header in enumerate(headers):
            align = alignments[i] if i < len(alignments) else ''
            content = self._process_inline(html.escape(header))
            html_parts.append(f'<th{align}>{content}</th>')
        
        html_parts.extend(['</tr>', '</thead>', '<tbody>'])
        
        # Body rows
        for line in lines[2:]:
            if '|' not in line:
                continue
            
            cells = [cell.strip() for cell in line.split('|')]
            cells = [c for c in cells if c is not None]  # Keep empty cells
            
            html_parts.append('<tr>')
            for i, cell in enumerate(cells):
                if i < len(headers):  # Don't exceed header count
                    align = alignments[i] if i < len(alignments) else ''
                    content = self._process_inline(html.escape(cell))
                    html_parts.append(f'<td{align}>{content}</td>')
            html_parts.append('</tr>')
        
        html_parts.extend(['</tbody>', '</table>'])
        return ''.join(html_parts)
    
    def _process_paragraph(self, block: str) -> str:
        """Process paragraph - fallback for any block"""
        content = self._process_inline(html.escape(block))
        return f'<p>{content}</p>'
    
    def _process_inline(self, text: str) -> str:
        """Process inline elements in already-escaped text"""
        # Inline code (must be first to protect from other processing)
        text = re.sub(
            r'`([^`]+)`',
            lambda m: f'<code>{m.group(1)}</code>',
            text
        )
        
        # Images
        text = re.sub(
            r'!\[([^\]]*)\]\(([^\)]+?)(?:\s+&quot;([^&]+)&quot;)?\)',
            lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}" title="{m.group(3) or ""}">',
            text
        )
        
        # Links
        text = re.sub(
            r'\[([^\]]+)\]\(([^\)]+?)(?:\s+&quot;([^&]+)&quot;)?\)',
            lambda m: f'<a href="{m.group(2)}" title="{m.group(3) or ""}">{m.group(1)}</a>',
            text
        )
        
        # Reference links
        def process_ref_link(match):
            link_text = match.group(1)
            ref_id = (match.group(2) or link_text).lower()
            if ref_id in self.link_refs:
                ref = self.link_refs[ref_id]
                title_attr = f' title="{ref["title"]}"' if ref['title'] else ''
                return f'<a href="{ref["url"]}"{title_attr}>{link_text}</a>'
            return match.group(0)
        
        text = re.sub(r'\[([^\]]+)\]\[([^\]]*)\]', process_ref_link, text)
        
        # Autolinks
        text = re.sub(
            r'&lt;(https?://[^\s&]+)&gt;',
            r'<a href="\1">\1</a>',
            text
        )
        text = re.sub(
            r'&lt;([^@\s]+@[^@\s]+\.[^@\s]+)&gt;',
            r'<a href="mailto:\1">\1</a>',
            text
        )
        
        # Footnotes
        def process_footnote(match):
            ref_id = match.group(1)
            if ref_id not in self.footnote_refs:
                self.footnote_refs.append(ref_id)
            return f'<sup><a href="#fn{ref_id}" id="fnref{ref_id}">[{ref_id}]</a></sup>'
        
        text = re.sub(r'\[\^([^\]]+)\]', process_footnote, text)
        
        # Emphasis (order matters!)
        # Strong + emphasis
        text = re.sub(r'\*\*\*(\S(?:.*?\S)?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'___(\S(?:.*?\S)?)___', r'<strong><em>\1</em></strong>', text)
        
        # Strong
        text = re.sub(r'\*\*(\S(?:.*?\S)?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(\S(?:.*?\S)?)__', r'<strong>\1</strong>', text)
        
        # Emphasis
        text = re.sub(r'\*(\S(?:.*?\S)?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(\S(?:.*?\S)?)_', r'<em>\1</em>', text)
        
        # Strikethrough
        text = re.sub(r'~~(\S(?:.*?\S)?)~~', r'<del>\1</del>', text)
        
        # Line breaks
        text = re.sub(r'  $', '<br>', text, flags=re.MULTILINE)
        
        return text
    
    def _generate_footnotes_html(self) -> str:
        """Generate HTML for footnotes"""
        html_parts = ['\n<div class="footnotes">\n<hr>\n<ol>']
        
        for fn_id in self.footnote_refs:
            if fn_id in self.footnotes:
                content = self._process_inline(html.escape(self.footnotes[fn_id]))
                html_parts.append(
                    f'<li id="fn{fn_id}">{content} '
                    f'<a href="#fnref{fn_id}" class="footnote-backref">↩</a></li>'
                )
        
        html_parts.append('</ol>\n</div>')
        return '\n'.join(html_parts)


class MarkdownViewer(BasePreviewViewer):
    """Markdown preview widget with enhanced features"""
    
    def __init__(self, colors):
        super().__init__(colors)
        self.parser = MarkdownParser()
    
    def setup_custom_style(self):
        """Apply markdown-specific styling to the preview"""
        style = f"""
            body {{
                max-width: 900px;
                margin: 0 auto;
            }}
            
            /* Headers */
            h1, h2, h3, h4, h5, h6 {{
                margin-top: 24px;
                margin-bottom: 16px;
                font-weight: 600;
                line-height: 1.25;
                color: {self.colors["white"]};
            }}
            
            h1 {{ 
                font-size: 2em; 
                border-bottom: 1px solid {self.colors["gray3"]}; 
                padding-bottom: 0.3em; 
                margin-top: 0;
            }}
            h2 {{ 
                font-size: 1.5em; 
                border-bottom: 1px solid {self.colors["gray3"]}; 
                padding-bottom: 0.3em; 
            }}
            h3 {{ font-size: 1.25em; }}
            h4 {{ font-size: 1em; }}
            h5 {{ font-size: 0.875em; }}
            h6 {{ font-size: 0.85em; color: {self.colors["gray4"]}; }}
            
            /* Paragraphs */
            p {{
                margin-bottom: 16px;
                margin-top: 0;
            }}
            
            /* Text formatting */
            strong {{ font-weight: 600; }}
            em {{ font-style: italic; }}
            del {{ text-decoration: line-through; color: {self.colors["gray4"]}; }}
            
            /* Links */
            a {{
                color: {self.colors["blue"]};
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            
            /* Code */
            code {{
                background-color: {self.colors["gray2"]};
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 0.9em;
                color: {self.colors["green"]};
            }}
            
            pre {{
                background-color: {self.colors["gray2"]};
                border: 1px solid {self.colors["gray3"]};
                border-radius: 6px;
                padding: 16px;
                overflow-x: auto;
                margin-bottom: 16px;
                line-height: 1.45;
            }}
            
            pre code {{
                background-color: transparent;
                padding: 0;
                color: {self.colors["white"]};
                display: block;
            }}
            
            /* Blockquotes */
            blockquote {{
                border-left: 4px solid {self.colors["gray3"]};
                padding-left: 16px;
                color: {self.colors["gray4"]};
                margin: 16px 0;
                font-style: italic;
            }}
            
            blockquote p {{
                margin-bottom: 8px;
            }}
            
            blockquote p:last-child {{
                margin-bottom: 0;
            }}
            
            /* Lists */
            ul, ol {{
                margin-bottom: 16px;
                padding-left: 2em;
            }}
            
            li {{
                margin-bottom: 4px;
            }}
            
            /* Tables */
            table {{
                border-collapse: collapse;
                margin-bottom: 16px;
                width: 100%;
            }}
            
            th, td {{
                border: 1px solid {self.colors["gray3"]};
                padding: 8px 12px;
            }}
            
            th {{
                background-color: {self.colors["gray2"]};
                font-weight: 600;
            }}
            
            tr:nth-child(even) {{
                background-color: rgba(255, 255, 255, 0.02);
            }}
            
            /* Horizontal rules */
            hr {{
                border: 0;
                height: 1px;
                background: {self.colors["gray3"]};
                margin: 24px 0;
            }}
            
            /* Images */
            img {{
                max-width: 100%;
                height: auto;
                border-radius: 6px;
                margin: 16px 0;
            }}
            
            /* Footnotes */
            .footnotes {{
                margin-top: 48px;
                font-size: 0.9em;
                color: {self.colors["gray4"]};
            }}
            
            .footnotes hr {{
                margin: 24px 0 16px 0;
            }}
            
            .footnotes ol {{
                padding-left: 1.5em;
            }}
            
            .footnote-backref {{
                text-decoration: none;
                margin-left: 0.5em;
            }}
            
            sup {{
                font-size: 0.8em;
                vertical-align: super;
                line-height: 0;
            }}
        """
        
        self.document().setDefaultStyleSheet(style)
    
    def update_content(self, markdown_text):
        """Update the preview with rendered markdown"""
        if not markdown_text.strip():
            self.show_empty_message("Markdown")
            return
            
        try:
            html_content = self.parser.parse(markdown_text)
            
            # Wrap in basic HTML structure
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """
            
            self.preserve_scroll_position(lambda: self.setHtml(full_html))
            
        except Exception as e:
            self.show_error(html.escape(str(e)), "Markdown Parsing Error")


class MarkdownPreviewWidget(BasePreviewWidget):
    """Combined widget with splitter for editor and preview"""
    
    def __init__(self, text_edit, colors):
        super().__init__(text_edit, colors, MarkdownViewer)


def integrate_markdown_viewer(main_window):
    """
    Integration function to add markdown viewer to existing Notepad app
    Call this from the main app after initialization
    """
    # Replace central widget with preview widget
    old_central = main_window.centralWidget()
    old_layout = old_central.layout()
    text_edit = main_window.text_edit
    
    # Remove text_edit from old layout
    old_layout.removeWidget(text_edit)
    
    # Create new preview widget
    preview_widget = MarkdownPreviewWidget(text_edit, main_window.colors)
    main_window.setCentralWidget(preview_widget)
    main_window.preview_widget = preview_widget
    
    # Add menu items
    view_menu = None
    for action in main_window.menuBar().actions():
        if action.text() == '&View':
            view_menu = action.menu()
            break
    
    if view_menu:
        view_menu.addSeparator()
        
        # Toggle preview action
        preview_action = main_window.add_menu_action(
            view_menu, 
            'Markdown &Preview', 
            lambda: toggle_preview_callback(main_window),
            'Ctrl+Shift+P'
        )
        preview_action.setCheckable(True)
        main_window.preview_action = preview_action
        
        # Live preview action
        live_preview_action = main_window.add_menu_action(
            view_menu,
            '&Live Preview',
            lambda: toggle_live_preview_callback(main_window),
            checkable=True,
            checked=True  # Enable by default
        )
        main_window.live_preview_action = live_preview_action
        
        # Refresh preview action
        main_window.add_menu_action(
            view_menu,
            '&Refresh Preview',
            lambda: refresh_preview_callback(main_window),
            'F5'
        )


def toggle_preview_callback(main_window):
    """Callback for toggle preview menu action"""
    is_visible = main_window.preview_widget.toggle_preview()
    main_window.preview_action.setChecked(is_visible)
    
    # Update live preview connection
    if main_window.live_preview_action.isChecked():
        main_window.preview_widget.set_live_preview(is_visible)


def toggle_live_preview_callback(main_window):
    """Callback for toggle live preview menu action"""
    enabled = main_window.live_preview_action.isChecked()
    main_window.preview_widget.set_live_preview(enabled)
    
    # If preview is visible and live preview was just enabled, update it
    if enabled and main_window.preview_widget.preview_visible:
        main_window.preview_widget.update_preview()


def refresh_preview_callback(main_window):
    """Manually refresh the preview"""
    if main_window.preview_widget.preview_visible:
        main_window.preview_widget._do_update_preview()