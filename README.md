# Notepad --

A PyQt6 text editor with syntax highlighting and live preview functionality.


<img width="1494" height="839" alt="screenshot_02" src="https://github.com/user-attachments/assets/19cba204-b961-4f82-bbe6-8802a17bd420" />
<img width="1535" height="831" alt="screenshot_03" src="https://github.com/user-attachments/assets/0d1a9e97-b484-42bb-aabd-2500cdf383ae" />


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

### Building
```bash
pyinstaller Notepad.spec
```

## Supported Languages

Syntax highlighting for Python, JavaScript, TypeScript, HTML, CSS, JSON, XML, shell scripts, and configuration files. Preview support for HTML, Markdown, and XML files.

## Technical Notes

Built with PyQt6, uses QWebEngine for HTML preview, custom regex-based syntax parsing, and PyInstaller for distribution. Implements common GUI patterns including factory methods, worker threads, and observer updates.
