from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ZipLookupSource:
    name: str
    source_type: str
    description: str
    expected_files: tuple[str, ...]
    notes: str


USPS_CITY_STATE = ZipLookupSource(
    name="USPS City State Product",
    source_type="preferred",
    description=(
        "USPS AIS product containing ZIP Codes with corresponding city and county "
        "names, plus other Post Office names."
    ),
    expected_files=("*.txt", "*.csv", "*.xlsx"),
    notes=(
        "Preferred official source, but access is through USPS EPF/AIS ordering. "
        "USPS documents that the data is encrypted and cannot be exported from "
        "the product viewer, so it is not bundled here."
    ),
)

HUD_USPS_CROSSWALK = ZipLookupSource(
    name="HUD-USPS ZIP Code Crosswalk",
    source_type="accepted",
    description=(
        "HUD public crosswalk files derived from USPS Vacancy Data. ZIP-to-* "
        "files include ZIP, USPS_ZIP_PREF_CITY, and USPS_ZIP_PREF_STATE fields."
    ),
    expected_files=("ZIP_*_*.csv", "*.csv"),
    notes=(
        "Good public fallback when source files are available locally. HUD notes "
        "that PO Box only ZIP Codes are excluded and a small number of ZIP Codes "
        "may be missing."
    ),
)

FEDERAL_GOVERNMENT_ZIPCODES_ARCHIVE = ZipLookupSource(
    name="Archived federalgovernmentzipcodes.us Primary CSV",
    source_type="third_party_fallback",
    description=(
        "Archived CSV with Zipcode, City, and State columns. It was historically "
        "published as a free ZIP database and is used only because direct USPS "
        "CSV access is not practical for this project."
    ),
    expected_files=("free-zipcode-database-Primary.csv",),
    notes=(
        "Third-party fallback, not official USPS validation data. Rebuild with "
        "USPS City State Product or HUD-USPS source files when available."
    ),
)

SOURCE_DIR = Path("resources") / "zip_lookup" / "source"
LOOKUP_CSV = Path("resources") / "zip_lookup" / "us_zip_state_lookup.csv"
BUILD_REPORT = Path("resources") / "zip_lookup" / "build_report.txt"

ALL_SOURCES = (
    USPS_CITY_STATE,
    HUD_USPS_CROSSWALK,
    FEDERAL_GOVERNMENT_ZIPCODES_ARCHIVE,
)
