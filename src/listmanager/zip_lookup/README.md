# ZIP Lookup Module

The application reads `resources/zip_lookup/us_zip_state_lookup.csv` at runtime.
It does not call USPS, HUD, or any other API while processing lists.

Preferred source order:

1. USPS City State Product. This is the preferred official source, but USPS
   distributes it through EPF/AIS ordering. USPS describes the data as encrypted
   and not exportable from the product viewer, so it is not bundled here.
2. HUD-USPS ZIP Code Crosswalk files. These are derived from USPS Vacancy Data
   and include `USPS_ZIP_PREF_CITY` and `USPS_ZIP_PREF_STATE` fields in ZIP-to-*
   files. HUD notes PO Box only ZIP Codes are excluded and a small number of
   active ZIP Codes may be missing.
3. Census ZCTA files. Use only as a fallback. ZCTAs are Census geography
   approximations and are not the same as USPS ZIP Codes.
4. Third-party ZIP CSV. The bundled source CSV is an archived third-party
   fallback because direct USPS CSV access is not practical for this project.

To rebuild:

```bash
python -m listmanager.zip_lookup.build_zip_lookup
```

Place source CSV files under `resources/zip_lookup/source/`. The builder accepts:

- HUD ZIP-to-* CSVs with `ZIP`, `USPS_ZIP_PREF_CITY`, and
  `USPS_ZIP_PREF_STATE`.
- CSVs with `Zipcode`, `City`, and `State`.
- CSVs with `zip`, `city`, and `state`.

The generated lookup preserves ZIP values as five-character text and writes a
build report that flags ZIPs mapped to multiple states.
