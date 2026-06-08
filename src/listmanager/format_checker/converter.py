from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .exporter import write_converted_workbook
from .issues import ERROR_CODES, message_for
from .mapper import CONTACT_FIELDS, TARGET_COLUMNS, missing_mapped_fields
from .normalizer import (
    apply_zip_state_validation,
    clean_text,
    normalize_country,
    normalize_state,
    normalize_zip_parts,
    split_last_first,
)
from .scanner import WorkbookScan, scan_workbook as _scan_workbook


@dataclass(frozen=True)
class ConversionResult:
    source_path: Path
    output_path: Path | None
    detected_format: str
    rows_scanned: int
    rows_converted: int
    rows_needing_review: int
    warning_count: int
    error_count: int
    issue_counts: dict[str, int]


def _value(values: list[object], idx: int | None) -> object:
    if idx is None or idx >= len(values):
        return ""
    return values[idx]


def _append_unique(target: list[str], code: str) -> None:
    if code not in target:
        target.append(code)


def _mapped_row(scan: WorkbookScan, source_values: list[object], warnings: list[str]) -> dict[str, str]:
    row = {
        "Company": "",
        "ATTN": "",
        "FullName": "",
        "First Name": "",
        "Last Name": "",
        "PrimaryAddress": "",
        "Address2": "",
        "City": "",
        "State": "",
        "Zip": "",
        "Zip4": "",
        "Country": "",
    }

    if scan.headerless:
        first, last = split_last_first(_value(source_values, 0))
        row["First Name"] = first
        row["Last Name"] = last
        row["PrimaryAddress"] = clean_text(_value(source_values, 2))
        row["City"] = clean_text(_value(source_values, 3))
        row["Zip"] = clean_text(_value(source_values, 4))
        _append_unique(warnings, "NAME_SPLIT_LAST_FIRST")
        return row

    for field, idx in scan.field_map.items():
        row[field] = clean_text(_value(source_values, idx))

    if scan.target_format == "COMPANY":
        if row["FullName"]:
            row["ATTN"] = row["FullName"]
        elif row["First Name"] or row["Last Name"]:
            row["ATTN"] = clean_text(f"{row['First Name']} {row['Last Name']}")
        for field in CONTACT_FIELDS:
            row[field] = row[field] if field == "FullName" else row[field]
    return row


def _normalize_row(row: dict[str, str], errors: list[str], warnings: list[str]) -> None:
    row["Country"] = normalize_country(row.get("Country", ""), warnings)
    row["State"] = normalize_state(row.get("State", ""), warnings)
    zip_value, zip4 = normalize_zip_parts(row.get("Zip", ""), row["Country"], errors, warnings)
    row["Zip"] = zip_value
    if zip4 and not row.get("Zip4"):
        row["Zip4"] = zip4
    apply_zip_state_validation(row, errors, warnings)


def _required_errors(target_format: str, row: dict[str, str], errors: list[str]) -> None:
    if target_format == "UNKNOWN":
        _append_unique(errors, "UNKNOWN_TARGET_FORMAT")
        return
    if not any(row.get(field, "") for field in ("Company", "FullName", "First Name", "Last Name")):
        _append_unique(errors, "RECIPIENT_MISSING")
    if target_format == "COMPANY" and not row.get("Company"):
        _append_unique(errors, "COMPANY_MISSING")
    if target_format == "FULLNAME" and not row.get("FullName"):
        _append_unique(errors, "FULLNAME_MISSING")
    if target_format == "FIRSTLAST":
        if not row.get("First Name"):
            _append_unique(errors, "FIRST_NAME_MISSING")
        if not row.get("Last Name"):
            _append_unique(errors, "LAST_NAME_MISSING")
    if not row.get("PrimaryAddress"):
        _append_unique(errors, "PRIMARY_ADDRESS_MISSING")
    if not row.get("City"):
        _append_unique(errors, "CITY_MISSING")
    if not row.get("Zip"):
        _append_unique(errors, "ZIP_MISSING")
    if not row.get("State") and "INTERNATIONAL_MAIL_REVIEW_REQUIRED" not in errors:
        _append_unique(errors, "STATE_MISSING")


def _review_row(
    scan: WorkbookScan,
    source_row_number: int,
    row: dict[str, str],
    errors: list[str],
    original: dict[str, object],
) -> dict[str, object]:
    review = {
        "Source File": scan.source_path.name,
        "Source Sheet": scan.sheet_name,
        "Source Row": source_row_number,
        "Target Format": scan.target_format,
        "Error Codes": " | ".join(errors),
        "Error Message": message_for(errors),
        **row,
    }
    for header, value in original.items():
        review[f"ORIGINAL: {header}"] = value
    return review


def _output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}_converted.xlsx"


def scan_workbook(input_path: Path, output_dir: Path | None = None) -> ConversionResult:
    scan = _scan_workbook(Path(input_path))
    issue_counts = Counter(scan.warnings)
    if scan.target_format == "UNKNOWN":
        issue_counts["UNKNOWN_TARGET_FORMAT"] = len(scan.rows)
    return ConversionResult(
        source_path=Path(input_path),
        output_path=_output_path(Path(input_path), output_dir) if output_dir else None,
        detected_format=scan.target_format,
        rows_scanned=len(scan.rows),
        rows_converted=0,
        rows_needing_review=0,
        warning_count=sum(issue_counts[code] for code in issue_counts if code not in ERROR_CODES),
        error_count=sum(issue_counts[code] for code in issue_counts if code in ERROR_CODES),
        issue_counts=dict(issue_counts),
    )


def convert_workbook(input_path: Path, output_dir: Path) -> ConversionResult:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    scan = _scan_workbook(input_path)
    target_format = scan.target_format
    output_path = _output_path(input_path, output_dir)
    main_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    issue_counts: Counter[str] = Counter(scan.warnings)
    missing_fields = missing_mapped_fields(target_format, scan.field_map)

    for source_row in scan.rows:
        errors: list[str] = []
        warnings = list(scan.warnings)
        row = _mapped_row(scan, source_row.values, warnings)

        if target_format == "UNKNOWN":
            _append_unique(errors, "UNKNOWN_TARGET_FORMAT")
        if missing_fields:
            _append_unique(errors, "REQUIRED_COLUMNS_NOT_MAPPED")

        _normalize_row(row, errors, warnings)
        _required_errors(target_format, row, errors)

        for code in warnings:
            issue_counts[code] += 1
        for code in errors:
            issue_counts[code] += 1

        if errors:
            review_rows.append(_review_row(scan, source_row.source_row, row, errors, source_row.original))
        else:
            main_rows.append({field: row.get(field, "") for field in TARGET_COLUMNS[target_format]})

    report_rows = [
        ("Source file name", input_path.name),
        ("Source sheet used", scan.sheet_name),
        ("Detected target format", target_format),
        ("Rows scanned", len(scan.rows)),
        ("Rows converted to main sheet", len(main_rows)),
        ("Rows moved to NEEDS_REVIEW", len(review_rows)),
        ("Warning count", sum(count for code, count in issue_counts.items() if code not in ERROR_CODES)),
        ("Error count", sum(count for code, count in issue_counts.items() if code in ERROR_CODES)),
        ("Counts by issue code", "; ".join(f"{code}: {count}" for code, count in sorted(issue_counts.items()))),
        ("Duplicates", "Duplicates were not removed during this stage."),
    ]
    for assumption in scan.assumptions:
        report_rows.append(("Assumption", assumption))

    write_converted_workbook(output_path, target_format, main_rows, review_rows, report_rows, scan.headers)

    return ConversionResult(
        source_path=input_path,
        output_path=output_path,
        detected_format=target_format,
        rows_scanned=len(scan.rows),
        rows_converted=len(main_rows),
        rows_needing_review=len(review_rows),
        warning_count=sum(count for code, count in issue_counts.items() if code not in ERROR_CODES),
        error_count=sum(count for code, count in issue_counts.items() if code in ERROR_CODES),
        issue_counts=dict(issue_counts),
    )


def _input_files(input_path: Path) -> list[Path]:
    input_path = Path(input_path)
    if input_path.is_dir():
        return sorted(
            path for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() in {".xlsx", ".xlsm"}
        )
    return [input_path]


def convert_many(input_paths: list[Path], output_dir: Path) -> list[ConversionResult]:
    files: list[Path] = []
    for input_path in input_paths:
        files.extend(_input_files(Path(input_path)))
    return [convert_workbook(path, output_dir) for path in files]


def scan_many(input_paths: list[Path], output_dir: Path | None = None) -> list[ConversionResult]:
    files: list[Path] = []
    for input_path in input_paths:
        files.extend(_input_files(Path(input_path)))
    return [scan_workbook(path, output_dir) for path in files]
