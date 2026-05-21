"""
list_spools.py
--------------
Prints a summary of all spools: ID followed by the note field.

Usage:
    python list_spools.py
"""

import requests
from config import API_KEY, BASE_URL


def main():
    with requests.Session() as session:
        session.headers.update({
            "X-API-Key": API_KEY,
            "Accept": "application/json",
        })
        response = session.get(f"{BASE_URL}/api/v1/inventory/spools", timeout=30)
        response.raise_for_status()
        spools = response.json()

    for spool in sorted(spools, key=lambda s: s["id"]):
        note = spool.get("note") or ""
        print(f"{spool['id']} - {note}")


if __name__ == "__main__":
    main()
