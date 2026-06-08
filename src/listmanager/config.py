from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "sheet_names": ["COMPANY", "FULLNAME", "FIRSTLAST"],
    "data_start_row": 8,
    "country_us_aliases": [
        "US",
        "USA",
        "U.S.",
        "U.S.A.",
        "UNITED STATES",
        "UNITED STATES OF AMERICA",
    ],
    "output": {
        "merged_us": "merged_us.csv",
        "international": "international.csv",
        "errors": "errors.csv",
    },
}


def build_config(data_start_row: int) -> Dict[str, Any]:
    """Return a deep-copied config dict with the provided start row applied."""
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["data_start_row"] = int(data_start_row)
    return cfg


__all__ = ["DEFAULT_CONFIG", "build_config"]
