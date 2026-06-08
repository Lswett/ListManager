from __future__ import annotations
import re
import pandas as pd

from listmanager.zip_lookup import ZIP_LOOKUP_MISSING_MESSAGE, load_zip_lookup
from listmanager.zip_lookup.build_zip_lookup import STATE_CODES

# Output columns used by this module:
# - __Sheet, __SourceFile, UniqueFileID, School
# - Company, ATTN, FullName, First Name, Last Name
# - PrimaryAddress, Address2, City, State, Zip, Zip4, Country
# - IsUS, Zip5
# - ErrorReason

def _has_any_text(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().ne("")

INTERNATIONAL_MAIL_MESSAGE = (
    "International mail detected. Review manually before processing because this "
    "converter currently supports US mailing formats only."
)

_COUNTRY_US_VALUES = {"", "US", "USA", "U.S.", "U.S.A.", "UNITED STATES", "UNITED STATES OF AMERICA"}
_INTERNATIONAL_COUNTRIES = {
    "CANADA", "CA", "MEXICO", "MX", "UNITED KINGDOM", "UK", "ENGLAND", "FRANCE",
    "GERMANY", "CHINA", "INDIA", "JAPAN", "AUSTRALIA", "ITALY", "SPAIN",
}
_CANADIAN_POSTAL_RE = re.compile(r"^[A-Z]\d[A-Z][ -]?\d[A-Z]\d$", re.IGNORECASE)


def _append_text(existing: str, value: str) -> str:
    if not existing:
        return value
    if value in [part.strip() for part in existing.split("|")]:
        return existing
    return f"{existing} | {value}"


def _normalize_state(value: object) -> str:
    return "" if value is None else str(value).strip().upper()


def _country_text(value: object) -> str:
    return "" if value is None else str(value).strip().upper()


def _looks_international(row: pd.Series, zip_found: bool) -> bool:
    country = _country_text(row.get("CountryNorm", row.get("Country", "")))
    raw_country = _country_text(row.get("Country", ""))
    postal = "" if row.get("Zip") is None else str(row.get("Zip")).strip()
    state = _normalize_state(row.get("State", ""))

    if country and country not in _COUNTRY_US_VALUES:
        return True
    if raw_country in _INTERNATIONAL_COUNTRIES and raw_country not in _COUNTRY_US_VALUES:
        return True
    if _CANADIAN_POSTAL_RE.match(postal):
        return True
    if raw_country == "" and not zip_found and state and state not in STATE_CODES:
        return True
    if country == "US" and raw_country == "" and not zip_found and re.search(r"[A-Za-z]", postal):
        return True
    return False

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

    # Ensure columns exist
    if "ErrorReason" not in df.columns:
        df["ErrorReason"] = ""
    if "IssueCodes" not in df.columns:
        df["IssueCodes"] = ""

    try:
        zip_lookup = load_zip_lookup()
    except FileNotFoundError as exc:
        df["IssueCodes"] = df["IssueCodes"].map(lambda value: _append_text(str(value), "ZIP_LOOKUP_FILE_MISSING"))
        df["ErrorReason"] = ZIP_LOOKUP_MISSING_MESSAGE
        raise FileNotFoundError(ZIP_LOOKUP_MISSING_MESSAGE) from exc

    expected_states = []
    zip_found_values = []
    for zip5 in df["Zip5"]:
        states = zip_lookup.states_by_zip.get(str(zip5), frozenset()) if zip5 else frozenset()
        zip_found_values.append(bool(states))
        expected_states.append(next(iter(states)) if len(states) == 1 else "")
    df["_ExpectedZipState"] = expected_states
    df["_ZipFound"] = zip_found_values

    international = df.apply(lambda row: _looks_international(row, bool(row["_ZipFound"])), axis=1)

    fill_state = (
        ~international
        & df["State"].astype(str).str.strip().eq("")
        & df["_ExpectedZipState"].astype(str).str.strip().ne("")
    )
    df.loc[fill_state, "State"] = df.loc[fill_state, "_ExpectedZipState"]
    df.loc[fill_state, "IssueCodes"] = df.loc[fill_state, "IssueCodes"].map(
        lambda value: _append_text(str(value), "STATE_FILLED_FROM_ZIP")
    )

    state_present = df["State"].astype(str).str.strip().ne("")
    state_mismatch = (
        ~international
        & state_present
        & df["_ExpectedZipState"].astype(str).str.strip().ne("")
        & (df["State"].map(_normalize_state) != df["_ExpectedZipState"])
    )
    zip_invalid = ~international & df["Zip5"].astype(str).str.strip().eq("")
    zip_not_found = ~international & ~zip_invalid & ~df["_ZipFound"].fillna(False)

    # Required address fields after any state fill.
    missing_addr = (
        df["PrimaryAddress"].astype(str).str.strip().eq("") |
        df["City"].astype(str).str.strip().eq("") |
        df["State"].astype(str).str.strip().eq("") |
        df["Zip"].astype(str).str.strip().eq("")
    )

    # Identity errors
    id_err = compute_identity_error(df)

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
    add_reason(zip_invalid, "ZIP_INVALID")
    add_reason(zip_not_found, "ZIP_NOT_FOUND")
    add_reason(state_mismatch, "STATE_ZIP_MISMATCH")
    add_reason(international, INTERNATIONAL_MAIL_MESSAGE)

    issue_masks = [
        (zip_invalid, "ZIP_INVALID"),
        (zip_not_found, "ZIP_NOT_FOUND"),
        (state_mismatch, "STATE_ZIP_MISMATCH"),
        (international, "INTERNATIONAL_MAIL_REVIEW_REQUIRED"),
    ]
    for mask, code in issue_masks:
        df.loc[mask, "IssueCodes"] = df.loc[mask, "IssueCodes"].map(lambda value, c=code: _append_text(str(value), c))

    return df.drop(columns=["_ExpectedZipState", "_ZipFound"], errors="ignore")
