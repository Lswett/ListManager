from __future__ import annotations
from pathlib import Path
import re
import pandas as pd

from typing import Iterable, Dict

from .io import read_input
from .normalize import canonicalize
from .validate import validate_rows

def _reorder_for_output(df: pd.DataFrame) -> pd.DataFrame:
    """
    Put the most useful columns first in outputs.
    Keeps everything else after.
    """
    priority = [
        "UniqueFileID", "School",
        "Company", "ATTN", "FullName", "First Name", "Last Name",
        "PrimaryAddress", "Address2", "City", "State",
        "Zip", "Zip4", "Zip5",
        "Country", "CountryNorm",
        "__SourceFile", "__Sheet",
        "IssueCodes",
        "ErrorReason"
    ]
    cols = [c for c in priority if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]

def _sanitize_column_names(columns: list[str]) -> list[str]:
    """
    Ensure column headers are <=10 alphanumeric characters with no spaces/special chars.
    """
    sanitized: list[str] = []
    used: set[str] = set()
    counts: dict[str, int] = {}

    for raw in columns:
        base = re.sub(r"[^0-9A-Za-z]", "", (raw or ""))
        if not base:
            base = "COL"

        counter = counts.get(base, 0)
        while True:
            suffix = "" if counter == 0 else str(counter)
            limit = 10 - len(suffix)
            if limit <= 0:
                raise ValueError(
                    "Unable to sanitize column headers to <=10 characters without duplicates."
                )
            trimmed = base[:limit]
            if not trimmed:
                trimmed = "COL"[:limit]
            candidate = f"{trimmed}{suffix}"
            if candidate not in used:
                used.add(candidate)
                sanitized.append(candidate)
                counts[base] = counter + 1
                break
            counter += 1

    return sanitized

def _prepare_for_export(df: pd.DataFrame) -> pd.DataFrame:
    df = _reorder_for_output(df)
    sanitized = _sanitize_column_names(list(df.columns))
    rename_map = dict(zip(df.columns, sanitized))
    return df.rename(columns=rename_map)

def merge_files(files: Iterable[str], outdir: Path, cfg: dict) -> Dict[str, int]:
    frames = []
    for path in files:
        df = read_input(path, cfg)
        if not df.empty:
            frames.append(df)

    if not frames:
        raise ValueError("No rows found in input files. Ensure they use the COMPANY/FULLNAME/FIRSTLAST tabs and data starts on the expected row.")

    combined = pd.concat(frames, ignore_index=True)

    # Normalize + add School/UniqueFileID/Zip5/CountryNorm/IsUS
    combined = canonicalize(combined, cfg)

    # Validate
    combined = validate_rows(combined)

    if combined.empty:
        raise ValueError("No rows found. Make sure you used the COMPANY/FULLNAME/FIRSTLAST tabs and pasted starting at row 8.")

    # Split 
    errors = combined[combined["ErrorReason"].ne("")].copy()
    ok = combined[combined["ErrorReason"].eq("")].copy()

    international = combined[
        combined["IssueCodes"].fillna("").astype(str).str.contains("INTERNATIONAL_MAIL_REVIEW_REQUIRED")
    ].copy()
    merged_us = ok[
        ok["IsUS"]
        & ~ok["IssueCodes"].fillna("").astype(str).str.contains("INTERNATIONAL_MAIL_REVIEW_REQUIRED")
    ].copy()

    # Reorder and sanitize column headers for readability/export constraints
    merged_us = _prepare_for_export(merged_us)
    international = _prepare_for_export(international)
    errors = _prepare_for_export(errors)

    # Output
    out = cfg["output"]
    merged_us.to_csv(outdir / out["merged_us"], index=False)
    international.to_csv(outdir / out["international"], index=False)
    errors.to_csv(outdir / out["errors"], index=False)

    summary = {
        "total": len(combined),
        "merged_us": len(merged_us),
        "international": len(international),
        "errors": len(errors),
    }

    print(
        f"Merged rows: {summary['total']}"
        f" | US OK: {summary['merged_us']}"
        f" | Intl: {summary['international']}"
        f" | Errors: {summary['errors']}"
    )
    return summary
