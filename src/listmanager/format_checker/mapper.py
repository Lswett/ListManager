from __future__ import annotations

import re

TARGET_COLUMNS = {
    "COMPANY": ["Company", "ATTN", "PrimaryAddress", "Address2", "City", "State", "Zip", "Zip4", "Country"],
    "FULLNAME": ["FullName", "PrimaryAddress", "Address2", "City", "State", "Zip", "Zip4", "Country"],
    "FIRSTLAST": ["First Name", "Last Name", "PrimaryAddress", "Address2", "City", "State", "Zip", "Zip4", "Country"],
}

REVIEW_COLUMNS = [
    "Source File",
    "Source Sheet",
    "Source Row",
    "Target Format",
    "Error Codes",
    "Error Message",
    "Company",
    "ATTN",
    "FullName",
    "First Name",
    "Last Name",
    "PrimaryAddress",
    "Address2",
    "City",
    "State",
    "Zip",
    "Zip4",
    "Country",
]

COMPANY_SYNONYMS = {
    "company", "companyname", "organization", "organizationname", "business",
    "businessname", "school", "schoolname", "district", "department", "agency",
    "employer", "institution", "program",
}

FIELD_SYNONYMS = {
    "Company": COMPANY_SYNONYMS,
    "FullName": {"fullname", "name", "studentname", "studentsname", "recipientname"},
    "First Name": {"firstname", "first", "givenname"},
    "Last Name": {"lastname", "last", "surname", "familyname"},
    "PrimaryAddress": {
        "address", "street", "streetaddress", "mailingstreet", "mailingaddress",
        "addressline1", "a1streetline1", "address1", "primaryaddress",
    },
    "Address2": {
        "address2", "addressline2", "mailingstreet2", "a1streetline2", "suite",
        "unit", "apartment", "apt",
    },
    "City": {"city", "mailingcity", "a1city"},
    "State": {"state", "statecode", "mailingstateprovince", "mailingstate", "a1statecode", "province"},
    "Zip": {"zip", "zipcode", "postalcode", "mailingzippostalcode", "a1zip", "zippostalcode"},
    "Country": {"country", "nation"},
}

CONTACT_FIELDS = ("FullName", "First Name", "Last Name")


def normalize_header(value: object) -> str:
    text = "" if value is None else str(value).strip().lower()
    text = text.replace("'", "")
    return re.sub(r"[^a-z0-9]", "", text)


def map_headers(headers: list[object]) -> dict[str, int]:
    field_map: dict[str, int] = {}
    normalized = [normalize_header(header) for header in headers]
    for idx, header_key in enumerate(normalized):
        if not header_key:
            continue
        for field, synonyms in FIELD_SYNONYMS.items():
            if header_key in synonyms and field not in field_map:
                field_map[field] = idx
    return field_map


def header_score(headers: list[object]) -> int:
    return len(map_headers(headers))


def detect_target_format(field_map: dict[str, int], headerless: bool = False) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if headerless:
        return "FIRSTLAST", warnings
    if "Company" in field_map:
        warnings.append("COMPANY_FORMAT_AUTO_SELECTED")
        return "COMPANY", warnings
    if "First Name" in field_map and "Last Name" in field_map:
        return "FIRSTLAST", warnings
    if "FullName" in field_map:
        return "FULLNAME", warnings
    return "UNKNOWN", []


def missing_mapped_fields(target_format: str, field_map: dict[str, int]) -> list[str]:
    if target_format == "UNKNOWN":
        return []
    required = {
        "COMPANY": ["Company", "PrimaryAddress", "City", "Zip"],
        "FULLNAME": ["FullName", "PrimaryAddress", "City", "Zip"],
        "FIRSTLAST": ["First Name", "Last Name", "PrimaryAddress", "City", "Zip"],
    }[target_format]
    return [field for field in required if field not in field_map]
