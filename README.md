# ListManager

Desktop mailing-list processing tool for merging spreadsheet inputs, validating records, analyzing DBF files, and exporting production-ready datasets.

ListManager was built as a companion tool for coworkers at my workplace who need to use mailing/presort software they aren't fluent in. It packages the tedious, error-prone parts of list preparation, including merging, normalization, ZIP/state validation, and template formatting, behind a GUI that a non-technical user can run confidently.

The goal is for users to understand the basic principles of the workflow without needing to understand every technical step involved in preparing a mailing list.

A CLI sits underneath the same core logic for repeatable, scripted runs.

> **Status:** Actively developed; in production use.

## Typical Workflow

1. **Format Checker** converts messy `.xlsx`/`.xlsm` files into standardized workbooks containing:

   * Valid rows
   * `NEEDS_REVIEW`
   * `CONVERSION_REPORT`
2. Review flagged rows, including:

   * International mail
   * Missing fields
   * Invalid ZIPs
   * State/ZIP mismatches
3. **Export to Mailing Template** writes passed records into the official template.
4. Alternatively, run **Merge** directly on already-standardized files.

## Capabilities

* Merge `.csv`, `.xlsx`, `.xlsm`, and `.xls` input files from a folder
* Normalize whitespace, countries, ZIP values, and output headers
* Generate deterministic per-row `UniqueFileID` values
* Split valid US, international, and error rows into separate output files
* Fill or verify US state values using a local offline ZIP lookup
* Perform ZIP/state validation without API calls at runtime
* Route international mail into a review output instead of normal output
* Convert messy Excel mailing lists into standardized `COMPANY` / `FULLNAME` / `FIRSTLAST` workbooks
* Analyze `.dbf` files by a selected grouping column
* Review DBF validation warnings and hard-stop errors
* Create clean and quarantine exports from DBF data

## Requirements

* Python 3.10+
* `pandas`
* `openpyxl`
* `xlrd`
* `dbfread`
* Tkinter

Tkinter ships with the standard Windows Python installer, so no Qt/PySide6 binary wheels are required.

## Installation

Create a virtual environment and install the project dependencies:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

For an existing virtual environment after dependency changes:

```powershell
.\venv\Scripts\python.exe -m pip install -e .
```

## GUI Usage

Launch the desktop application with:

```powershell
.\venv\Scripts\python.exe gui.py
```

The GUI contains three primary tabs:

### Merge

* Choose input and output folders
* Set the data start row
* Run the spreadsheet merge

### Format Checker

* Scan input files
* Convert and validate records
* Review results in a table
* Choose the output folder

### DBF Breakdown

* Select a DBF file
* Analyze record counts by a selected column
* Create clean lists
* Export results

The GUI also includes **Export to Mailing Template** for the template export workflow.

## CLI Usage

Run the merge process with:

```powershell
.\venv\Scripts\python.exe run_merge.py --outdir out
```

### CLI Options

| Flag          | Default     | Purpose        |
| ------------- | ----------- | -------------- |
| `--inputdir`  | `ListInput` | Input folder   |
| `--start-row` | `8`         | First data row |
| `--outdir`    | `out`       | Output folder  |

## Format Checker

The Format Checker converts messy `.xlsx`/`.xlsm` mailing lists into standardized workbooks.

One output workbook is created per source file. Each workbook contains:

### `COMPANY` / `FULLNAME` / `FIRSTLAST`

The clean, standardized output sheet containing records that passed validation.

### `NEEDS_REVIEW`

Contains rows with blocking issues, including:

* International mail
* Missing required fields
* Invalid ZIPs
* ZIPs not found in the local lookup
* State/ZIP mismatches

### `CONVERSION_REPORT`

Contains details about the conversion and transformations performed on the source data.

Rows with warnings still go to the main output sheet, while blocked rows are routed to `NEEDS_REVIEW`.

> **Note:** Duplicates are not removed during the Format Checker stage.

### Run from the CLI

```powershell
.\venv\Scripts\python.exe -m listmanager.format_checker.convert examples/messy_inputs examples/converted_outputs
```

The input argument can be either:

* A single Excel file
* A folder containing Excel files

## Template Export

Template Export writes validated records into the official mailing-list template while preserving the template's existing structure.

The export preserves:

* Template rows 1–7
* Row 4 headers
* Instructions
* Example rows
* Formatting
* Tab names
* Other template tabs

The following sheets are intentionally excluded:

* `NEEDS_REVIEW`
* `CONVERSION_REPORT`

### CLI

```powershell
.\venv\Scripts\python.exe -m listmanager.template_export input_converted.xlsx MailingListTemplate.xlsx output_template_ready.xlsx
```

### GUI

The same workflow is available through **Export to Mailing Template**:

1. Run the normal Format Checker conversion and validation process.
2. Review the converted workbook if needed.
3. Open **Export to Mailing Template**.
4. Select the converted workbook.
5. Select `MailingListTemplate.xlsx`.
6. Choose where to save the template-ready workbook.
7. Click **Export to Template**.

## ZIP/State Validation

### Fully Offline

ZIP/state validation never calls USPS, HUD, or any ZIP API at runtime.

The project uses a local lookup file so mailing-list validation can run without an internet connection or external API dependency.

### Data Sources

The sourcing decision is:

#### USPS City State Product

The official preferred source. However, the published data is encrypted and non-exportable from the viewer, preventing it from being bundled directly with the application.

#### HUD-USPS ZIP Code Crosswalk

The preferred public fallback.

Source CSV files can be placed under:

```text
resources/zip_lookup/source/
```

> **Caveat:** HUD notes that these files exclude PO-Box-only ZIPs and may miss a small number of active ZIP Codes.

#### Bundled Fallback

The project also includes an archived third-party CSV containing ZIP, city, and state columns.

This is **not official USPS validation data** and is provided as a fallback.

### Rebuilding the Lookup

After replacing or updating the source files, rebuild the local lookup with:

```powershell
.\venv\Scripts\python.exe -m listmanager.zip_lookup.build_zip_lookup
```

This generates:

```text
resources/zip_lookup/us_zip_state_lookup.csv
resources/zip_lookup/build_report.txt
```

ZIP values are stored as text so leading zeros are preserved.

For example:

```text
06110
```

will remain `06110` rather than being converted to `6110`.

> **Note:** Census ZCTA data should only be used as a last resort. ZCTAs are Census geographic approximations and are not equivalent to USPS ZIP validation data.

### International Mail

International mail is intentionally routed to review:

```text
INTERNATIONAL_MAIL_REVIEW_REQUIRED
```

ListManager currently supports **US mailing formats only**.

## Build a Windows Executable

Install the package with the build dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[build]"
```

Then build the executable:

```powershell
.\venv\Scripts\pyinstaller.exe --clean --noconfirm listmanager_gui.spec
```

The packaged application will be generated in:

```text
dist/ListManager/
```

## Project Layout

```text
ListManager/
├── src/
│   └── listmanager/
│       ├── core/
│       │   ├── merge.py
│       │   ├── normalize.py
│       │   ├── validate.py
│       │   └── dbf_breakdown.py
│       │
│       ├── format_checker/
│       ├── zip_lookup/
│       ├── template_export/
│       ├── cli.py
│       └── gui.py
│
├── resources/
│   └── zip_lookup/
│       ├── source/
│       ├── us_zip_state_lookup.csv
│       └── build_report.txt
│
├── run_merge.py
├── requirements.txt
├── listmanager_gui.spec
└── ...
```

The core processing logic is separated from the GUI so that both the desktop application and CLI entry points share the same underlying functionality.

## Challenges & Lessons Learned

### Sourcing Offline ZIP Validation Data

Finding reliable ZIP validation data that could legally and practically be bundled with the application presented several challenges.

The official USPS City/State product is encrypted and non-exportable, while HUD crosswalk files exclude PO-Box-only ZIPs.

The project documents these tradeoffs and provides a rebuildable fallback system with:

* Source data documentation
* A lookup-generation script
* A generated lookup file
* A build report

### Preserving ZIP Leading Zeros

Spreadsheet applications frequently interpret ZIP codes as numeric values, which can corrupt codes such as:

```text
06110
```

ListManager explicitly stores ZIP values as text to preserve leading zeros throughout the processing pipeline.

### Separating Core Logic from the UI

All major processing functionality lives in the core package and is shared by the GUI and CLI entry points.

This allows the same validation and transformation logic to be used for:

* Interactive desktop workflows
* Repeatable scripted workflows
* Future automation

### Designing for Non-Technical Users

The GUI abstracts away many of the tedious and error-prone steps involved in preparing mailing lists.

Instead of requiring coworkers to understand the implementation details of normalization, validation, file merging, and template formatting, the application exposes those operations through a guided workflow.

## Future Improvements

* Automated tests for merge and validation rules
* Cross-platform packaging
* Continuous integration on push
* Expanded validation coverage
* Additional automated data-quality checks
* More robust configuration options for different mailing workflows

## License

TBD
