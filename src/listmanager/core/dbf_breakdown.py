from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

from dbfread import DBF


@dataclass
class BreakdownRow:
    value: str
    count: int
    percent: float


@dataclass
class ValidationResult:
    total_rows: int
    hard_stop_rows: List[int]
    review_rows: List[int]
    hard_stop_counts: Dict[str, int]
    review_counts: Dict[str, int]
    row_reasons: Dict[int, List[str]]
    hard_stop_rows_by_rule: Dict[str, List[int]]
    review_rows_by_rule: Dict[str, List[int]]

    @property
    def hard_stop_total(self) -> int:
        return len(self.hard_stop_rows)

    @property
    def review_total(self) -> int:
        return len(self.review_rows)


@dataclass
class DBFBreakdown:
    detected_column: str
    rows: List[BreakdownRow]
    barcode_missing: List[int]
    columns: List[str]
    headers: List[str]
    records: List[Dict[str, object]]
    validation: ValidationResult


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_blank(value) -> bool:
    return _clean_text(value) == ""


def _normalize_header_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", (name or "")).upper()


def _find_header(headers: List[str], field_name: str) -> str | None:
    target = _normalize_header_name(field_name)
    for header in headers:
        if _normalize_header_name(header) == target:
            return header
    return None


def _build_lookup(headers: List[str]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for name in headers:
        upper = name.upper()
        lookup[upper] = name
        normalized = _normalize_header_name(name)
        lookup.setdefault(normalized, name)
    return lookup


def _value(record: Mapping[str, object], lookup: Dict[str, str], field: str):
    key = lookup.get(field.upper()) or lookup.get(_normalize_header_name(field))
    if key is None:
        return None
    return record.get(key)


Rule = Tuple[str, callable, str, str, str]  # (id, checker, label, description, severity)


def _rule(rule_id: str, checker, label: str, description: str, severity: str) -> Rule:
    if not callable(checker):
        raise TypeError(f"Rule '{rule_id}' checker is not callable: {checker!r}")
    return (rule_id, checker, label, description, severity)


HARD_STOP_RULES: List[Rule] = [
    _rule(
        "missing_zip5",
        lambda r, l: (
            _is_blank(_value(r, l, "ZIP5"))
            or len(_clean_text(_value(r, l, "ZIP5"))) != 5
            or not _clean_text(_value(r, l, "ZIP5")).isdigit()
        ),
        "Missing ZIP5",
        "5-digit ZIP code is missing or invalid. USPS cannot sort mail without it.",
        "hard",
    ),
    _rule(
        "missing_imb",
        lambda r, l: _is_blank(_value(r, l, "IMB_ENCODE")),
        "Missing IMB",
        "Intelligent Mail barcode was not generated, risking automation rates.",
        "hard",
    ),
    _rule(
        "std_status_ndf",
        lambda r, l: _clean_text(_value(r, l, "STD_STATUS")).upper() in {"N", "D", "F"},
        "STD_STATUS N/D/F",
        "Address failed standardization (N), was deleted (D), or failed processing (F).",
        "hard",
    ),
    _rule(
        "dpv_flag_n",
        lambda r, l: _clean_text(_value(r, l, "DPV_FLAG")).upper() == "N",
        "DPV_FLAG=N",
        "DPV could not confirm the address as deliverable.",
        "hard",
    ),
    _rule(
        "dpv_flag_d",
        lambda r, l: _clean_text(_value(r, l, "DPV_FLAG")).upper() == "D",
        "DPV_FLAG=D",
        "Primary number missing or unconfirmed (DPV_FLAG D).",
        "hard",
    ),
    _rule(
        "coa_rtncod",
        lambda r, l: _clean_text(_value(r, l, "COA_RTNCOD")).upper() in {"02", "03"},
        "COA_RTNCOD 02/03",
        "Customer moved with no forwarding address (02) or closed PO box (03).",
        "hard",
    ),
]


REVIEW_RULES: List[Rule] = [
    _rule(
        "std_status_mu",
        lambda r, l: _clean_text(_value(r, l, "STD_STATUS")).upper() in {"M", "U"},
        "STD_STATUS M/U",
        "Address match uncertain: M (multiple matches) or U (unverified).",
        "review",
    ),
    _rule(
        "dpv_flag_s",
        lambda r, l: _clean_text(_value(r, l, "DPV_FLAG")).upper() == "S",
        "DPV_FLAG=S",
        "Secondary unit (e.g., apartment) likely missing.",
        "review",
    ),
    _rule(
        "dpv_vacant_y",
        lambda r, l: _clean_text(_value(r, l, "DPV_VACANT")).upper() == "Y",
        "DPV_VACANT=Y",
        "Address flagged as vacant.",
        "review",
    ),
    _rule(
        "zip41_blank",
        lambda r, l: _is_blank(_value(r, l, "ZIP41")),
        "Missing ZIP+4",
        "ZIP+4 (ZIP41) missing or blank; may impact automation rates.",
        "review",
    ),
    _rule(
        "dlvpnt_blank",
        lambda r, l: _is_blank(_value(r, l, "DLVPNT")),
        "Missing Delivery Point",
        "Delivery point (DLVPNT) missing; impacts barcode qualification.",
        "review",
    ),
    _rule(
        "dpv_ftnts",
        lambda r, l: not _is_blank(_value(r, l, "DPV_FTNTS")),
        "DPV_FTNTS present",
        "DPV notes indicate missing secondary/unit information.",
        "review",
    ),
]


RULE_INFO = {
    label: {"id": rule_id, "description": description, "severity": severity}
    for rule_id, _, label, description, severity in HARD_STOP_RULES + REVIEW_RULES
}

CLEAN_EXPORT_HEADERS: List[str] = [
    "UniqueFile",
    "School",
    "Company",
    "ATTN",
    "FullName",
    "FirstName",
    "LastName",
    "PrimaryAdd",
    "Address2",
    "City",
    "State",
    "Zip",
    "Zip4",
    "Zip5",
    "Country",
    "CountryNor",
    "SourceFile",
    "Sheet",
    "ErrorReaso",
    "IsUS",
]


def detect_group_column(record: Mapping[str, object]) -> str:
    """
    Determine the grouping column by checking the first non-empty string field
    from the provided record (typically the first DBF row).
    """
    for field, value in record.items():
        text = _clean_text(value)
        if text:
            return field
    return ""


def validate_records(records: List[Dict[str, object]], headers: List[str]) -> ValidationResult:
    lookup = _build_lookup(headers)
    hard_counts = {label: 0 for _, _, label, _, _ in HARD_STOP_RULES}
    review_counts = {label: 0 for _, _, label, _, _ in REVIEW_RULES}
    hard_rows: List[int] = []
    hard_rows_by_rule: Dict[str, List[int]] = {label: [] for _, _, label, _, _ in HARD_STOP_RULES}
    review_rows_by_rule: Dict[str, List[int]] = {label: [] for _, _, label, _, _ in REVIEW_RULES}
    review_rows: List[int] = []
    row_reasons: Dict[int, List[str]] = defaultdict(list)

    for idx, record in enumerate(records, start=1):
        hard_hit = False
        for rule_id, checker, label, _, _ in HARD_STOP_RULES:
            if not callable(checker):
                raise TypeError(f"Rule '{rule_id}' checker is not callable: {checker!r}")
            if checker(record, lookup):
                hard_counts[label] += 1
                row_reasons[idx].append(label)
                hard_rows_by_rule[label].append(idx)
                hard_hit = True
        if hard_hit:
            hard_rows.append(idx)
            continue

        review_hit = False
        for rule_id, checker, label, _, _ in REVIEW_RULES:
            if not callable(checker):
                raise TypeError(f"Rule '{rule_id}' checker is not callable: {checker!r}")
            if checker(record, lookup):
                review_counts[label] += 1
                row_reasons[idx].append(label)
                review_rows_by_rule[label].append(idx)
                review_hit = True
        if review_hit:
            review_rows.append(idx)

    return ValidationResult(
        total_rows=len(records),
        hard_stop_rows=hard_rows,
        review_rows=review_rows,
        hard_stop_counts=hard_counts,
        review_counts=review_counts,
        row_reasons=dict(row_reasons),
        hard_stop_rows_by_rule=hard_rows_by_rule,
        review_rows_by_rule=review_rows_by_rule,
    )


def analyze_dbf(path: str, preferred_column: str | None = None) -> DBFBreakdown:
    """
    Load the DBF, detect the grouping column, and compute counts/percentages.
    """
    dbf_path = Path(path)
    if not dbf_path.is_file():
        raise FileNotFoundError(f"DBF file not found: {dbf_path}")

    table = DBF(dbf_path, load=True)
    raw_records = list(table)
    if not raw_records:
        raise ValueError("DBF contains no records.")

    headers = list(table.field_names)
    records = [dict(row) for row in raw_records]
    validation = validate_records(records, headers)

    preferred_field = None
    if preferred_column:
        preferred_field = _find_header(headers, preferred_column)

    school_field = _find_header(headers, "SCHOOL")
    column = preferred_field or school_field or detect_group_column(records[0])
    if not column:
        raise ValueError("Unable to detect grouping column from the first record.")

    total = len(records)
    counts: dict[str, int] = {}
    for record in records:
        text = _clean_text(record.get(column))
        if not text:
            text = "(blank)"
        counts[text] = counts.get(text, 0) + 1

    rows = [
        BreakdownRow(value=value, count=count, percent=(count / total) * 100.0)
        for value, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]

    barcode_missing = []
    barcode_field = _find_header(headers, "BARCODE")
    if barcode_field:
        for idx, record in enumerate(records, start=1):
            text = _clean_text(record.get(barcode_field))
            if not text:
                barcode_missing.append(idx)

    return DBFBreakdown(
        detected_column=column,
        rows=rows,
        barcode_missing=barcode_missing,
        columns=list(headers),
        headers=headers,
        records=records,
        validation=validation,
    )


def list_dbf_columns(path: str) -> List[str]:
    dbf_path = Path(path)
    if not dbf_path.is_file():
        raise FileNotFoundError(f"DBF file not found: {dbf_path}")
    table = DBF(dbf_path, load=False)
    return list(table.field_names)


def split_dbf_by_column(path: str, outdir: Path, column_name: str = "SCHOOL") -> list[Path]:
    dbf_path = Path(path)
    if not dbf_path.is_file():
        raise FileNotFoundError(f"DBF file not found: {dbf_path}")

    table = DBF(dbf_path, load=True)
    raw_records = list(table)
    if not raw_records:
        raise ValueError("DBF contains no records.")

    headers = list(table.field_names)
    records = [dict(row) for row in raw_records]
    return export_records_by_column(records, headers, column_name, outdir)


def prepare_clean_export(
    records: List[Dict[str, object]],
    headers: List[str],
) -> Tuple[List[str], List[Dict[str, object]]]:
    """
    Build a clean-list dataset limited to the requested headers. Missing headers
    are created with blank values, and UniqueFile is renumbered sequentially.
    """
    target_headers = list(CLEAN_EXPORT_HEADERS)
    prepared: List[Dict[str, object]] = []
    for idx, record in enumerate(records, start=1):
        row: Dict[str, object] = {}
        for header in target_headers:
            source_field = _find_header(headers, header)
            row[header] = record.get(source_field, "") if source_field else ""
        row["UniqueFile"] = str(idx)
        prepared.append(row)
    return target_headers, prepared


def export_records_by_column(
    records: List[Dict[str, object]],
    headers: List[str],
    column_name: str,
    outdir: Path,
) -> list[Path]:
    column = _find_header(headers, column_name)
    if not column:
        raise ValueError(f"Column '{column_name}' not found.")

    unique_field = _find_header(headers, "UNIQUEFILE")
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    groups: Dict[str, List[Dict[str, object]]] = {}
    for record in records:
        value = _clean_text(record.get(column))
        if not value:
            value = "(blank)"
        groups.setdefault(value, []).append(record)

    def _safe_filename(value: str) -> str:
        slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
        return slug or "blank"

    written_files: List[Path] = []
    for value, rows in groups.items():
        filename = f"{column}_{_safe_filename(value)}.csv"
        dest = outdir / filename
        counter = 1
        while dest.exists():
            dest = outdir / f"{column}_{_safe_filename(value)}_{counter}.csv"
            counter += 1

        with dest.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for idx, record in enumerate(rows, start=1):
                row = {field: record.get(field, "") for field in headers}
                if unique_field and unique_field in row:
                    row[unique_field] = str(idx)
                writer.writerow(row)

        written_files.append(dest)

    return written_files


def create_clean_and_quarantine(
    records: List[Dict[str, object]],
    headers: List[str],
    validation: ValidationResult,
    selected_rules: List[str] | None = None,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], List[str]]:
    selected = set(selected_rules or [])
    if not selected:
        return list(records), [], headers

    clean_records: List[Dict[str, object]] = []
    quarantine_records: List[Dict[str, object]] = []
    for idx, record in enumerate(records, start=1):
        reasons = validation.row_reasons.get(idx, [])
        matched = [reason for reason in reasons if reason in selected]
        if matched:
            quarantined = dict(record)
            quarantined["ERROR_REASON"] = "; ".join(matched)
            quarantine_records.append(quarantined)
        else:
            clean_records.append(dict(record))

    headers_with_error = list(headers)
    if _find_header(headers_with_error, "ERROR_REASON") is None:
        headers_with_error.append("ERROR_REASON")

    return clean_records, quarantine_records, headers_with_error
