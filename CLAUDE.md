# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is "Notepad --", a PyQt6-based text editor with advanced features including syntax highlighting, live preview, and file management. It's a modern replacement for basic text editors with IDE-like capabilities.

## Development Commands

### Running the Application
```bash
python main.py [optional_file_path]
```

### Building Executable
```bash
# Uses PyInstaller with Notepad.spec configuration
pyinstaller Notepad.spec
```

### Testing
No automated test framework is currently configured. Manual testing should focus on:
- File operations (open, save, new)
- Syntax highlighting for various languages
- Preview functionality for HTML/Markdown/XML
- Encoding detection and conversion

## Architecture Overview

### Core Structure
- **main.py**: Entry point and main application class (`Notepad`) containing all UI logic, file operations, and application state
- **components/**: Preview and UI components
  - `unified_preview.py`: Manages all preview types (HTML, Markdown, XML) through a unified interface
  - `base_preview_viewer.py`: Base class for preview widgets
  - `modules/`: Specific preview implementations (markdown_viewer, xml_viewer, html_viewer)
- **utils/**: Utility modules
  - `syntax_highlighter.py`: Comprehensive syntax highlighting system supporting multiple languages

### Key Design Patterns
- **Unified Preview System**: All preview types (HTML, Markdown, XML) are managed through `UnifiedPreviewManager` which handles switching between different preview widgets dynamically
- **Syntax Highlighting**: Extensible highlighter system with language-specific classes inheriting from `SyntaxHighlighter`
- **File Worker Pattern**: Background file operations using `QThread` and `FileWorker` for non-blocking I/O
- **Settings Management**: Uses `QSettings` for persistent configuration storage

### Application State
- Current file path, encoding, and modification state tracked in main window
- Backup system with automatic recovery on startup
- Recent files list with configurable maximum
- Theme system using Atom One Dark color scheme

### Preview System Integration
The preview system is modular and file-type-aware:
- Preview widgets are created on-demand and cached
- Live preview mode updates content as you type
- Manual refresh capability (F5)
- Preview visibility is toggled per file type

### Supported File Types
**Programming**: Python, JavaScript, TypeScript, HTML, CSS, JSON, XML, C/C++, Java, C#, Go, Rust, PHP, Ruby
**Documents**: Markdown, Plain Text, Configuration files (INI, YAML, TOML), Shell scripts

## Key Components to Understand

### Main Window (`main.py:369-1528`)
- Central application logic
- File operations with encoding detection
- Menu system with dynamic visibility based on file type
- Theme and UI management

### Syntax Highlighting (`utils/syntax_highlighter.py`)
- Language-specific highlighters: `PythonHighlighter`, `JavaScriptHighlighter`, `HtmlHighlighter`, etc.
- Factory function `get_highlighter_for_file()` for automatic language detection
- One Dark theme integration for consistent coloring

### Preview System (`components/unified_preview.py`)
- `UnifiedPreviewManager` handles all preview types
- Dynamic widget creation and caching
- File type detection and menu visibility management

## Development Guidelines

### File Operations
- All file I/O should use `FileWorker` for background processing
- Encoding detection is handled automatically via `detect_encoding_with_bom()`
- Backup files are created automatically and cleaned on successful save

### Adding New Language Support
1. Create new highlighter class in `syntax_highlighter.py` inheriting from `SyntaxHighlighter`
2. Add file extension mapping in `get_highlighter_for_file()`
3. Update `TEXT_EXTENSIONS` set in `main.py` if needed

### Adding New Preview Types
1. Create new viewer module in `components/modules/`
2. Add preview type mapping in `unified_preview.py:PREVIEW_TYPES`
3. Add widget creation logic in `UnifiedPreviewManager.get_or_create_preview_widget()`

### UI Theme Customization
- Colors are defined in `main.py:393-413` as the `colors` dictionary
- VS Code-inspired stylesheet in `setupTheme()` method
- Icon system uses inline SVG with color replacement

## Build Configuration

### PyInstaller Settings (`Notepad.spec`)
- Entry point: `main.py`
- Icon: `icon.ico`
- Console mode disabled for windowed application
- UPX compression enabled