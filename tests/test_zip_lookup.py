from __future__ import annotations

import unittest

import pandas as pd

from listmanager.config import build_config
from listmanager.core.normalize import canonicalize
from listmanager.core.validate import validate_rows
from listmanager.zip_lookup import get_state_for_zip, normalize_zip


def _rows(*rows: dict[str, str]) -> pd.DataFrame:
    base = {
        "__Sheet": "COMPANY",
        "__SourceFile": "source.xlsx",
        "School": "Source",
        "Company": "Example Co",
        "ATTN": "",
        "FullName": "",
        "First Name": "",
        "Last Name": "",
        "PrimaryAddress": "1 Main St",
        "Address2": "",
        "City": "West Hartford",
        "State": "CT",
        "Zip": "06110",
        "Zip4": "",
        "Country": "",
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def _validated(*rows: dict[str, str]) -> pd.DataFrame:
    df = canonicalize(_rows(*rows), build_config(8))
    return validate_rows(df)


class ZipLookupTests(unittest.TestCase):
    def test_leading_zero_zip_is_preserved(self) -> None:
        self.assertEqual(normalize_zip("06110"), "06110")
        self.assertEqual(get_state_for_zip("06110"), "CT")

    def test_missing_state_is_filled_from_zip(self) -> None:
        df = _validated({"State": "", "Zip": "06110"})

        self.assertEqual(df.loc[0, "State"], "CT")
        self.assertEqual(df.loc[0, "ErrorReason"], "")
        self.assertIn("STATE_FILLED_FROM_ZIP", df.loc[0, "IssueCodes"])

    def test_state_zip_mismatch_moves_to_review(self) -> None:
        df = _validated({"State": "MI", "Zip": "06110"})

        self.assertIn("STATE_ZIP_MISMATCH", df.loc[0, "ErrorReason"])
        self.assertIn("STATE_ZIP_MISMATCH", df.loc[0, "IssueCodes"])

    def test_zip_not_found_moves_to_review(self) -> None:
        df = _validated({"State": "MI", "Zip": "99999"})

        self.assertIn("ZIP_NOT_FOUND", df.loc[0, "ErrorReason"])
        self.assertIn("ZIP_NOT_FOUND", df.loc[0, "IssueCodes"])

    def test_international_country_moves_to_review(self) -> None:
        df = _validated({"State": "ON", "Zip": "K1A 0B1", "Country": "Canada"})

        self.assertIn("International mail detected", df.loc[0, "ErrorReason"])
        self.assertIn("INTERNATIONAL_MAIL_REVIEW_REQUIRED", df.loc[0, "IssueCodes"])

    def test_canadian_postal_code_is_not_forced_to_us_zip(self) -> None:
        df = _validated({"State": "ON", "Zip": "K1A 0B1"})

        self.assertEqual(df.loc[0, "Zip5"], "")
        self.assertEqual(df.loc[0, "State"], "ON")
        self.assertIn("INTERNATIONAL_MAIL_REVIEW_REQUIRED", df.loc[0, "IssueCodes"])

    def test_blank_country_valid_us_zip_is_allowed(self) -> None:
        df = _validated({"Country": "", "Zip": "06110", "State": "CT"})

        self.assertEqual(df.loc[0, "ErrorReason"], "")

    def test_united_states_country_is_normalized_and_allowed(self) -> None:
        df = _validated({"Country": "United States", "Zip": "06110", "State": "CT"})

        self.assertEqual(df.loc[0, "CountryNorm"], "US")
        self.assertEqual(df.loc[0, "ErrorReason"], "")
        self.assertIn("COUNTRY_NORMALIZED_US", df.loc[0, "IssueCodes"])

    def test_company_rows_still_pass_company_format(self) -> None:
        df = _validated({"Company": "Example Co", "Zip": "06110", "State": "CT"})

        self.assertEqual(df.loc[0, "ErrorReason"], "")

    def test_duplicates_are_not_removed_in_validation_stage(self) -> None:
        df = _validated(
            {"Company": "Example Co", "Zip": "06110", "State": "CT"},
            {"Company": "Example Co", "Zip": "06110", "State": "CT"},
        )

        self.assertEqual(len(df), 2)
        self.assertTrue(df["ErrorReason"].eq("").all())


if __name__ == "__main__":
    unittest.main()
