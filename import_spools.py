"""
bambuddy_import.py
------------------
Reads a CSV file of filament spools and imports each one into Bambuddy
via their REST API.

Usage:
    python bambuddy_import.py

Before running, copy config.sample.py to config.py and fill in your values:
    BASE_URL  - Your Bambuddy instance URL (no trailing slash)
    API_KEY   - Your Bambuddy API key
    CSV_FILE  - Path to your CSV file

Dependencies:
    pip install requests
"""

import csv
import requests

from config import BASE_URL, API_KEY, CSV_FILE, SPOOL_CATALOG_MAP


def build_payload(row):
    """Build the API request body from a single CSV row dict."""

    def get_field(csv_col):
        """Return the stripped field value, or None if missing or blank."""
        value = row.get(csv_col, "").strip()
        return value if value else None

    def get_float_field(csv_col):
        """Return the field value as a float, or None if missing or unparseable."""
        value = get_field(csv_col)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def get_temp_range(csv_col):
        """
        Parse a "min-max" temperature field (e.g. "190-230").
        Returns (min, max) as ints, or (None, None) if missing or invalid.
        A single value with no dash is used for both min and max.
        """
        value = get_field(csv_col)
        if value is None:
            return None, None
        try:
            parts = value.split("-")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
            single = int(float(value))
            return single, single
        except (ValueError, IndexError):
            return None, None

    # Resolve the spool type to a catalog entry; unrecognised IDs are left as None.
    spool_id_raw = get_field("spool_id")
    core_catalog_id = None
    if spool_id_raw is not None:
        try:
            core_catalog_id = SPOOL_CATALOG_MAP.get(int(float(spool_id_raw)))
        except ValueError:
            pass

    # The API expects an 8-character RGBA hex string; append FF for full opacity.
    hex_raw = get_field("filament_color_hex")
    if hex_raw is not None:
        rgba_value = hex_raw.lstrip("#") + "FF"
    else:
        rgba_value = None

    slicer_filament = get_field("filament_sku")

    # Combine brand, type, and line into a single display name, skipping blank parts.
    name_parts = [
        get_field("filament_brand"),
        get_field("filament_type"),
        get_field("filament_line"),
    ]
    slicer_filament_name = " ".join(p for p in name_parts if p) or None

    nozzle_min, nozzle_max = get_temp_range("filament_print_temp")

    # Append the previous roll ID as a structured tag so it can be searched later.
    note = get_field("note")
    roll_id = get_field("roll_id")
    if roll_id is not None:
        roll_id_tag = f"#previous_id:{roll_id}"
        note = f"{note}\n{roll_id_tag}" if note else roll_id_tag

    return {
        "material"                 : get_field("filament_type"),
        "subtype"                  : get_field("filament_line"),
        "color_name"               : get_field("filament_color"),
        "rgba"                     : rgba_value,
        "brand"                    : get_field("filament_brand"),
        "label_weight"             : get_float_field("starting_size_g") or 1000,
        "core_weight_catalog_id"   : core_catalog_id,
        "weight_used"              : get_float_field("filament_used") or 0,
        "slicer_filament"          : slicer_filament,
        "slicer_filament_name"     : slicer_filament_name,
        "nozzle_temp_min"          : nozzle_min,
        "nozzle_temp_max"          : nozzle_max,
        "note"                     : note,
        "tag_uid"                  : None,
        "tray_uuid"                : get_field("tray_uuid"),
        "data_origin"              : "csv_import",
        "tag_type"                 : None,
        "cost_per_kg"              : None,
        "weight_locked"            : False,
        "last_scale_weight"        : None,
        "last_weighed_at"          : None,
    }


def post_spool(session, payload, row_number):
    """
    POST a single spool payload to the API.
    Returns True on success, False on any error.
    """
    url = f"{BASE_URL}/api/v1/inventory/spools"

    try:
        response = session.post(url, json=payload, timeout=15)
        response.raise_for_status()
        print(f"  [OK]  Row {row_number}: {payload.get('brand', '?')} "
              f"{payload.get('material', '?')} — {payload.get('color_name', '?')}")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"  [FAIL] Row {row_number}: HTTP error — {e}")
        print(f"         Response body: {e.response.text}")
        return False

    except requests.exceptions.ConnectionError:
        print(f"  [FAIL] Row {row_number}: Could not connect to {BASE_URL}. "
              "Check your BASE_URL and network connection.")
        return False

    except requests.exceptions.Timeout:
        print(f"  [FAIL] Row {row_number}: Request timed out.")
        return False


def main():
    print(f"Bambuddy CSV Importer")
    print(f"Target: {BASE_URL}")
    print(f"File:   {CSV_FILE}")
    print("-" * 50)

    success_count = 0
    fail_count    = 0
    skip_count    = 0

    # Reuse a single session so all requests share one TCP connection.
    with requests.Session() as session:
        session.headers.update({
            "X-API-Key"    : API_KEY,
            "Content-Type" : "application/json",
            "Accept"       : "application/json",
        })

        try:
            # newline="" and utf-8-sig are required for correct CSV parsing on Windows
            # and for files exported from Excel (which prepends a UTF-8 BOM).
            with open(CSV_FILE, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)

                for row_number, row in enumerate(reader, start=1):
                    # material is required by the API; skip rows that lack it.
                    if not row.get("filament_type", "").strip():
                        print(f"  [SKIP] Row {row_number}: no filament_type, skipping.")
                        skip_count += 1
                        continue

                    payload = build_payload(row)

                    if post_spool(session, payload, row_number):
                        success_count += 1
                    else:
                        fail_count += 1

        except FileNotFoundError:
            print(f"ERROR: CSV file not found: '{CSV_FILE}'")
            print("Check the CSV_FILE path in config.py.")
            return

    print("-" * 50)
    print(f"Import complete.")
    print(f"  Succeeded : {success_count}")
    print(f"  Failed    : {fail_count}")
    print(f"  Skipped   : {skip_count}")


if __name__ == "__main__":
    main()
