from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ZIP_LOOKUP_MISSING_MESSAGE = (
    "US ZIP lookup file is missing. Run the ZIP lookup build step or add the "
    "dataset under resources/zip_lookup/."
)

_ZIP_RE = re.compile(r"^\s*(\d{5})(?:[-\s]?\d{4})?\s*$")


@dataclass(frozen=True)
class ZipLookup:
    rows: tuple[dict[str, str], ...]
    states_by_zip: dict[str, frozenset[str]]

    def state_for_zip(self, zip_value: object) -> str | None:
        zip5 = normalize_zip(zip_value)
        if not zip5:
            return None
        states = self.states_by_zip.get(zip5, frozenset())
        if len(states) == 1:
            return next(iter(states))
        return None


def normalize_zip(zip_value: object) -> str:
    if zip_value is None:
        return ""
    text = str(zip_value).strip()
    if not text:
        return ""
    match = _ZIP_RE.match(text)
    if match:
        return match.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) == 5:
        return digits
    if len(digits) == 9 and re.fullmatch(r"\D*\d{5}\D*\d{4}\D*", text):
        return digits[:5]
    return ""


def _resource_candidates(path: str | Path | None) -> Iterable[Path]:
    if path is not None:
        yield Path(path)
        return

    relative = Path("resources") / "zip_lookup" / "us_zip_state_lookup.csv"
    yield Path.cwd() / relative
    yield Path(__file__).resolve().parents[3] / relative

    if hasattr(sys, "_MEIPASS"):
        yield Path(getattr(sys, "_MEIPASS")) / relative


@lru_cache(maxsize=4)
def load_zip_lookup(path: str | Path | None = None) -> ZipLookup:
    selected = next((candidate for candidate in _resource_candidates(path) if candidate.is_file()), None)
    if selected is None:
        raise FileNotFoundError(ZIP_LOOKUP_MISSING_MESSAGE)

    rows: list[dict[str, str]] = []
    states_by_zip: dict[str, set[str]] = {}
    with selected.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"zip", "state", "city", "source"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"ZIP lookup file is missing required column(s): {', '.join(sorted(missing))}")
        for row in reader:
            zip5 = normalize_zip(row.get("zip", ""))
            state = (row.get("state") or "").strip().upper()
            if not zip5 or len(state) != 2:
                continue
            clean_row = {key: (value or "").strip() for key, value in row.items()}
            clean_row["zip"] = zip5
            clean_row["state"] = state
            rows.append(clean_row)
            states_by_zip.setdefault(zip5, set()).add(state)

    return ZipLookup(
        rows=tuple(rows),
        states_by_zip={zip5: frozenset(states) for zip5, states in states_by_zip.items()},
    )


def get_state_for_zip(zip_value: object, lookup: ZipLookup | None = None) -> str | None:
    return (lookup or load_zip_lookup()).state_for_zip(zip_value)


def is_us_zip(zip_value: object, lookup: ZipLookup | None = None) -> bool:
    zip5 = normalize_zip(zip_value)
    return bool(zip5 and zip5 in (lookup or load_zip_lookup()).states_by_zip)


def validate_zip_state(zip_value: object, state_value: object, lookup: ZipLookup | None = None) -> bool:
    expected = get_state_for_zip(zip_value, lookup)
    state = "" if state_value is None else str(state_value).strip().upper()
    return bool(expected and state == expected)
