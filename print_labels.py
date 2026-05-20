"""
print_labels.py
---------------
Fetches one or more spools from the Bambuddy API and writes a PDF of
ams_holder_75x55 labels (75 × 55 mm, one label per page).

Usage:
    python print_labels.py <id> [<id> ...] [--output labels.pdf]

Dependencies:
    pip install requests reportlab qrcode[pil]
"""

import argparse
import io
import sys

import qrcode
import requests
from reportlab.lib.colors import Color, HexColor, black
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from config import API_KEY, BASE_URL

LABEL_W = 75.0 * mm
LABEL_H = 55.0 * mm


# ── Data container ────────────────────────────────────────────────────────────

class LabelData:
    __slots__ = ("spool_id", "name", "material", "brand", "subtype",
                 "rgba", "extra_colors", "storage_location", "deeplink_url")

    def __init__(self, spool_id, name, material, brand=None, subtype=None,
                 rgba=None, extra_colors=None, storage_location=None, deeplink_url=""):
        self.spool_id = spool_id
        self.name = name
        self.material = material
        self.brand = brand
        self.subtype = subtype
        self.rgba = rgba
        self.extra_colors = extra_colors or []
        self.storage_location = storage_location
        self.deeplink_url = deeplink_url


# ── Colour helpers ────────────────────────────────────────────────────────────

def _color_from_hex(hex_str, fallback=HexColor(0x808080)):
    """Parse an RRGGBB or RRGGBBAA string into a ReportLab Color."""
    if not hex_str:
        return fallback
    h = hex_str.lstrip("#").strip()
    if len(h) not in (6, 8):
        return fallback
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return Color(r, g, b, alpha=a)
    except ValueError:
        return fallback


def _hex_code_label(rgba):
    """Return a printable #RRGGBB string, dropping the alpha channel."""
    if not rgba:
        return ""
    h = rgba.lstrip("#").strip()
    if len(h) not in (6, 8):
        return ""
    rgb = h[:6]
    if not all(c in "0123456789abcdefABCDEF" for c in rgb):
        return ""
    return f"#{rgb.upper()}"


# ── QR generation ─────────────────────────────────────────────────────────────

def _qr_png_bytes(payload):
    if not payload:
        return b""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _draw_swatch(c, x, y, w, h, data):
    """Draw a colour swatch; multi-colour spools render as vertical stripes."""
    primary = _color_from_hex(data.rgba)
    colors = [primary] + [_color_from_hex(hx) for hx in data.extra_colors if hx]

    stripe_w = w / len(colors)
    for i, col in enumerate(colors):
        c.setFillColor(col)
        c.rect(x + i * stripe_w, y, stripe_w, h, stroke=0, fill=1)

    # Thin border so light-coloured swatches stay visible on white stock.
    c.setStrokeColor(black)
    c.setLineWidth(0.3)
    c.rect(x, y, w, h, stroke=1, fill=0)


def _draw_qr(c, x, y, size, payload):
    png = _qr_png_bytes(payload)
    if not png:
        return
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(io.BytesIO(png)), x, y, width=size, height=size, mask="auto")


def _truncate(c, text, font, size, max_w):
    """Truncate text with an ellipsis to fit within max_w points."""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    while text and c.stringWidth(text + ell, font, size) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


def _draw_label(c, data):
    """Render one ams_holder_75x55 label.

    Layout: swatch on the left (full height); filament type and subtype span
    the full remaining width at the top; QR sits in the lower-right with the
    remaining text fields to its left.
    """
    x, y, w, h = 0, 0, LABEL_W, LABEL_H
    pad = 1.2 * mm
    inner_x = x + pad
    inner_y = y + pad
    inner_w = w - 2 * pad
    inner_h = h - 2 * pad

    # Hairline border for easy cutting from blank stock.
    c.setStrokeColor(HexColor(0xCCCCCC))
    c.setLineWidth(0.4)
    c.rect(x, y, w, h, stroke=1, fill=0)

    swatch_w = min(inner_w * 0.18, inner_h, 16 * mm)
    _draw_swatch(c, inner_x, inner_y, swatch_w, inner_h, data)

    text_x = inner_x + swatch_w + 1.5 * mm
    full_w = inner_x + inner_w - text_x  # spans all the way to the right edge

    c.setFillColor(black)
    cursor_y = y + h - pad
    gap = 3.5  # points of spacing between lines

    # Lines 1 & 2: filament type and subtype — span full width so they never get cut off.
    if data.material:
        size = 14
        c.setFont("Helvetica-Bold", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, _truncate(c, data.material, "Helvetica-Bold", size, full_w))
        cursor_y -= gap

    if data.subtype:
        size = 14
        c.setFont("Helvetica-Bold", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, _truncate(c, data.subtype, "Helvetica-Bold", size, full_w))
        cursor_y -= gap*2

    # QR is placed in the lower-right of the space that remains below the header lines.
    remaining_h = cursor_y - inner_y
    qr_size = min(inner_w * 0.40, remaining_h, 36 * mm)
    qr_x = x + w - pad - qr_size
    qr_y = inner_y + (remaining_h - qr_size) / 2
    _draw_qr(c, qr_x, qr_y, qr_size, data.deeplink_url)

    text_w = qr_x - text_x - 1.5 * mm
    if text_w < 8 * mm:
        return

    # Remaining lines occupy the text column to the left of the QR.
    if data.name:
        size = 11
        c.setFont("Helvetica-Bold", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, _truncate(c, data.name, "Helvetica-Bold", size, text_w))
        cursor_y -= gap

    hex_code = _hex_code_label(data.rgba)
    if hex_code:
        size = 8
        c.setFont("Helvetica", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, hex_code)
        cursor_y -= gap*2

    if data.brand:
        size = 10
        c.setFont("Helvetica-Bold", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, _truncate(c, data.brand, "Helvetica-Bold", size, text_w))
        cursor_y -= gap

    if data.storage_location:
        size = 6.5
        c.setFont("Helvetica-Oblique", size)
        cursor_y -= size
        c.drawString(text_x, cursor_y, _truncate(c, data.storage_location, "Helvetica-Oblique", size, text_w))

    # Spool ID anchored at the bottom — the most-readable field at arm's length.
    id_size = 20
    c.setFont("Helvetica-Bold", id_size)
    c.drawString(text_x, inner_y + 0.5, _truncate(c, f"#{data.spool_id}", "Helvetica-Bold", id_size, text_w))


# ── PDF rendering ─────────────────────────────────────────────────────────────

def render_pdf(data_list):
    """Render a list of LabelData to a PDF and return the bytes."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(LABEL_W, LABEL_H))
    c.setTitle("Bambuddy spool labels (ams_holder_75x55)")
    for data in data_list:
        _draw_label(c, data)
        c.showPage()
    c.save()
    return buf.getvalue()


# ── API helpers ───────────────────────────────────────────────────────────────

def fetch_spool(session, spool_id):
    response = session.get(f"{BASE_URL}/api/v1/inventory/spools/{spool_id}", timeout=15)
    response.raise_for_status()
    return response.json()


def spool_to_label(spool):
    """Map a Bambuddy API spool object to a LabelData."""
    return LabelData(
        spool_id=spool["id"],
        name=spool.get("color_name") or "",
        material=spool.get("material") or "",
        brand=spool.get("brand"),
        subtype=spool.get("subtype"),
        rgba=spool.get("rgba"),
        storage_location=spool.get("storage_location"),
        deeplink_url=f"{BASE_URL}/inventory?spool={spool['id']}",
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate ams_holder_75x55 PDF labels for Bambuddy spools."
    )
    parser.add_argument("ids", nargs="+", type=int, metavar="ID", help="One or more spool IDs")
    parser.add_argument("--output", "-o", default="labels.pdf", metavar="FILE",
                        help="Output PDF path (default: labels.pdf)")
    args = parser.parse_args()

    with requests.Session() as session:
        session.headers.update({
            "X-API-Key": API_KEY,
            "Accept": "application/json",
        })

        labels = []
        for spool_id in args.ids:
            try:
                spool = fetch_spool(session, spool_id)
                labels.append(spool_to_label(spool))
                print(f"  [OK]   #{spool_id}: {spool.get('brand', '?')} "
                      f"{spool.get('material', '?')} — {spool.get('color_name', '?')}")
            except requests.exceptions.HTTPError as e:
                print(f"  [FAIL] #{spool_id}: HTTP {e.response.status_code} — {e}", file=sys.stderr)
            except requests.exceptions.ConnectionError:
                print(f"  [FAIL] Could not connect to {BASE_URL}. Check BASE_URL and network.", file=sys.stderr)
                sys.exit(1)
            except requests.exceptions.Timeout:
                print(f"  [FAIL] #{spool_id}: Request timed out.", file=sys.stderr)

        if not labels:
            print("No labels to generate.", file=sys.stderr)
            sys.exit(1)

        with open(args.output, "wb") as f:
            f.write(render_pdf(labels))

        print(f"\nWrote {len(labels)} label(s) to {args.output}")


if __name__ == "__main__":
    main()
