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

import csv        # Standard library module for reading CSV files (no install needed)
import requests   # Third-party HTTP library — the Python equivalent of Java's HttpClient

from config import BASE_URL, API_KEY, CSV_FILE, SPOOL_CATALOG_MAP

# ---------------------------------------------------------------------------
# HELPER FUNCTION: Build the API payload from one CSV row
# ---------------------------------------------------------------------------
# In Python, a "dict" is like a HashMap<String, Object> in Java.
# A function is defined with "def" instead of a return-type declaration.
# ---------------------------------------------------------------------------

def build_payload(row):
    """
    Accepts a single CSV row (as a dict of {column_header: value})
    and returns a dict matching the Bambuddy POST /api/v1/inventory/spools body.
    """

    def get_field(csv_col):
        """
        Inner helper: returns the CSV value stripped of whitespace,
        or None if the column is missing or blank.
        In Python, None is used where Java uses null.
        """
        value = row.get(csv_col, "").strip()   # dict.get(key, default) — safe lookup
        return value if value else None        # return None instead of empty string

    def get_float_field(csv_col):
        """Returns the CSV value as a float, or None if missing/unparseable."""
        value = get_field(csv_col)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    # -----------------------------------------------------------------------
    # CHANGE 2: Parse temp range fields formatted as "min-max" (e.g. "190-230")
    # -----------------------------------------------------------------------
    # We split on "-" and unpack into two variables.
    # In Python, tuple unpacking lets you do: a, b = [1, 2]
    # The * operator in *parts unpacks a list into positional args — here we
    # use it to safely handle the split result regardless of list length.
    # -----------------------------------------------------------------------
    def get_temp_range(csv_col):
        """
        Parses a "min-max" formatted temperature field (e.g. "190-230").
        Returns a tuple of (min_int, max_int), or (None, None) if missing/invalid.
        """
        value = get_field(csv_col)
        if value is None:
            return None, None
        try:
            parts = value.split("-")   # str.split() works like Java's String.split()
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
            else:
                # Single value with no dash — use it for both min and max
                single = int(float(value))
                return single, single
        except (ValueError, IndexError):
            return None, None   # Tuple return — Python functions can return multiple values

    # -----------------------------------------------------------------------
    # CHANGE 1: Map spool_id to core_weight_catalog_id using SPOOL_CATALOG_MAP.
    # -----------------------------------------------------------------------
    spool_id_raw = get_field("spool_id")
    core_catalog_id    = None

    if spool_id_raw is not None:
        try:
            spool_id_int = int(float(spool_id_raw))
            # dict.get(key, default) returns None if key not in map —
            # equivalent to Java's map.getOrDefault(key, null)
            core_catalog_id = SPOOL_CATALOG_MAP.get(spool_id_int, None)
        except ValueError:
            pass   # "pass" is Python's empty block — like an empty {} catch in Java

    # -----------------------------------------------------------------------
    # CHANGE 3: Append "FF" to filament_color_hex to build the rgba value.
    # e.g. "FF5733" becomes "FF5733FF"
    # The hex value may or may not include a leading "#" — strip it if present.
    # -----------------------------------------------------------------------
    hex_raw = get_field("filament_color_hex")
    if hex_raw is not None:
        hex_clean = hex_raw.lstrip("#")   # Remove leading "#" if present
        rgba_value = hex_clean + "FF"     # Append FF for full opacity alpha channel
    else:
        rgba_value = None

    # -----------------------------------------------------------------------
    # CHANGE 4 & 5: slicer_filament and slicer_filament_name
    # slicer_filament       = filament_sku
    # slicer_filament_name  = brand + type + line, space-separated,
    #                         with None/blank parts filtered out
    # -----------------------------------------------------------------------
    slicer_filament = get_field("filament_sku")

    # Build the name from up to 3 parts, skipping any that are None/blank.
    # This list comprehension is like a Java stream filter + collect:
    #   parts = [x for x in [...] if x]  →  keep only truthy (non-None, non-empty) values
    name_parts = [
        get_field("filament_brand"),
        get_field("filament_type"),
        get_field("filament_line"),
    ]
    name_parts_clean = [p for p in name_parts if p]          # filter out None/blank
    slicer_filament_name = " ".join(name_parts_clean) or None # join with space; None if empty

    # -----------------------------------------------------------------------
    # CHANGE 2 (continued): Unpack the temp range tuple
    # -----------------------------------------------------------------------
    nozzle_min, nozzle_max = get_temp_range("filament_print_temp")

    note = get_field("note")
    roll_id = get_field("roll_id")
    if roll_id is not None:
        roll_id_tag = f" #previous_id:{roll_id}"
        note = f"{note}\n{roll_id_tag}" if note else roll_id_tag

    # Build and return the payload dict.
    # This is essentially constructing a JSON object — requests will serialize it.
    payload = {
        "material"                 : get_field("filament_type"),
        "subtype"                  : get_field("filament_line"),
        "color_name"               : get_field("filament_color"),
        "rgba"                     : rgba_value,             # CHANGE 3
        "brand"                    : get_field("filament_brand"),
        "label_weight"             : 1000,                   # Default: 1kg spool
        "core_weight_catalog_id"   : core_catalog_id,        # CHANGE 1
        "weight_used"              : get_float_field("filament_used"),
        "slicer_filament"          : slicer_filament,        # CHANGE 4
        "slicer_filament_name"     : slicer_filament_name,   # CHANGE 5
        "nozzle_temp_min"          : nozzle_min,             # CHANGE 2
        "nozzle_temp_max"          : nozzle_max,             # CHANGE 2
        "note"                     : note,
        "tag_uid"                  : None,
        "tray_uuid"                : get_field("tray_uuid"),
        "data_origin"              : "csv_import",           # Tags records with import origin
        "tag_type"                 : None,
        "cost_per_kg"              : None,
        "weight_locked"            : False,
        "last_scale_weight"        : None,
        "last_weighed_at"          : None,
    }

    return payload


# ---------------------------------------------------------------------------
# HELPER FUNCTION: POST one spool to the Bambuddy API
# ---------------------------------------------------------------------------

def post_spool(session, payload, row_number):
    """
    Sends a single spool payload to the API.

    Parameters:
        session    - a requests.Session object (like a reusable HttpClient)
        payload    - the dict to send as JSON
        row_number - used only for human-readable logging

    Returns True on success, False on failure.
    """

    url = f"{BASE_URL}/api/v1/inventory/spools"   # f-string = Java's String.format()

    try:
        # session.post() sends an HTTP POST request.
        # json=payload automatically serializes the dict and sets Content-Type.
        response = session.post(url, json=payload, timeout=15)

        # raise_for_status() throws an exception for 4xx/5xx responses,
        # similar to checking response.isSuccessful() and throwing in Java.
        response.raise_for_status()

        print(f"  [OK]  Row {row_number}: {payload.get('brand', '?')} "
              f"{payload.get('material', '?')} — {payload.get('color_name', '?')}")
        return True

    except requests.exceptions.HTTPError as e:
        # The server responded but with an error status code (4xx/5xx)
        print(f"  [FAIL] Row {row_number}: HTTP error — {e}")
        print(f"         Response body: {e.response.text}")
        return False

    except requests.exceptions.ConnectionError:
        # Could not reach the server at all
        print(f"  [FAIL] Row {row_number}: Could not connect to {BASE_URL}. "
              "Check your BASE_URL and network connection.")
        return False

    except requests.exceptions.Timeout:
        print(f"  [FAIL] Row {row_number}: Request timed out.")
        return False


# ---------------------------------------------------------------------------
# MAIN FUNCTION
# ---------------------------------------------------------------------------
# Python doesn't require a main() method, but it's good practice to use one.
# The "if __name__ == '__main__'" block at the bottom is the Python equivalent
# of Java's public static void main(String[] args) — it runs only when you
# execute this file directly, not when it's imported as a module.
# ---------------------------------------------------------------------------

def main():
    print(f"Bambuddy CSV Importer")
    print(f"Target: {BASE_URL}")
    print(f"File:   {CSV_FILE}")
    print("-" * 50)

    # Track results for a summary at the end
    success_count = 0
    fail_count    = 0
    skip_count    = 0

    # requests.Session reuses the underlying TCP connection across multiple
    # requests — more efficient than creating a new connection per spool.
    # Think of it like a pooled HttpClient in Java.
    with requests.Session() as session:

        # Set the API key header once on the session — it will be sent with
        # every request automatically. In Java you'd set this on the HttpClient
        # or add it manually to each request.
        session.headers.update({
            "X-API-Key"    : API_KEY,
            "Content-Type" : "application/json",
            "Accept"       : "application/json",
        })

        # Open the CSV file.
        # "with" is Python's try-with-resources equivalent — the file is
        # automatically closed when the block exits, even on exception.
        # newline="" is recommended by the csv module docs for Windows compatibility.
        # encoding="utf-8-sig" handles CSVs saved by Excel (which adds a BOM marker).
        try:
            with open(CSV_FILE, newline="", encoding="utf-8-sig") as csvfile:

                # DictReader parses each row into a dict keyed by the header row.
                # Similar to reading a CSV into a List<Map<String, String>> in Java.
                reader = csv.DictReader(csvfile)

                # Iterate over each row — Python "for" loops are like Java's
                # enhanced for-each: "for (Map<String, String> row : rows)"
                for row_number, row in enumerate(reader, start=1):

                    # Skip rows where filament_type (material) is blank —
                    # material is a required field in the API.
                    if not row.get("filament_type", "").strip():
                        print(f"  [SKIP] Row {row_number}: no filament_type, skipping.")
                        skip_count += 1
                        continue   # "continue" works the same as in Java

                    # Build the JSON payload for this row
                    payload = build_payload(row)

                    # Uncomment the next two lines to print each payload for debugging:
                    # print(f"  [DEBUG] Row {row_number} payload:")
                    # print(json.dumps(payload, indent=2))

                    # Send to the API and track result
                    if post_spool(session, payload, row_number):
                        success_count += 1
                    else:
                        fail_count += 1

        except FileNotFoundError:
            print(f"ERROR: CSV file not found: '{CSV_FILE}'")
            print("Check the CSV_FILE path at the top of the script.")
            return   # Exit main() early

    # Print summary
    print("-" * 50)
    print(f"Import complete.")
    print(f"  Succeeded : {success_count}")
    print(f"  Failed    : {fail_count}")
    print(f"  Skipped   : {skip_count}")


# ---------------------------------------------------------------------------
# Entry point — equivalent to Java's main(String[] args)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()