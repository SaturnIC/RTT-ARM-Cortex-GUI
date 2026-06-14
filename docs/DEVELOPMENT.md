# Development Guide

## Table of Contents
- [Project Structure](#project-structure)
- [Running from Source](#running-from-source)
- [Demo Mode](#demo-mode)
- [Testing](#testing)
- [Building Executables](#building-executables)
  - [Prerequisites](#prerequisites)
  - [Building](#building)
  - [How It Works](#how-it-works)
  - [Troubleshooting](#troubleshooting)

## Project Structure

```
rtt_python_gui.py           # Main application entry point
requirements.txt            # Python dependencies
rtt_python_gui.spec         # PyInstaller build spec
debug/
    demo_log.txt           # Demo mode sample log data
libs/
    jlink/
        rtt_handler.py           # Real J-Link RTT handler
        rtt_handler_interface.py # Abstract base class for handlers
        demo_rtt_handler.py      # Demo mode handler (replays demo_log.txt)
    log/
        log_controller.py        # Log filtering, highlighting, pausing logic
        log_view.py              # GUI log display widget
tests/
    test_config_functionality.py # Config load/save tests
    test_main_functionality.py   # Integration tests (demo mode, MCU selection)
docs/
    DEVELOPMENT.md               # This file
```

## Running from Source

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate     # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python rtt_python_gui.py
   ```

## Demo Mode

Test without hardware by replaying a sample log file:
```bash
python rtt_python_gui.py --demo-messages
```
The demo handler reads from `debug/demo_log.txt`. Each line is fed into the application as if it came from an RTT connection.

## Testing

Run the test suite:
```bash
python -m pytest tests/ -v
```

Tests cover:
- Config file loading and saving
- Demo mode initialization and MCU list
- GUI event handling

## Building Executables

The application can be frozen into a standalone executable using [PyInstaller](https://pyinstaller.org/).

### Prerequisites

Install PyInstaller in your virtual environment:
```bash
pip install pyinstaller
```

### Building

Use the provided spec file:
```bash
pyinstaller rtt_python_gui.spec
```

The executable will be created in the `dist/` directory.

The spec file handles:
- Collecting matplotlib data files (fonts, matplotlibrc) via `collect_data_files`
- Bundling `debug/demo_log.txt` for demo mode
- Explicit hidden imports for matplotlib C extensions and PIL
- Excluding unused packages (Qt, Wx, GTK, scipy, pandas)
- Stripping debug symbols (`strip=True`) and UPX compression (`upx=True`) to reduce size

### How It Works

**PyInstaller spec (`rtt_python_gui.spec`):**
- `collect_data_files('matplotlib', include_py_files=False)` — collects only matplotlib data files (fonts, config)
- `datas=[('debug/demo_log.txt', 'debug')]` — bundles the demo log file inside the executable
- `hiddenimports` — includes matplotlib C extensions and `PIL._tkinter_finder` that PyInstaller can't auto-detect
- `excludes` — removes unused packages to reduce binary size

**Demo handler path resolution (`libs/jlink/demo_rtt_handler.py`):**
When frozen, PyInstaller extracts bundled files to a temporary directory accessible via `sys._MEIPASS`. The demo handler checks for this:
```python
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.join(base_path, '..', '..')
log_path = os.path.join(base_path, 'debug', 'demo_log.txt')
```

**Config file:**
The config file is stored at the platform's user data directory (via `platformdirs`), not inside the app bundle. This works correctly in both source and frozen modes.

### Troubleshooting

**`ModuleNotFoundError: No module named 'PIL._tkinter_finder'`**
Make sure you're using the spec file (`pyinstaller rtt_python_gui.spec`) rather than a plain `pyinstaller` command. The spec includes the necessary hidden imports.

**`demo_log.txt not found` when running the frozen binary**
The demo log file must be bundled via the `datas` entry in the spec file. Rebuild with the spec file.

**Matplotlib charts not rendering**
If charts appear blank or throw errors in the frozen binary, ensure `collect_data_files('matplotlib')` is present in the spec file and the hidden imports include `matplotlib.backends.backend_tkagg`.

**Large executable size**
Matplotlib, numpy, and PIL are large libraries (~30-40MB combined). The spec file excludes unused backends and modules. To reduce further:
- Install UPX (`sudo apt install upx` on Linux, `brew install upx` on macOS) for binary compression
- Add more modules to the `excludes` list in the spec file
