import io
import requests
from datetime import datetime
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

def generate_certificate_pdf(student_name, course_name, org_name, logo_url=None, signature_url=None, issue_date=None):
    """
    Generates a professional certificate PDF in memory using ReportLab.
    Includes Org Logo and Admin Signature if provided.
    """
    buffer = io.BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    # 1. Background Border
    c.setStrokeColor(colors.HexColor("#7c3aed")) # Admin Purple
    c.setLineWidth(15)
    c.rect(20, 20, w-40, h-40)
    
    c.setStrokeColor(colors.HexColor("#a78bfa")) # Light Purple
    c.setLineWidth(2)
    c.rect(35, 35, w-70, h-70)

    # 2. Logo (If provided)
    if logo_url:
        try:
            # Handle local paths if no scheme is provided
            final_logo_url = logo_url
            if not final_logo_url.startswith("http"):
                final_logo_url = f"http://127.0.0.1:8000/{final_logo_url}"
                
            logo_data = requests.get(final_logo_url).content
            logo_img = ImageReader(io.BytesIO(logo_data))
            c.drawImage(logo_img, w/2 - 50, h - 100, width=100, height=60, mask='auto', preserveAspectRatio=True)
        except Exception as e:
            print(f"Error loading certificate logo: {e}")

    # 3. Header
    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(colors.HexColor("#1e293b"))
    # Move title down if logo exists
    title_y = h - 130 if logo_url else h - 120
    c.drawCentredString(w/2, title_y, org_name.upper())
    
    c.setFont("Helvetica", 18)
    c.drawCentredString(w/2, title_y - 35, "OFFICIAL CERTIFICATE OF COMPLETION")

    # 4. Content
    c.setFont("Helvetica", 22)
    c.drawCentredString(w/2, h/2 + 40, "This is to certify that")
    
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(colors.HexColor("#7c3aed"))
    c.drawCentredString(w/2, h/2 - 20, student_name)
    
    c.setFont("Helvetica", 22)
    c.setFillColor(colors.HexColor("#1e293b"))
    c.drawCentredString(w/2, h/2 - 70, "has successfully completed the course")
    
    c.setFont("Helvetica-BoldOblique", 28)
    c.drawCentredString(w/2, h/2 - 120, f'"{course_name}"')

    # 5. Footer (Date and Signature)
    if not issue_date:
        issue_date = datetime.utcnow().strftime("%B %d, %Y")
    
    c.setFont("Helvetica", 14)
    c.drawCentredString(w/4 + 50, 120, f"Issued on: {issue_date}")
    
    # Signature Line
    c.setDash(1, 2)
    c.line(w*0.6, 120, w*0.85, 120)
    c.setDash()
    
    # Draw Signature Image (If provided)
    if signature_url:
        try:
            # Handle local paths if no scheme is provided
            final_sig_url = signature_url
            if not final_sig_url.startswith("http"):
                final_sig_url = f"http://127.0.0.1:8000/{final_sig_url}"
                
            sig_data = requests.get(final_sig_url).content
            sig_img = ImageReader(io.BytesIO(sig_data))
            # Draw signature above the line
            c.drawImage(sig_img, w*0.65, 125, width=120, height=50, mask='auto', preserveAspectRatio=True)
        except Exception as e:
            print(f"Error loading certificate signature: {e}")

    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(w*0.725, 105, "Platform Administrator")

    # 6. Finishing up
    c.showPage()
    c.save()
    
    buffer.seek(0)
    return buffer
