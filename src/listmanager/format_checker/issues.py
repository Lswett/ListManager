from __future__ import annotations

ERROR_MESSAGES = {
    "UNKNOWN_TARGET_FORMAT": "Could not detect COMPANY, FULLNAME, or FIRSTLAST target format.",
    "REQUIRED_COLUMNS_NOT_MAPPED": "One or more required columns could not be mapped from the source workbook.",
    "RECIPIENT_MISSING": "Recipient information is missing.",
    "COMPANY_MISSING": "Company is required for COMPANY format.",
    "FULLNAME_MISSING": "FullName is required for FULLNAME format.",
    "FIRST_NAME_MISSING": "First Name is required for FIRSTLAST format.",
    "LAST_NAME_MISSING": "Last Name is required for FIRSTLAST format.",
    "PRIMARY_ADDRESS_MISSING": "PrimaryAddress is required.",
    "CITY_MISSING": "City is required.",
    "ZIP_MISSING": "ZIP is required.",
    "ZIP_INVALID": "ZIP is invalid.",
    "ZIP_NOT_FOUND": "ZIP was not found in the local US ZIP lookup.",
    "STATE_MISSING": "State is required and could not be filled from ZIP.",
    "STATE_ZIP_MISMATCH": "State does not match the local ZIP lookup.",
    "INTERNATIONAL_MAIL_REVIEW_REQUIRED": (
        "International mail detected. Review manually before processing because this "
        "converter currently supports US mailing formats only."
    ),
}

ERROR_CODES = frozenset(ERROR_MESSAGES)

WARNING_CODES = frozenset(
    {
        "ZIP_PADDED",
        "ZIP4_SPLIT",
        "STATE_FILLED_FROM_ZIP",
        "STATE_NAME_CONVERTED",
        "NAME_SPLIT_LAST_FIRST",
        "COMPANY_FORMAT_AUTO_SELECTED",
        "COUNTRY_NORMALIZED_US",
        "DUPLICATE_POSSIBLE",
    }
)


def message_for(codes: list[str]) -> str:
    return " | ".join(ERROR_MESSAGES.get(code, code) for code in codes if code in ERROR_MESSAGES)
