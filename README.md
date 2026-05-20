# bambuddy_spoolimport

A Python script that reads a CSV file of filament spools and bulk-imports them into [Bambuddy](https://bambuddy.app) via its REST API.

> **AI Disclaimer:** The code in this repository was mostly generated with the assistance of AI tools, but has been human-tested and verified to work correctly.

## Requirements

- Python 3.7+
- [requests](https://pypi.org/project/requests/)
- [reportlab](https://pypi.org/project/reportlab/) and [qrcode](https://pypi.org/project/qrcode/) (only needed for `print_labels.py`)

```
pip install requests reportlab qrcode[pil]
```

## Setup

1. Copy `config.sample.py` to `config.py`:

   ```
   cp config.sample.py config.py
   ```

2. Edit `config.py` and fill in your values:

   | Variable           | Description                                              |
   |--------------------|----------------------------------------------------------|
   | `BASE_URL`         | Your Bambuddy instance URL (no trailing slash)           |
   | `API_KEY`          | Your Bambuddy API key                                    |
   | `CSV_FILE`         | Path to your CSV file (relative or absolute)             |
   | `SPOOL_CATALOG_MAP`| Maps your CSV `spool_id` values to Bambuddy catalog IDs |

## CSV Format

The script expects a CSV with the following column headers:

| Column               | Description                                      |
|----------------------|--------------------------------------------------|
| `filament_type`      | Material (e.g. PLA, PETG) — **required**         |
| `filament_brand`     | Brand name                                       |
| `filament_line`      | Product line / sub-brand                         |
| `filament_color`     | Color name                                       |
| `filament_color_hex` | Hex color code (with or without leading `#`)     |
| `filament_sku`       | SKU used by your slicer                          |
| `filament_print_temp`| Nozzle temp range formatted as `min-max` (e.g. `190-230`) |
| `filament_used`      | Weight used in grams                             |
| `spool_id`           | Spool type ID — mapped to a catalog entry via `SPOOL_CATALOG_MAP` |
| `tray_uuid`          | AMS tray UUID (optional)                         |
| `starting_size_g`    | Starting weight in grams — defaults to 1000 if blank (optional) |
| `note`               | Free-text note (optional)                        |
| `roll_id`            | Previous roll ID — appended to the note as `#previous_id:XXX` (optional) |

Rows with a blank `filament_type` are skipped.

## Usage

### Import spools from CSV

```
python import_spools.py
```

Prints a per-row result (`[OK]`, `[FAIL]`, or `[SKIP]`) and a summary on completion.

### Print spool labels

Fetches spools from the Bambuddy API and generates a PDF of 75 × 55 mm labels
(ams_holder_75x55 format, one label per page). The PDF is written to `labels.pdf`
by default; use `--output` to change the path.

```
# Single label
python print_labels.py 42

# Multiple specific labels
python print_labels.py 42 43 44

# All spools
python print_labels.py --all

# Custom output path
python print_labels.py --all --output all_labels.pdf
python print_labels.py 42 43 --output my_labels.pdf
```
