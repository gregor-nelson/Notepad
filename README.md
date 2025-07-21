# Notepad --

A PyQt6 text editor with syntax highlighting and live preview functionality.

<img width="1920" height="1080" alt="screenshot_03" src="https://github.com/user-attachments/assets/c6c0db1c-9561-401e-abb3-8de635760828" />

<img width="1494" height="839" alt="screenshot_02" src="https://github.com/user-attachments/assets/19cba204-b961-4f82-bbe6-8802a17bd420" />

<img width="1052" height="692" alt="screenshot_01" src="https://github.com/user-attachments/assets/53cd245e-3598-4120-b442-daa038fae578" />

## Features

- Multi-language syntax highlighting (Python, JavaScript, TypeScript, HTML, CSS, JSON, XML, shell scripts)
- Line numbers and text statistics
- Auto-backup with crash recovery
- Encoding detection (UTF-8, UTF-16, etc.)
- Recent files list

- Live preview for HTML, Markdown, and XML files
- QWebEngine-based HTML rendering with CSS/JS support
- Custom markdown parser
- Side-by-side editor and preview layout

- Atom One Dark colour scheme
- SVG icons with colour theming
- Font selection
- Find and replace with regex support
- Print functionality

## Architecture

### Structure
- `main.py` - Main application window with file operations and UI management
- `utils/syntax_highlighter.py` - Language-specific highlighters using regex parsing
- `components/unified_preview.py` - Preview system managing different file types
- `components/modules/` - Individual preview implementations (markdown, HTML, XML)

### Implementation Details
- Multi-threaded file I/O using QThread workers to prevent UI blocking
- Factory pattern for creating appropriate syntax highlighters based on file extension
- State machine parsing for multi-line constructs (docstrings, comments, template literals)
- Widget caching in preview system for performance
- Settings persistence using QSettings

## Usage

### Requirements
```bash
pip install PyQt6 PyQt6-WebEngine
```

### Running
```bash
python main.py [file_path]
```

### Building
```bash
pyinstaller Notepad.spec
```

## Supported Languages

Syntax highlighting for Python, JavaScript, TypeScript, HTML, CSS, JSON, XML, shell scripts, and configuration files. Preview support for HTML, Markdown, and XML files.

## Technical Notes

Built with PyQt6, uses QWebEngine for HTML preview, custom regex-based syntax parsing, and PyInstaller for distribution. Implements common GUI patterns including factory methods, worker threads, and observer updates.
