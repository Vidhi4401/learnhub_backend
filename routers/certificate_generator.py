"""
Professional Certificate PDF Generator
Uses ReportLab to produce a high-quality landscape certificate.
"""

import io
import math
import hashlib
from datetime import datetime
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

# ── Colour Palette ─────────────────────────────────────────────────────────
PURPLE_DARK  = HexColor("#4c1d95")
PURPLE_MID   = HexColor("#7c3aed")
PURPLE_LIGHT = HexColor("#ede9fe")
GOLD         = HexColor("#d97706")
GOLD_LIGHT   = HexColor("#fef3c7")
INK          = HexColor("#1e293b")
MUTED        = HexColor("#64748b")
WHITE        = colors.white


def _corners(c, x, y, w, h, size=20, lw=2.5, colour=GOLD):
    c.setStrokeColor(colour)
    c.setLineWidth(lw)
    for cx, cy, sx, sy in [
        (x,   y+h,  1, -1),
        (x+w, y+h, -1, -1),
        (x,   y,    1,  1),
        (x+w, y,   -1,  1),
    ]:
        c.line(cx, cy, cx + sx*size, cy)
        c.line(cx, cy, cx, cy + sy*size)


def _seal(c, cx, cy, r=30):
    c.setStrokeColor(GOLD)
    c.setFillColor(PURPLE_DARK)
    c.setLineWidth(2)
    c.circle(cx, cy, r, stroke=1, fill=1)
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(1)
    c.circle(cx, cy, r * 0.78, stroke=1, fill=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    for i in range(12):
        a = math.radians(i * 30)
        c.line(cx + math.cos(a)*r*0.52, cy + math.sin(a)*r*0.52,
               cx + math.cos(a)*r*0.76, cy + math.sin(a)*r*0.76)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(cx, cy + 3, "VERIFIED")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx, cy - 7, "✓")


def generate_certificate_pdf(
    student_name: str,
    course_name:  str,
    org_name:     str,
    issue_date:   str = None
) -> io.BytesIO:
    if not issue_date:
        issue_date = datetime.utcnow().strftime("%B %d, %Y")

    buffer = io.BytesIO()
    W, H   = landscape(A4)
    c      = canvas.Canvas(buffer, pagesize=landscape(A4))

    # ── Background ──────────────────────────────────────────────────────────
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Purple tinted top band
    c.setFillColor(PURPLE_LIGHT)
    c.rect(0, H - 105, W, 105, fill=1, stroke=0)

    # Gold divider at base of band
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(50, H - 105, W - 50, H - 105)

    # ── Borders ─────────────────────────────────────────────────────────────
    m = 22
    c.setStrokeColor(PURPLE_DARK)
    c.setLineWidth(6)
    c.rect(m, m, W - m*2, H - m*2, fill=0, stroke=1)

    c.setStrokeColor(PURPLE_MID)
    c.setLineWidth(1)
    inner_m = m + 9
    c.rect(inner_m, inner_m, W - inner_m*2, H - inner_m*2, fill=0, stroke=1)

    _corners(c, inner_m, inner_m, W - inner_m*2, H - inner_m*2)

    # ── Header ──────────────────────────────────────────────────────────────
    c.setFillColor(PURPLE_DARK)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(W/2, H - 50, org_name.upper())

    ry = H - 67
    c.setStrokeColor(PURPLE_MID)
    c.setLineWidth(0.8)
    c.line(W/2 - 145, ry, W/2 - 20, ry)
    c.line(W/2 + 20,  ry, W/2 + 145, ry)
    c.setFillColor(PURPLE_MID)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(W/2, ry - 5, "CERTIFICATE  OF  COMPLETION")

    # ── Seals ───────────────────────────────────────────────────────────────
    _seal(c, m + 74, H/2 + 8)
    _seal(c, W - m - 74, H/2 + 8)

    # ── Body ────────────────────────────────────────────────────────────────
    top = H - 142

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 13)
    c.drawCentredString(W/2, top, "This is to proudly certify that")

    # Student name
    ny = top - 48
    c.setFillColor(PURPLE_DARK)
    c.setFont("Helvetica-Bold", 42)
    c.drawCentredString(W/2, ny, student_name)

    # Underline
    nw = min(c.stringWidth(student_name, "Helvetica-Bold", 42) + 40, W - 160)
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.line(W/2 - nw/2, ny - 8, W/2 + nw/2, ny - 8)

    c.setFillColor(INK)
    c.setFont("Helvetica", 14)
    c.drawCentredString(W/2, ny - 34, "has successfully completed the course")

    # Course name
    cy2 = ny - 72
    c.setFillColor(PURPLE_MID)
    c.setFont("Helvetica-BoldOblique", 21)
    max_cw = W - 300
    cd = course_name
    while c.stringWidth(f'"{cd}"', "Helvetica-BoldOblique", 21) > max_cw and len(cd) > 8:
        cd = cd[:-1]
    if cd != course_name:
        cd = cd.rstrip() + "…"
    c.drawCentredString(W/2, cy2, f'"{cd}"')

    c.setFillColor(INK)
    c.setFont("Helvetica", 11.5)
    c.drawCentredString(W/2, cy2 - 26,
        "and has demonstrated the knowledge and skills required for this qualification.")

    # ── Footer ──────────────────────────────────────────────────────────────
    fy = m + 56

    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(80, fy + 24, W - 80, fy + 24)

    # Date (left)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(80, fy + 8, "DATE OF ISSUE")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(80, fy - 8, issue_date)

    # Cert ID (centre)
    cert_id = hashlib.md5(
        f"{student_name}{course_name}{issue_date}".encode()
    ).hexdigest()[:12].upper()
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(W/2, fy, f"Certificate No: {cert_id}")

    # Signature line (right)
    sx = W - 185
    c.setStrokeColor(INK)
    c.setDash(2, 3)
    c.setLineWidth(0.8)
    c.line(sx - 70, fy + 6, sx + 70, fy + 6)
    c.setDash()
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(sx, fy - 8, "AUTHORISED SIGNATURE")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
