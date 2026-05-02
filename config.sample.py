BASE_URL = "https://your-bambuddy-url.com"   # No trailing slash
API_KEY  = "your-api-key-here"
CSV_FILE = "spools.csv"                       # Path to your CSV file, relative or absolute

# Maps the CSV "spool_id" value to the Bambuddy core_weight_catalog_id.
# If a spool_id is not listed here, catalog_id and core_weight are left as None.
SPOOL_CATALOG_MAP = {
    1: 25,
    2: 24,
    3: 23,
}
