# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a PyQt6-based text editor called "Notepad --" with VS Code-inspired dark theming and advanced features including syntax highlighting, preview capabilities, and file management.

## Build and Development Commands

### Building the Executable
```bash
# Build executable using PyInstaller
pyinstaller Notepad.spec
```

### Running the Application
```bash
# Run directly
python main.py

# Run with a specific file
python main.py filename.txt
```

## Core Architecture

### Main Components
- **main.py**: Core application with `Notepad` class (QMainWindow)
- **syntax_highlighter.py**: Syntax highlighting system with multiple language support
- **unified_preview.py**: Preview system manager for markdown, HTML, XML
- **base_preview_viewer.py**: Standardized base classes for all preview viewers
- **xml_viewer.py**: XML-specific preview functionality (extends BasePreviewViewer)
- **markdown_viewer.py**: Markdown preview functionality (extends BasePreviewViewer)
- **html_viewer.py**: HTML preview functionality (extends BasePreviewViewer)

### Key Design Patterns
- **Modular Preview System**: Uses a unified preview manager that registers different preview types based on file extensions
- **Standardized Preview Architecture**: All preview viewers extend `BasePreviewViewer` and `BasePreviewWidget` for consistent interface and behavior
- **Theme System**: VS Code-inspired color scheme stored in `self.colors` dictionary
- **File Worker Threading**: Background file operations using `QThread` and `FileWorker` class
- **Plugin Architecture**: Preview modules are integrated via the `unified_preview.integrate_unified_preview()` function

### Application Structure
```
main.py (QMainWindow)
├── TextEditWithLineNumbers (QPlainTextEdit with line numbers)
├── LineNumberArea (Custom widget for line numbers)
├── UnifiedPreviewManager (Preview system)
├── FileWorker (Background file operations)
├── Icons (SVG-based icon system)
└── Preview Viewers (All extend base classes):
    ├── BasePreviewViewer (Abstract base for content viewers)
    ├── BasePreviewWidget (Abstract base for splitter widgets)
    ├── HTMLViewer/HTMLPreviewWidget
    ├── MarkdownViewer/MarkdownPreviewWidget
    └── XMLViewer/XMLPreviewWidget (with XMLTreeWidget & XMLFormattedView)
```

### Preview System Integration
The preview system is modular and extensible:
- Extensions are registered in `PREVIEW_TYPES` dictionary
- Each preview type has its own module (markdown_viewer, xml_viewer, html_viewer)
- All viewers follow standardized interface: `BasePreviewViewer.update_content()` and `BasePreviewWidget`
- Common functionality (styling, error handling, scroll preservation) is provided by base classes
- Preview widgets are created on-demand and cached
- Integration happens through `unified_preview.integrate_unified_preview(main_window)`

### File Handling
- Supports multiple encodings with BOM detection
- Backup system for unsaved changes
- Recent files management
- Drag and drop support for text files
- Large file handling with chunked reading/writing

### Color Scheme
Uses VS Code Dark+ inspired colors accessible via `self.colors`:
- `"black"`: Main background (#1e1e1e)
- `"white"`: Main text (#d4d4d4)
- `"blue"`: Accent color (#007acc)
- `"selection"`: Selection background (#264f78)
- And more defined in `setupTheme()` method

## Key Configuration
- Organization: "InterMoor"
- Application: "Notepad --"
- Default encoding: UTF-8
- Backup interval: 30 seconds
- Autosave interval: 5 minutes
- Max recent files: 10
- Supported text file extensions in `TEXT_EXTENSIONS` set

## Development Notes
- The application uses QSettings for persistent configuration
- Custom SVG icons are defined inline in the `Icons` class
- Syntax highlighting is file extension-based
- Preview functionality is automatically integrated when the application starts
- The application supports both standalone text editing and split-view preview modes