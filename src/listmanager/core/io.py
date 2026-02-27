from __future__ import annotations
import pandas as pd
from pathlib import Path
import re

def _clean_spaces(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()

def school_from_filename(filename: str) -> str:
    """
    Simple rule: use the file name (without extension) as the School label,
    cleaned for spaces. You can later add smarter extraction rules if needed.
    """
    stem = Path(filename).stem
    stem = stem.replace("_", " ").replace("-", " ")
    return _clean_spaces(stem)

def read_input(path: str, cfg: dict) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        df["__Sheet"] = "CSV"
        df["__SourceFile"] = p.name
        df["School"] = school_from_filename(p.name)
        return df

    if p.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return read_template_workbook(p, cfg)

    raise ValueError(f"Unsupported file type: {p.suffix}")

def read_template_workbook(path: Path, cfg: dict) -> pd.DataFrame:
    """
    Reads COMPANY/FULLNAME/FIRSTLAST sheets and stacks rows into a canonical dataframe.
    Assumes headers are on Excel row 4 (header=3) and real data begins at cfg['data_start_row'].
    """
    sheet_names = cfg["sheet_names"]
    start_row = int(cfg["data_start_row"])

    frames: list[pd.DataFrame] = []
    for s in sheet_names:
        try:
            df = pd.read_excel(path, sheet_name=s, dtype=str, keep_default_na=False, na_filter=False,header=3)
        except ValueError:
            continue  # sheet missing

        # Only read from start_row downward.
        # With header=3 (row 4 headers), the first df row corresponds to Excel row 5.
        excel_row_of_first_df_row = 5
        rows_to_skip = max(0, start_row - excel_row_of_first_df_row)
        if rows_to_skip:
            df = df.iloc[rows_to_skip:].copy()

        df["__Sheet"] = s
        df["__SourceFile"] = path.name
        df["School"] = school_from_filename(path.name)
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
