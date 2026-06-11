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
- Convert messy Excel mailing lists into official COMPANY, FULLNAME, or FIRSTLAST workbooks.
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

The GUI includes three tabs:

- `Merge`: choose input/output folders, set the data start row, and run the spreadsheet merge.
- `Format Checker`: convert messy Excel files into standardized workbooks before merging.
- `DBF Breakdown`: choose a DBF file, analyze counts by column, create clean lists, and export results.

## CLI Usage

```bash
.\venv\Scripts\python.exe run_merge.py --outdir out
```

Optional flags:

- `--inputdir PATH` defaults to `ListInput`
- `--start-row N` defaults to `8`

## Format Checker

The Format Checker workflow converts messy `.xlsx` or `.xlsm` mailing-list files
into standardized ListManager workbooks before they are merged. It writes one
converted workbook per source file. Each converted workbook contains:

- `COMPANY`, `FULLNAME`, or `FIRSTLAST` as the main clean output sheet
- `NEEDS_REVIEW` inside the same workbook
- `CONVERSION_REPORT` inside the same workbook

Rows with warnings can still go to the main sheet. Rows with blocking issues,
including international mail, missing required fields, invalid ZIPs, ZIPs not
found in the local lookup, and state/ZIP mismatches, go to `NEEDS_REVIEW`.
Duplicates are not removed during this stage.

Run from the command line:

```bash
.\venv\Scripts\python.exe -m listmanager.format_checker.convert examples/messy_inputs examples/converted_outputs
```

The input argument can be one Excel file or a folder of Excel files. The GUI has
a separate `Format Checker` tab with scan, convert, results table, and output
folder controls. The existing `Merge` tab remains for already standardized files.

## Template Export

After a workbook has been converted and reviewed, export its passed records into
the official mailing list template:

```bash
.\venv\Scripts\python.exe -m listmanager.template_export input_converted.xlsx MailingListTemplate.xlsx output_template_ready.xlsx
```

The exporter reads only the passed-records sheet from the converted workbook:
`COMPANY`, `FULLNAME`, or `FIRSTLAST`. It writes those rows into the matching
template tab, starting at row 8. Template rows 1-7, row 4 headers, instructions,
examples, formatting, tab names, and other tabs are preserved. `NEEDS_REVIEW`
and `CONVERSION_REPORT` are intentionally excluded.

The same workflow is available in the GUI under `Export to Mailing Template`:

1. Run the normal Format Checker conversion/validation process.
2. Review the converted workbook if needed.
3. Open `Export to Mailing Template`.
4. Select the converted workbook.
5. Select `MailingListTemplate.xlsx`.
6. Choose where to save the template-ready workbook.
7. Click `Export to Template`.

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
