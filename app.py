import os
import io
import requests
from datetime import datetime
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)
CORS(app)

# Supabase config
SUPABASE_URL = 'https://rgmmtroobtxltcyykxtl.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJnbW10cm9vYnR4bHRjeXlreHRsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUxODU2NTMsImV4cCI6MjEwMDc2MTY1M30.MxrlRj31hbPWVLJ3Fhw1h3q-vjdki3YNYpZqw9nGk-c'

# Store list — English name (must match Supabase exactly) + Arabic name
STORES = [
    ("219-Al Faisaliayh (King Fahd Rd.)",              "الفيصلية - طريق الملك فهد"),
    ("280-Dahya King Fahad - Go station",               "ضاحية الملك فهد - محطة Go"),
    ("82-AlAqrabia (Prince Faisal Bin Fahed Rd.)",      "العقربية - طريق الأمير فيصل بن فهد"),
    ("270-Othman Ibn affan (AlNouzha)",                 "عثمان بن عفان - النزهة"),
    ("310-Al Rakah Al Janubiyah (King Fahed Rd.)",      "الراكة الجنوبية - طريق الملك فهد"),
    ("208-AlJalawiyah (King Khalid St.)",               "الجلوية - شارع الملك خالد"),
    ("308-AlNur (King Saud Rd.)",                       "النور - طريق الملك سعود"),
    ("233-Al Qusur (Prince Mohammed Bin Fahad Road)",   "القصور - طريق الأمير محمد بن فهد"),
    ("271-Al Fursan (Riyadh Rd.)",                      "الفرسان - طريق الرياض"),
    ("56-AlAzizia (King Khaled Rd.)",                   "العزيزية - طريق الملك خالد"),
    ("92-AlFaisalyah (Abu Bakr AlSdek St.)",            "الفيصلية - شارع أبو بكر الصديق"),
    ("53-Al Buhayrah",                                  "البحيرة"),
]

# Register Amiri font
font_dir = os.path.dirname(__file__)
try:
    pdfmetrics.registerFont(TTFont('Amiri', os.path.join(font_dir, 'Amiri-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('Amiri-Bold', os.path.join(font_dir, 'Amiri-Bold.ttf')))
    ARABIC_FONT = 'Amiri'
    ARABIC_FONT_BOLD = 'Amiri-Bold'
except Exception as e:
    print(f"Warning: Could not load Amiri font: {e}")
    ARABIC_FONT = 'Helvetica'
    ARABIC_FONT_BOLD = 'Helvetica-Bold'


def shape_arabic(text):
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def fetch_orders(date_str):
    """
    Fetch orders for a given date. Tries YYYY-MM-DD format first,
    then MM/DD/YYYY format as fallback (in case dates are stored differently).
    """
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}

    # Try YYYY-MM-DD first
    url1 = f"{SUPABASE_URL}/rest/v1/orders?date=eq.{date_str}&apikey={SUPABASE_KEY}"
    try:
        resp = requests.get(url1, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"Query {date_str}: {len(data)} rows")
        if data:
            return data
    except Exception as e:
        print(f"Fetch error (attempt 1): {e}")

    # Try MM/DD/YYYY as fallback
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        alt_date = dt.strftime('%m/%d/%Y')
        url2 = f"{SUPABASE_URL}/rest/v1/orders?date=eq.{alt_date}&apikey={SUPABASE_KEY}"
        resp2 = requests.get(url2, timeout=15)
        resp2.raise_for_status()
        data2 = resp2.json()
        print(f"Query {alt_date}: {len(data2)} rows")
        if data2:
            return data2
    except Exception as e:
        print(f"Fetch error (attempt 2): {e}")

    return []


def fetch_all_dates():
    """Debug: fetch recent orders to see what date format is used."""
    url = f"{SUPABASE_URL}/rest/v1/orders?select=date,store_name,quantity&limit=20&order=id.desc&apikey={SUPABASE_KEY}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return [{"error": str(e)}]


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/debug')
def debug():
    """Shows recent orders from Supabase — use to verify date format."""
    rows = fetch_all_dates()
    return jsonify({"recent_orders": rows, "total": len(rows)})


@app.route('/generate-pdf')
def generate_pdf():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "date parameter required (YYYY-MM-DD)"}), 400

    orders_raw = fetch_orders(date_str)

    # Build lookup: store_name → quantity
    order_map = {}
    for row in orders_raw:
        order_map[row.get('store_name', '')] = row.get('quantity', 0)

    # Format date for display
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        display_date = dt.strftime('%d %B %Y')
        display_date_ar = dt.strftime('%Y/%m/%d')
    except Exception:
        display_date = date_str
        display_date_ar = date_str

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER, spaceAfter=4)
    subtitle_style = ParagraphStyle('SubtitleStyle', parent=styles['Normal'],
        fontName='Helvetica', fontSize=11, alignment=TA_CENTER, spaceAfter=2,
        textColor=colors.HexColor('#555555'))
    arabic_title_style = ParagraphStyle('ArabicTitle', parent=styles['Normal'],
        fontName=ARABIC_FONT_BOLD, fontSize=16, alignment=TA_CENTER, spaceAfter=4)
    arabic_sub_style = ParagraphStyle('ArabicSub', parent=styles['Normal'],
        fontName=ARABIC_FONT, fontSize=11, alignment=TA_CENTER, spaceAfter=2,
        textColor=colors.HexColor('#555555'))
    cell_en_style = ParagraphStyle('CellEN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, alignment=TA_LEFT)
    cell_ar_style = ParagraphStyle('CellAR', parent=styles['Normal'],
        fontName=ARABIC_FONT, fontSize=9, alignment=TA_RIGHT)
    cell_num_style = ParagraphStyle('CellNum', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER)

    elements = []

    # Logo
    logo_path = os.path.join(font_dir, 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=40*mm, height=14*mm)
            logo.hAlign = 'CENTER'
            elements.append(logo)
            elements.append(Spacer(1, 3*mm))
        except Exception:
            pass

    # Header
    elements.append(Paragraph("Shawarmer — Eastern Region (Dammam &amp; Khobar)", title_style))
    elements.append(Paragraph(shape_arabic("شاورمر - المنطقة الشرقية (الدمام والخبر)"), arabic_title_style))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph("Fresh Arabic Bread Order", subtitle_style))
    elements.append(Paragraph(shape_arabic("طلب الخبز العربي الطازج"), arabic_sub_style))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(f"Order Date: {display_date}", subtitle_style))
    elements.append(Paragraph(shape_arabic(f"تاريخ الطلب: {display_date_ar}"), arabic_sub_style))
    elements.append(Spacer(1, 5*mm))

    # Table header
    header_en = Paragraph("<b>#</b>", cell_num_style)
    header_store_en = Paragraph("<b>Store (English)</b>",
        ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=TA_LEFT))
    header_store_ar = Paragraph(shape_arabic("المتجر (عربي)"),
        ParagraphStyle('H2', parent=styles['Normal'], fontName=ARABIC_FONT_BOLD, fontSize=9, alignment=TA_RIGHT))
    header_qty = Paragraph("<b>Packets</b>",
        ParagraphStyle('H3', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER))

    table_data = [[header_en, header_store_en, header_store_ar, header_qty]]

    total = 0
    for i, (en_name, ar_name) in enumerate(STORES, start=1):
        qty = order_map.get(en_name, 0)
        total += qty

        row_num = Paragraph(str(i), cell_num_style)
        row_en = Paragraph(en_name, cell_en_style)
        row_ar = Paragraph(shape_arabic(ar_name), cell_ar_style)
        row_qty = Paragraph(
            f"<b>{qty}</b>" if qty > 0 else "<font color='#aaaaaa'>—</font>",
            cell_num_style
        )
        table_data.append([row_num, row_en, row_ar, row_qty])

    # Total row
    total_label_en = Paragraph("<b>TOTAL</b>",
        ParagraphStyle('Tot', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT))
    total_label_ar = Paragraph(shape_arabic("الإجمالي"),
        ParagraphStyle('TotAr', parent=styles['Normal'], fontName=ARABIC_FONT_BOLD, fontSize=10, alignment=TA_RIGHT))
    total_qty = Paragraph(f"<b>{total}</b>",
        ParagraphStyle('TotQ', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER))
    table_data.append(["", total_label_en, total_label_ar, total_qty])

    col_widths = [10*mm, 72*mm, 72*mm, 22*mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c8102e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#fff5f5')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ffeaea')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#c8102e')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#c8102e')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 8*mm))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, alignment=TA_CENTER,
        textColor=colors.HexColor('#888888'))
    elements.append(Paragraph(
        f"Generated by Shawarmer Bread Ordering System • {datetime.now().strftime('%Y-%m-%d %H:%M')} AST",
        footer_style
    ))

    doc.build(elements)
    buffer.seek(0)

    filename = f"shawarmer-bread-order-{date_str}.pdf"
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=True, download_name=filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
