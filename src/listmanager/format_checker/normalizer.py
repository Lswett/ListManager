from __future__ import annotations

import re

from listmanager.zip_lookup import get_state_for_zip, is_us_zip, normalize_zip
from listmanager.zip_lookup.build_zip_lookup import STATE_CODES

US_COUNTRY_VALUES = {"", "US", "USA", "U.S.", "U.S.A.", "UNITED STATES", "UNITED STATES OF AMERICA"}
INTERNATIONAL_COUNTRIES = {
    "CANADA", "CA", "MEXICO", "MX", "UNITED KINGDOM", "UK", "ENGLAND", "FRANCE",
    "GERMANY", "CHINA", "INDIA", "JAPAN", "AUSTRALIA", "ITALY", "SPAIN",
}
CANADIAN_POSTAL_RE = re.compile(r"^[A-Z]\d[A-Z][ -]?\d[A-Z]\d$", re.IGNORECASE)

STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "PUERTO RICO": "PR", "GUAM": "GU",
    "VIRGIN ISLANDS": "VI",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ")
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return re.sub(r"\s+", " ", text).strip()


def split_last_first(value: object) -> tuple[str, str]:
    text = clean_text(value)
    if "," not in text:
        return "", ""
    last, first = text.split(",", 1)
    first = clean_text(first).split(" ")[0] if clean_text(first) else ""
    return clean_text(first), clean_text(last)


def normalize_zip_parts(value: object, country: str, errors: list[str], warnings: list[str]) -> tuple[str, str]:
    raw = clean_text(value)
    country_key = clean_text(country).upper()
    if country_key and country_key not in US_COUNTRY_VALUES:
        return raw, ""
    if not raw:
        return "", ""
    if CANADIAN_POSTAL_RE.match(raw):
        return raw, ""

    if "-" in raw:
        left, right = raw.split("-", 1)
        zip5 = normalize_zip(left)
        zip4_digits = re.sub(r"\D", "", right)[:4]
        if zip5 and len(zip4_digits) == 4:
            warnings.append("ZIP4_SPLIT")
            return zip5, zip4_digits

    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 4:
        warnings.append("ZIP_PADDED")
        return digits.zfill(5), ""
    if len(digits) == 5:
        return digits, ""
    if len(digits) == 9:
        warnings.append("ZIP4_SPLIT")
        return digits[:5], digits[5:9]
    return raw, ""


def normalize_state(value: object, warnings: list[str]) -> str:
    state = clean_text(value).upper()
    if state in STATE_CODES:
        return state
    converted = STATE_NAMES.get(state)
    if converted:
        warnings.append("STATE_NAME_CONVERTED")
        return converted
    return state


def normalize_country(value: object, warnings: list[str]) -> str:
    country = clean_text(value)
    if not country:
        return ""
    if country.upper() in US_COUNTRY_VALUES:
        warnings.append("COUNTRY_NORMALIZED_US")
        return "US"
    return country


def is_international(country: str, zip_value: str, state: str) -> bool:
    country_key = clean_text(country).upper()
    if country_key and country_key not in US_COUNTRY_VALUES:
        return True
    if country_key in INTERNATIONAL_COUNTRIES and country_key not in US_COUNTRY_VALUES:
        return True
    if CANADIAN_POSTAL_RE.match(clean_text(zip_value)):
        return True
    zip5 = normalize_zip(zip_value)
    if state and state.upper() not in STATE_CODES and not (zip5 and is_us_zip(zip5)):
        return True
    if not zip5 and re.search(r"[A-Za-z]", clean_text(zip_value)):
        return True
    return False


def apply_zip_state_validation(row: dict[str, str], errors: list[str], warnings: list[str]) -> None:
    if is_international(row.get("Country", ""), row.get("Zip", ""), row.get("State", "")):
        errors.append("INTERNATIONAL_MAIL_REVIEW_REQUIRED")
        return

    zip5 = normalize_zip(row.get("Zip", ""))
    if not row.get("Zip"):
        errors.append("ZIP_MISSING")
        return
    if not zip5:
        errors.append("ZIP_INVALID")
        return
    row["Zip"] = zip5
    if not is_us_zip(zip5):
        errors.append("ZIP_NOT_FOUND")
        return

    expected_state = get_state_for_zip(zip5) or ""
    if not row.get("State") and expected_state:
        row["State"] = expected_state
        warnings.append("STATE_FILLED_FROM_ZIP")
    elif row.get("State") and expected_state and row["State"].upper() != expected_state:
        errors.append("STATE_ZIP_MISMATCH")

    if not row.get("State"):
        errors.append("STATE_MISSING")
