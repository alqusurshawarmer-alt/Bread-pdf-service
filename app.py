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
    """Fetch orders for a given date."""
    # Columns are: store, date, packets (NOT store_name / quantity)
    url = f"{SUPABASE_URL}/rest/v1/orders?select=store,date,packets&date=eq.{date_str}&apikey={SUPABASE_KEY}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"Query {date_str}: {len(data)} rows")
        return data
    except Exception as e:
        print(f"Fetch error: {e}")
        return []


def fetch_all_dates():
    """Debug: fetch recent orders."""
    url = f"{SUPABASE_URL}/rest/v1/orders?select=store,date,packets&limit=20&apikey={SUPABASE_KEY}"
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

    # Build lookup: store → packets
    order_map = {}
    for row in orders_raw:
        order_map[row.get('store', '')] = row.get('packets', 0)

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
    MAROON = colors.HexColor('#6b1a2a')
    GOLD   = colors.HexColor('#c8a84b')
    WHITE  = colors.white

    # Paragraph styles
    hdr_en_style = ParagraphStyle('HdrEN', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=18, alignment=TA_LEFT,
        textColor=WHITE, leading=22)
    hdr_sub_en_style = ParagraphStyle('HdrSubEN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, alignment=TA_LEFT,
        textColor=colors.HexColor('#dddddd'), leading=13)
    hdr_date_en_style = ParagraphStyle('HdrDateEN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, alignment=TA_LEFT,
        textColor=colors.HexColor('#dddddd'), leading=12)
    hdr_ar_style = ParagraphStyle('HdrAR', parent=styles['Normal'],
        fontName=ARABIC_FONT_BOLD, fontSize=18, alignment=TA_RIGHT,
        textColor=WHITE, leading=22)
    hdr_date_ar_style = ParagraphStyle('HdrDateAR', parent=styles['Normal'],
        fontName=ARABIC_FONT, fontSize=8, alignment=TA_RIGHT,
        textColor=colors.HexColor('#dddddd'), leading=12)
    banner_en_style = ParagraphStyle('BannerEN', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, alignment=TA_LEFT,
        textColor=MAROON)
    banner_ar_style = ParagraphStyle('BannerAR', parent=styles['Normal'],
        fontName=ARABIC_FONT_BOLD, fontSize=9, alignment=TA_RIGHT,
        textColor=MAROON)
    cell_en_style = ParagraphStyle('CellEN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, alignment=TA_LEFT)
    cell_ar_style = ParagraphStyle('CellAR', parent=styles['Normal'],
        fontName=ARABIC_FONT, fontSize=9, alignment=TA_RIGHT)
    cell_num_style = ParagraphStyle('CellNum', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER)
    th_en_style = ParagraphStyle('ThEN', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, alignment=TA_LEFT, textColor=WHITE)
    th_ar_style = ParagraphStyle('ThAR', parent=styles['Normal'],
        fontName=ARABIC_FONT_BOLD, fontSize=9, alignment=TA_RIGHT, textColor=WHITE)
    th_num_style = ParagraphStyle('ThNum', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER, textColor=WHITE)
    tot_en_style = ParagraphStyle('TotEN', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT)
    tot_ar_style = ParagraphStyle('TotAR', parent=styles['Normal'],
        fontName=ARABIC_FONT_BOLD, fontSize=10, alignment=TA_RIGHT)
    tot_num_style = ParagraphStyle('TotNum', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER)
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, alignment=TA_CENTER,
        textColor=colors.HexColor('#888888'))

    elements = []
    page_w = A4[0] - 30*mm  # usable width

    # ── HEADER BOX (maroon background, logo left, title centre, Arabic right) ──
    logo_path = os.path.join(font_dir, 'logo.png')
    if not os.path.exists(logo_path):
        logo_path = os.path.join(font_dir, 'logo.png.jpeg')

    logo_cell = ""
    if os.path.exists(logo_path):
        try:
            logo_cell = Image(logo_path, width=38*mm, height=38*mm)
        except Exception:
            pass

    title_cell = Table([
        [Paragraph("Fresh Arabic Bread", hdr_en_style)],
        [Paragraph("Daily Order Sheet  ·  Consolidated", hdr_sub_en_style)],
        [Paragraph(f"Date: {display_date}    Generated: {datetime.now().strftime('%d/%m/%Y %I:%M %p')}", hdr_date_en_style)],
    ], colWidths=[70*mm])
    title_cell.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    ar_cell = Table([
        [Paragraph(shape_arabic("خبز عربي طازج"), hdr_ar_style)],
        [Paragraph(shape_arabic(f"التاريخ: {display_date_ar}"), hdr_date_ar_style)],
    ], colWidths=[60*mm])
    ar_cell.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    header_table = Table(
        [[logo_cell, title_cell, ar_cell]],
        colWidths=[38*mm, 70*mm, 60*mm + (page_w - 38*mm - 70*mm - 60*mm)]
    )
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), MAROON),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 2*mm))

    # ── GOLD INFO BANNER ──
    banner_en = Paragraph("1 packet = 6 pcs of Arabic bread", banner_en_style)
    banner_ar = Paragraph(
        shape_arabic("شاورمر — المنطقة الشرقية (الدمام والخبر)  |  ١ طرد = ٦ قطع خبز عربي"),
        banner_ar_style)
    banner_table = Table([[banner_en, banner_ar]], colWidths=[page_w/2, page_w/2])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), GOLD),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(banner_table)
    elements.append(Spacer(1, 4*mm))

    # ── ORDER TABLE ──
    col_en  = 82*mm
    col_ar  = 72*mm
    col_qty = page_w - col_en - col_ar

    table_data = [[
        Paragraph("Store Name", th_en_style),
        Paragraph(shape_arabic("اسم الفرع"), th_ar_style),
        Paragraph("Pkts", th_num_style),
    ]]

    total = 0
    for en_name, ar_name in STORES:
        qty = order_map.get(en_name, 0)
        total += qty
        table_data.append([
            Paragraph(en_name, cell_en_style),
            Paragraph(shape_arabic(ar_name), cell_ar_style),
            Paragraph(f"<b>{qty}</b>" if qty > 0 else "<font color='#aaaaaa'>—</font>", cell_num_style),
        ])

    # Total row
    table_data.append([
        Paragraph("<b>Total (Pkts)</b>", tot_en_style),
        Paragraph(shape_arabic("المجموع (طرود)"), tot_ar_style),
        Paragraph(f"<b>{total}</b>", tot_num_style),
    ])

    t = Table(table_data, colWidths=[col_en, col_ar, col_qty], repeatRows=1)
    t.setStyle(TableStyle([
        # Header row — dark maroon
        ('BACKGROUND', (0,0), (-1,0), MAROON),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        # Alternating rows
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [WHITE, colors.HexColor('#f9f0f0')]),
        # Total row
        ('BACKGROUND', (0,-1), (-1,-1), MAROON),
        ('TEXTCOLOR', (0,-1), (-1,-1), WHITE),
        # Grid
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
        ('LINEBELOW', (0,0), (-1,0), 1.5, GOLD),
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, GOLD),
        # Alignment & padding
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (2,0), (2,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

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
