# ListManager

ListManager is a desktop mailing list processing tool for merging spreadsheet inputs,
validating records, analyzing DBF files, and exporting production-ready CSV datasets.

## Capabilities

- Merge `.csv`, `.xlsx`, `.xlsm`, and `.xls` input files from a folder.
- Normalize whitespace, countries, ZIP values, and output headers.
- Generate deterministic per-row `UniqueFileID` values.
- Split valid US, international, and error rows into separate output files.
- Fill or verify US state values from a local offline ZIP lookup.
- Move unsupported international mail into review output instead of normal output.
- Analyze `.dbf` files by a selected grouping column.
- Review DBF validation warnings and hard-stop errors.
- Create clean and quarantine exports from selected validation rules.

## Requirements

- Python 3.10 or newer
- pandas
- openpyxl
- xlrd
- dbfread

The GUI uses `tkinter`, which ships with the standard Windows Python installer. It does
not require PySide6, Qt theme packages, or other GUI binary wheels.

## Installation

```bash
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

For an existing venv, reinstall the editable project after dependency changes:

```bash
.\venv\Scripts\python.exe -m pip install -e .
```

## GUI Usage

```bash
.\venv\Scripts\python.exe gui.py
```

The GUI includes two tabs:

- `Merge`: choose input/output folders, set the data start row, and run the spreadsheet merge.
- `DBF Breakdown`: choose a DBF file, analyze counts by column, create clean lists, and export results.

## CLI Usage

```bash
.\venv\Scripts\python.exe run_merge.py --outdir out
```

Optional flags:

- `--inputdir PATH` defaults to `ListInput`
- `--start-row N` defaults to `8`

## Local ZIP Lookup

Runtime ZIP/state checks use `resources/zip_lookup/us_zip_state_lookup.csv`.
The app does not call USPS, HUD, or any ZIP API while processing lists.

USPS City State Product was checked first because it is the official preferred
source for city/state/ZIP validation. USPS publishes it through EPF/AIS access;
the product page describes the data as encrypted and not exportable from the
viewer, so it is not bundled here. HUD-USPS ZIP Code Crosswalk files are the
preferred public fallback when you can place source CSVs under
`resources/zip_lookup/source/`; HUD notes those files exclude PO Box only ZIPs
and can miss a small number of active ZIP Codes.

The current bundled source is an archived third-party CSV fallback with ZIP,
city, and state columns. It is not official USPS validation data. Rebuild the
lookup after replacing or updating source files:

```bash
.\venv\Scripts\python.exe -m listmanager.zip_lookup.build_zip_lookup
```

The build writes:

- `resources/zip_lookup/us_zip_state_lookup.csv`
- `resources/zip_lookup/build_report.txt`

ZIP values are stored as text, so leading zeros such as `06110` are preserved.
Census ZCTA data should only be used as a last resort because ZCTAs are Census
geographic approximations, not USPS ZIP validation data.

International mail is intentionally moved to review output with
`INTERNATIONAL_MAIL_REVIEW_REQUIRED` so it can be handled manually. This
converter currently supports US mailing formats only.

## Build A Windows Executable

```bash
.\venv\Scripts\python.exe -m pip install -e .[build]
.\venv\Scripts\pyinstaller.exe --clean --noconfirm listmanager_gui.spec
```

The packaged application is written to `dist/ListManager/`.

## Project Layout

```text
src/listmanager/
    core/
        merge.py
        normalize.py
        validate.py
        dbf_breakdown.py
    cli.py
    gui.py
```

The core processing logic is separate from the GUI so it can be used by both the
desktop app and command-line entry points.
