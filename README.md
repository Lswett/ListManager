# ListManager – Version 1

A desktop mailing list processing application designed for production mail environments.

ListManager ingests CSV/Excel data, applies USPS-style validation logic, analyzes DBF files, and exports production-ready datasets through a GUI-based workflow.

Version 1 is fully packaged as a Windows executable and is currently used in a university mailroom environment to support live mailing operations.

---

## Project Overview

Mail production workflows often involve:

- Merging multiple spreadsheet inputs
- Cleaning inconsistent column formats
- Enforcing USPS-related validation rules
- Reviewing barcode and ZIP issues
- Separating clean vs quarantine records
- Producing files ready for mailing systems

ListManager consolidates these steps into a single desktop application.

This project focuses on practical operational reliability, validation transparency, and a clear user workflow for production staff.

---

## Key Capabilities

### Merge & Normalize Engine

- Consolidates spreadsheet inputs from a defined folder
- Trims whitespace and normalizes headers
- Enforces ≤10-character header constraints
- Generates sequential Unique IDs
- Outputs production-ready merged datasets

### Validation System

- Applies USPS-style rule checks (ZIP, barcode presence, DPV-style logic, etc.)
- Classifies records into:
  - Hard-stop errors
  - Review-required warnings
- Tracks per-record validation reasons
- Produces auditable summaries

### DBF Breakdown Module

- Ingests `.dbf` files
- Auto-detects grouping fields (prefers `SCHOOL` when available)
- Computes record counts and percentages
- Flags barcode gaps
- Supports clean vs quarantine export flows

### Clean List Workflow

- Interactive rule selection for quarantine
- Contextual explanations for validation failures
- Exports:
  - Clean production dataset
  - Quarantine dataset (retains all fields + `ERROR_REASON`)
- Reassigns sequential Unique IDs for final export

### Desktop UX

- PySide6-based GUI
- Non-blocking worker threads
- Integrated log viewer
- Persistent folder selectors
- Light/Dark theme toggle (qt-material + PyQtDarkTheme)

---

## Real-World Deployment

- Packaged via PyInstaller into a standalone Windows executable
- Distributed internally for production use
- Actively used in a university mailroom environment
- Supports live mailing operations and compliance workflows

This is an operational production tool, not a prototype.

---

## Technical Stack

- Python 3.10+
- PySide6 (Qt for Python)
- pandas
- openpyxl
- dbfread
- qt-material
- PyQtDarkTheme
- PyInstaller (Windows executable distribution)

Project structure follows a `src/` layout:

```text
src/listmanager/
    core/
        merge.py
        normalize.py
        validate.py
        dbf_breakdown.py
    gui.py
    cli.py
```

Core processing logic is separated from the UI layer to maintain modularity and testability.

---

## Installation (Development)

```bash
pip install -r requirements.txt
```

---

## CLI Usage

```bash
python -m listmanager.cli --outdir out
```

Optional flags:

- `--inputdir PATH` (default: `ListInput`)
- `--start-row N` (default: 8)

---

## GUI Usage

```bash
python -m listmanager.gui
```

Workflow:

1. Select Input and Output folders
2. Configure data start row
3. Run Merge process
4. Optionally analyze DBF files
5. Review validation summary
6. Export clean and quarantine outputs

---

## Building the Windows Executable

```bash
pip install -e .[build]
pyinstaller --clean --noconfirm listmanager_gui.spec
```

Distribute the contents of:

```text
dist/ListManager/
```

Includes:

- `ListManager.exe`
- Required Qt plugins
- Embedded configuration

---

## Roadmap

- Expand validation coverage (additional Mail.dat-style rules)
- Add user profiles for different production workflows
- Extend analytics for error trend tracking
- Increase automated test coverage for core validation logic

---

## Development Notes

Version 1 was accelerated using AI-assisted scaffolding for repetitive components. Architecture decisions, validation logic, workflow design, packaging, and production deployment were directed and implemented to meet real operational requirements.

The project continues to evolve through iterative refinement based on production use.