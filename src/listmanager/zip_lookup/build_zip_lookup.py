from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .lookup import normalize_zip
from .sources import (
    BUILD_REPORT,
    FEDERAL_GOVERNMENT_ZIPCODES_ARCHIVE,
    HUD_USPS_CROSSWALK,
    LOOKUP_CSV,
    SOURCE_DIR,
)

STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "PR", "VI", "GU", "AS", "MP", "FM", "MH", "PW", "AA",
    "AE", "AP",
}


def _norm_state(value: object) -> str:
    state = "" if value is None else str(value).strip().upper()
    return state if state in STATE_CODES else ""


def _read_csv(path: Path) -> tuple[list[dict[str, str]], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = {field.lower(): field for field in (reader.fieldnames or [])}

    if {"usps_zip_pref_city", "usps_zip_pref_state", "zip"}.issubset(fields):
        return (
            [
                {
                    "zip": row.get(fields["zip"], ""),
                    "state": row.get(fields["usps_zip_pref_state"], ""),
                    "city": row.get(fields["usps_zip_pref_city"], ""),
                    "source": HUD_USPS_CROSSWALK.name,
                }
                for row in rows
            ],
            HUD_USPS_CROSSWALK.name,
        )

    if {"zipcode", "city", "state"}.issubset(fields):
        return (
            [
                {
                    "zip": row.get(fields["zipcode"], ""),
                    "state": row.get(fields["state"], ""),
                    "city": row.get(fields["city"], ""),
                    "source": FEDERAL_GOVERNMENT_ZIPCODES_ARCHIVE.name,
                }
                for row in rows
            ],
            FEDERAL_GOVERNMENT_ZIPCODES_ARCHIVE.name,
        )

    if {"zip", "city", "state"}.issubset(fields):
        return (
            [
                {
                    "zip": row.get(fields["zip"], ""),
                    "state": row.get(fields["state"], ""),
                    "city": row.get(fields["city"], ""),
                    "source": path.name,
                }
                for row in rows
            ],
            path.name,
        )

    raise ValueError(f"Unsupported ZIP source columns in {path}: {', '.join(reader.fieldnames or [])}")


def _source_files(source_dir: Path) -> Iterable[Path]:
    return sorted(path for path in source_dir.glob("*.csv") if path.is_file())


def build_lookup(source_dir: Path = SOURCE_DIR, output_csv: Path = LOOKUP_CSV, report_path: Path = BUILD_REPORT) -> None:
    records: list[dict[str, str]] = []
    source_names: set[str] = set()
    skipped = 0

    files = list(_source_files(source_dir))
    if not files:
        raise FileNotFoundError(f"No CSV source files found under {source_dir}")

    for path in files:
        raw_rows, source_name = _read_csv(path)
        source_names.add(source_name)
        for row in raw_rows:
            zip5 = normalize_zip(row["zip"])
            state = _norm_state(row["state"])
            city = str(row.get("city") or "").strip().upper()
            if not zip5 or not state:
                skipped += 1
                continue
            records.append({"zip": zip5, "state": state, "city": city, "source": source_name})

    unique = sorted({(row["zip"], row["state"], row["city"], row["source"]) for row in records})
    output_rows = [
        {"zip": zip5, "state": state, "city": city, "source": source}
        for zip5, state, city, source in unique
    ]

    states_by_zip: dict[str, set[str]] = defaultdict(set)
    cities_by_zip: dict[str, set[str]] = defaultdict(set)
    for row in output_rows:
        states_by_zip[row["zip"]].add(row["state"])
        cities_by_zip[row["zip"]].add(row["city"])
    multi_state = {zip5: sorted(states) for zip5, states in states_by_zip.items() if len(states) > 1}

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["zip", "state", "city", "source"])
        writer.writeheader()
        writer.writerows(output_rows)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("US ZIP lookup build report\n")
        fh.write(f"Source directory: {source_dir}\n")
        fh.write(f"Source files: {', '.join(path.name for path in files)}\n")
        fh.write(f"Source names: {', '.join(sorted(source_names))}\n")
        fh.write(f"Rows written: {len(output_rows)}\n")
        fh.write(f"Distinct ZIPs: {len(states_by_zip)}\n")
        fh.write(f"Rows skipped: {skipped}\n")
        fh.write(f"ZIPs with city aliases: {sum(1 for cities in cities_by_zip.values() if len(cities) > 1)}\n")
        fh.write(f"ZIPs with multiple states: {len(multi_state)}\n")
        if multi_state:
            fh.write("\nMultiple-state ZIPs flagged for review:\n")
            for zip5, states in sorted(multi_state.items()):
                fh.write(f"{zip5}: {', '.join(states)}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the local US ZIP-to-state lookup CSV.")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=LOOKUP_CSV)
    parser.add_argument("--report", type=Path, default=BUILD_REPORT)
    args = parser.parse_args(argv)
    build_lookup(args.source_dir, args.output, args.report)


if __name__ == "__main__":
    main()
