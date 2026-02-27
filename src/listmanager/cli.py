from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

from listmanager.config import build_config
from listmanager.core.merge import merge_files

SUPPORTED_EXTS = {".csv", ".xlsx", ".xlsm", ".xls"}


def _gather_input_files(inputdir: Path) -> List[str]:
    files = [
        str(p)
        for p in sorted(inputdir.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    if not files:
        raise FileNotFoundError(f"No CSV/Excel files found in {inputdir}")
    return files


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Merge mailing list spreadsheets/CSVs.")
    ap.add_argument(
        "--inputdir",
        default="ListInput",
        help="Directory containing .xlsx/.xls/.xlsm/.csv inputs (default: ListInput)",
    )
    ap.add_argument("--outdir", required=True, help="Output folder")
    ap.add_argument(
        "--start-row",
        type=int,
        default=8,
        help="Row number where data begins (default: 8)",
    )
    args = ap.parse_args(argv)

    cfg = build_config(args.start_row)
    inputdir = Path(args.inputdir)
    if not inputdir.is_dir():
        raise NotADirectoryError(f"Input directory not found: {inputdir}")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    input_files = _gather_input_files(inputdir)
    merge_files(input_files, outdir, cfg)


if __name__ == "__main__":
    main()
