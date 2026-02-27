from __future__ import annotations
import re
import pandas as pd

def clean_spaces(x: str) -> str:
    if x is None or pd.isna(x):   # <-- handles np.nan
        return ""
    s = "" if x is None else str(x)
    s = s.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()

def normalize_country(country: str, us_aliases: list[str]) -> tuple[str, bool]:
    c = clean_spaces(country).upper()
    if c == "":
        return "US", True
    if c in set(us_aliases):
        return "US", True
    return c, False

def parse_zip5(zip_raw: str) -> str:
    z = clean_spaces(zip_raw)
    digits = re.sub(r"\D", "", z)
    return digits[:5] if len(digits) >= 5 else ""

def canonicalize(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if df.empty:
        return df

    # Ensure expected columns exist
    needed = [
        "ATTN","Company","FullName","First Name","Last Name",
        "PrimaryAddress","Address2","City","State","Zip","Zip4","Country",
        "School","__Sheet","__SourceFile"
    ]
    for col in needed:
        if col not in df.columns:
            df[col] = ""

    # Clean whitespace everywhere
    for col in df.columns:
        df[col] = df[col].map(clean_spaces)

    # Country normalization + US flag
    us_aliases = cfg["country_us_aliases"]
    norm = df["Country"].map(lambda v: normalize_country(v, us_aliases))
    df["CountryNorm"] = [t[0] for t in norm]
    df["IsUS"] = [t[1] for t in norm]

    # Zip5 extraction
    df["Zip5"] = df["Zip"].map(parse_zip5)

    # Unique per-row ID for traceability
    # Deterministic numeric code per source file (<=10 digits, digits only)
    df = df.reset_index(drop=True)
    file_order = list(dict.fromkeys(df["__SourceFile"]))
    file_number = {src: idx for idx, src in enumerate(file_order, 1)}
    file_digits = len(str(len(file_order)))
    row_digits = 10 - file_digits
    if row_digits <= 0:
        raise ValueError("Too many files to generate <=10 digit UniqueFileIDs.")
    row_in_file = df.groupby("__SourceFile").cumcount() + 1
    max_rows = row_in_file.max()
    if max_rows >= 10 ** row_digits:
        raise ValueError("Too many rows in a single file to generate <=10 digit UniqueFileIDs.")
    df["UniqueFileID"] = [
        f"{file_number[src]:0{file_digits}d}{row:0{row_digits}d}"
        for src, row in zip(df["__SourceFile"], row_in_file)
    ]

    return df
