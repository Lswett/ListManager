from __future__ import annotations
import pandas as pd

# Output columns used by this module:
# - __Sheet, __SourceFile, UniqueFileID, School
# - Company, ATTN, FullName, First Name, Last Name
# - PrimaryAddress, Address2, City, State, Zip, Zip4, Country
# - IsUS, Zip5
# - ErrorReason

def _has_any_text(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().ne("")

def compute_identity_error(df: pd.DataFrame) -> pd.Series:
    """
    Enforce identity based on which template sheet the row came from:

      COMPANY:
        - Company required
        - ATTN optional
        - FullName/First/Last must be blank

      FULLNAME:
        - FullName required
        - Company/ATTN/First/Last must be blank

      FIRSTLAST:
        - First Name and Last Name required
        - Company/ATTN/FullName must be blank

    Also catches "mixed identity fields" if users paste into wrong columns.
    """
    sheet = df["__Sheet"].fillna("").astype(str).str.upper()

    is_company_sheet = sheet.eq("COMPANY")
    is_fullname_sheet = sheet.eq("FULLNAME")
    is_firstlast_sheet = sheet.eq("FIRSTLAST")

    # Missing required identity field(s) for each sheet
    missing_company = is_company_sheet & df["Company"].fillna("").astype(str).str.strip().eq("")
    missing_fullname = is_fullname_sheet & df["FullName"].fillna("").astype(str).str.strip().eq("")
    missing_firstlast = is_firstlast_sheet & (
        df["First Name"].fillna("").astype(str).str.strip().eq("") |
        df["Last Name"].fillna("").astype(str).str.strip().eq("")
    )

    # Mixed identity fields (shouldn't happen if they use the right tab, but people…)
    has_company = _has_any_text(df["Company"])
    has_attn = _has_any_text(df["ATTN"])
    has_fullname = _has_any_text(df["FullName"])
    has_first = _has_any_text(df["First Name"])
    has_last = _has_any_text(df["Last Name"])

    # Company cannot be combined with person name fields
    mixed_company_person = has_company & (has_fullname | has_first | has_last)

    # FullName cannot be combined with First/Last (pick one method)
    mixed_fullname_firstlast = has_fullname & (has_first | has_last)

    # ATTN should only appear with Company (allowed to be blank)
    attn_without_company = has_attn & (~has_company)

    # On COMPANY sheet, enforce person fields blank
    company_sheet_person_filled = is_company_sheet & (has_fullname | has_first | has_last)

    # On FULLNAME sheet, enforce Company/ATTN/First/Last blank
    fullname_sheet_other_filled = is_fullname_sheet & (has_company | has_attn | has_first | has_last)

    # On FIRSTLAST sheet, enforce Company/ATTN/FullName blank
    firstlast_sheet_other_filled = is_firstlast_sheet & (has_company | has_attn | has_fullname)

    return (
        missing_company |
        missing_fullname |
        missing_firstlast |
        mixed_company_person |
        mixed_fullname_firstlast |
        attn_without_company |
        company_sheet_person_filled |
        fullname_sheet_other_filled |
        firstlast_sheet_other_filled
    )

def validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds ErrorReason (string). If ErrorReason is non-empty -> row is an error row.

    Rules:
      - Address required on ALL sheets: PrimaryAddress, City, State, Zip
      - Identity rules enforced per sheet (COMPANY/FULLNAME/FIRSTLAST)
      - For US rows (Country blank => US): Zip must yield a 5-digit Zip5
      - For Intl rows: Country must be explicitly provided (not blank)
    """
    if df.empty:
        df["ErrorReason"] = ""
        return df

    # Ensure column exists
    if "ErrorReason" not in df.columns:
        df["ErrorReason"] = ""

    # Required address fields
    missing_addr = (
        df["PrimaryAddress"].astype(str).str.strip().eq("") |
        df["City"].astype(str).str.strip().eq("") |
        df["State"].astype(str).str.strip().eq("") |
        df["Zip"].astype(str).str.strip().eq("")
    )

    # Identity errors
    id_err = compute_identity_error(df)

    # US ZIP requirement
    bad_us_zip = df["IsUS"].fillna(False) & df["Zip5"].astype(str).str.strip().eq("")

    # Intl must provide Country explicitly
    intl_missing_country = (~df["IsUS"].fillna(True)) & df["Country"].astype(str).str.strip().eq("")

    # Build reasons (accumulate)
    df["ErrorReason"] = ""

    def add_reason(mask: pd.Series, reason: str):
        nonlocal df
        # If empty, set; else append
        empty = df["ErrorReason"].eq("")
        df.loc[mask & empty, "ErrorReason"] = reason
        df.loc[mask & ~empty, "ErrorReason"] = df.loc[mask & ~empty, "ErrorReason"] + " | " + reason

    add_reason(missing_addr, "Missing address field(s) (PrimaryAddress/City/State/Zip)")
    add_reason(id_err, "Invalid recipient identity (wrong tab or mixed fields)")
    add_reason(bad_us_zip, "Invalid US ZIP (needs 5 digits)")
    add_reason(intl_missing_country, "International address missing Country")

    return df
