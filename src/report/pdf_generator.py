"""PDF report generator reproducing the VASOSCREEN layout using reportlab."""

import io
from datetime import date
from typing import Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

from ..models import PPGBlock
from ..analysis import calculate_parameters
from ..config import LABEL_DESCRIPTIONS
from ..diagnosis.classifier import classify_channel, classify_pump, VenousGrade
from ..diagnosis.text_generator import generate_classification_table
from .templates import (
    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM,
    CONTENT_WIDTH, PAGE_WIDTH, PAGE_HEIGHT,
    FONT_TITLE, FONT_SUBTITLE, FONT_BODY, FONT_SMALL, FONT_TABLE,
    COLOR_CYAN, COLOR_BLACK, COLOR_GRAY, COLOR_RED,
    METHOD_TEXT, PARAM_DESCRIPTIONS, CHANNEL_GRID, CHANNEL_POINT_INFO,
)
from .chart_renderer import render_ppg_chart, render_diagnostic_chart


def generate_report_pdf(
    filepath: str,
    patient_name: str,
    patient_dob: Optional[str],
    patient_gender: Optional[str],
    patient_id: Optional[str],
    exam_date: date,
    blocks: Dict[int, PPGBlock],
    complaints: str = "",
    diagnosis_text: str = "",
    clinic_name: str = "",
    doctor_name: str = "",
    doctor_crm: str = "",
    report_title: str = "D-PPG",
    report_app_line: str = "D-PPG Digital Photoplethysmography",
):
    """Generate a PDF report.

    Args:
        filepath: Output PDF path
        patient_name: Full patient name
        patient_dob: Date of birth string
        patient_gender: M/F
        patient_id: Patient ID/document number
        exam_date: Date of the exam
        blocks: dict mapping label_byte -> PPGBlock
        complaints: Patient complaints text
        diagnosis_text: Diagnostic text (auto-generated or edited)
        clinic_name: Clinic name for header
        doctor_name: Doctor name for signature
        doctor_crm: Doctor CRM registration number
        report_title: Main report title (replaces VASOSCREEN)
        report_app_line: Application description line
    """
    c = Canvas(filepath, pagesize=A4)
    w, h = A4
    y = h - MARGIN_TOP

    # ================================================================
    # 1. HEADER (all texts configurable)
    # ================================================================
    c.setFont("Helvetica-Bold", FONT_TITLE)
    c.setFillColorRGB(*COLOR_CYAN)
    c.drawString(MARGIN_LEFT, y, report_title)
    y -= 16

    c.setFont("Helvetica", FONT_SMALL)
    c.setFillColorRGB(*COLOR_GRAY)
    if clinic_name:
        c.drawString(MARGIN_LEFT, y, clinic_name)
        y -= 10
    if doctor_name:
        label = f"Examinador: {doctor_name}"
        if doctor_crm:
            label += f"  CRM {doctor_crm}"
        c.drawString(MARGIN_LEFT, y, label)
        y -= 10

    y -= 5
    c.setStrokeColorRGB(*COLOR_CYAN)
    c.setLineWidth(1)
    c.line(MARGIN_LEFT, y, w - MARGIN_RIGHT, y)
    y -= 12

    # ================================================================
    # 2. PATIENT DATA
    # ================================================================
    c.setFont("Helvetica-Bold", FONT_SUBTITLE)
    c.setFillColorRGB(*COLOR_BLACK)
    c.drawString(MARGIN_LEFT, y, f"Paciente: {patient_name}")

    info_parts = []
    if patient_dob:
        info_parts.append(f"Nasc: {patient_dob}")
    if patient_gender:
        info_parts.append(f"Sexo: {'Masculino' if patient_gender == 'M' else 'Feminino'}")
    if patient_id:
        info_parts.append(f"ID: {patient_id}")

    if info_parts:
        c.setFont("Helvetica", FONT_BODY)
        c.drawRightString(w - MARGIN_RIGHT, y, "  |  ".join(info_parts))
    y -= 18

    # ================================================================
    # 3. APPLICATION LINE (configurable)
    # ================================================================
    c.setFont("Helvetica", FONT_BODY)
    c.setFillColorRGB(*COLOR_GRAY)
    c.drawString(MARGIN_LEFT, y, report_app_line)
    c.drawRightString(w - MARGIN_RIGHT, y, f"Data: {exam_date.strftime('%d/%m/%Y')}")
    y -= 18

    # ================================================================
    # 4. PPG CHARTS (2x2 grid) with point indicators
    # ================================================================
    chart_w_pt = CONTENT_WIDTH / 2 - 5
    chart_h_pt = 100
    dpi = 150
    chart_w_in = chart_w_pt / 72
    chart_h_in = chart_h_pt / 72

    for row_idx, row in enumerate(CHANNEL_GRID):
        for col_idx, label_byte in enumerate(row):
            block = blocks.get(label_byte)
            point_info = CHANNEL_POINT_INFO.get(label_byte)
            pt_num = point_info[0] if point_info else None
            pt_color = point_info[1] if point_info else None

            if block:
                png_data = render_ppg_chart(block, width_inches=chart_w_in,
                                            height_inches=chart_h_in, dpi=dpi,
                                            point_number=pt_num, point_color=pt_color)
            else:
                png_data = _placeholder_png(label_byte, chart_w_in, chart_h_in, dpi)

            x_pos = MARGIN_LEFT + col_idx * (chart_w_pt + 10)
            img = ImageReader(io.BytesIO(png_data))
            c.drawImage(img, x_pos, y - chart_h_pt, chart_w_pt, chart_h_pt)

        y -= chart_h_pt + 8

    y -= 5

    # ================================================================
    # 5. PARAMETERS TABLE (with red for abnormal values)
    # ================================================================
    params_by_label = {}
    for label_byte, block in blocks.items():
        p = calculate_parameters(block)
        if p:
            params_by_label[label_byte] = p

    y = _draw_params_table(c, y, params_by_label)
    y -= 10

    # ================================================================
    # 6. DIAGNOSTIC CHART
    # ================================================================
    diag_points = []
    labels_order = [(0xDF, "1-MIE"), (0xE1, "2-MID"), (0xE0, "3-MIE Tq"), (0xE2, "4-MID Tq")]
    for lb, lbl in labels_order:
        p = params_by_label.get(lb)
        if p:
            diag_points.append((p.To, p.Vo, lbl))

    if diag_points:
        diag_w_in = 3.5
        diag_h_in = 2.2
        diag_png = render_diagnostic_chart(diag_points, diag_w_in, diag_h_in, dpi)
        diag_w_pt = diag_w_in * 72
        diag_h_pt = diag_h_in * 72
        x_center = MARGIN_LEFT + (CONTENT_WIDTH - diag_w_pt) / 2
        c.drawImage(ImageReader(io.BytesIO(diag_png)), x_center, y - diag_h_pt,
                     diag_w_pt, diag_h_pt)
        y -= diag_h_pt + 8

    # ================================================================
    # 7. METHOD TEXT
    # ================================================================
    c.setFont("Helvetica", FONT_SMALL)
    c.setFillColorRGB(*COLOR_GRAY)
    text_obj = c.beginText(MARGIN_LEFT, y)
    text_obj.setFont("Helvetica", FONT_SMALL)
    text_obj.setFillColorRGB(*COLOR_GRAY)
    wrapped_method = _wrap_text(METHOD_TEXT, CONTENT_WIDTH, "Helvetica", FONT_SMALL, c)
    for line in wrapped_method:
        text_obj.textLine(line)
    c.drawText(text_obj)
    y -= (FONT_SMALL + 2) * len(wrapped_method) + 8

    # ================================================================
    # 8. CLASSIFICATION TABLE (with red for all abnormal grades)
    # ================================================================
    channels_dict = {}
    for lb, p in params_by_label.items():
        channels_dict[lb] = {"To": p.To, "Th": p.Th, "Ti": p.Ti, "Vo": p.Vo, "Fo": p.Fo}

    class_rows = generate_classification_table(channels_dict)
    if class_rows:
        y = _draw_classification_table(c, y, class_rows)
        y -= 10

    # Check if we need a new page
    if y < 200:
        c.showPage()
        y = h - MARGIN_TOP

    # ================================================================
    # 9. COMPLAINTS
    # ================================================================
    if complaints:
        c.setFont("Helvetica-Bold", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(MARGIN_LEFT, y, "Queixas:")
        y -= 12
        c.setFont("Helvetica", FONT_BODY)
        for line in _wrap_text(complaints, CONTENT_WIDTH, "Helvetica", FONT_BODY, c):
            if y < MARGIN_BOTTOM + 60:
                c.showPage()
                y = h - MARGIN_TOP
            c.drawString(MARGIN_LEFT, y, line)
            y -= 11
        y -= 5

    # ================================================================
    # 10. DIAGNOSIS
    # ================================================================
    if diagnosis_text:
        c.setFont("Helvetica-Bold", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(MARGIN_LEFT, y, "Diagnóstico:")
        y -= 12
        c.setFont("Helvetica", FONT_BODY)
        for para in diagnosis_text.split("\n\n"):
            for line in _wrap_text(para.strip(), CONTENT_WIDTH, "Helvetica", FONT_BODY, c):
                if y < MARGIN_BOTTOM + 40:
                    c.showPage()
                    y = h - MARGIN_TOP
                c.drawString(MARGIN_LEFT, y, line)
                y -= 11
            y -= 5

    # ================================================================
    # 11. SIGNATURE
    # ================================================================
    if doctor_name:
        sig_y = max(y - 40, MARGIN_BOTTOM + 20)
        c.setStrokeColorRGB(*COLOR_BLACK)
        c.line(MARGIN_LEFT + 100, sig_y, MARGIN_LEFT + 350, sig_y)
        sig_y -= 12
        c.setFont("Helvetica", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        sig_text = doctor_name
        if doctor_crm:
            sig_text += f" - CRM {doctor_crm}"
        c.drawCentredString(MARGIN_LEFT + 225, sig_y, sig_text)

    c.save()


def _draw_params_table(c: Canvas, y: float, params: Dict[int, 'PPGParameters']) -> float:
    """Draw the parameters table with red coloring for abnormal values."""
    col_labels = ["Parâmetro", "MIE", "MID", "MIE Tq", "MID Tq"]
    col_bytes = [None, 0xDF, 0xE1, 0xE0, 0xE2]
    col_widths = [150, 80, 80, 80, 80]

    rows = [
        ("To (s)", "To"),
        ("Th (s)", "Th"),
        ("Ti (s)", "Ti"),
        ("Vo (%)", "Vo"),
        ("Fo (%s)", "Fo"),
    ]

    # Header
    x = MARGIN_LEFT
    c.setFont("Helvetica-Bold", FONT_TABLE)
    c.setFillColorRGB(*COLOR_BLACK)
    for i, label in enumerate(col_labels):
        c.drawString(x + 3, y, label)
        x += col_widths[i]

    # Separator line below header (with proper spacing)
    y -= 4
    c.setStrokeColorRGB(*COLOR_GRAY)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, y, MARGIN_LEFT + sum(col_widths), y)
    y -= 9

    # Data rows
    c.setFont("Helvetica", FONT_TABLE)
    for row_label, attr in rows:
        x = MARGIN_LEFT
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(x + 3, y, row_label)
        x += col_widths[0]

        for i in range(1, 5):
            lb = col_bytes[i]
            p = params.get(lb)
            val = getattr(p, attr, None) if p else None
            if val is not None:
                text = str(int(val)) if attr == "Fo" else str(val)
                # Red for abnormal To or Vo
                is_abnormal = False
                if attr == "To" and classify_channel(val) != VenousGrade.NORMAL:
                    is_abnormal = True
                elif attr == "Vo" and classify_pump(val) != "normal":
                    is_abnormal = True
                if is_abnormal:
                    c.setFillColorRGB(*COLOR_RED)
                else:
                    c.setFillColorRGB(*COLOR_CYAN)
                c.drawString(x + 10, y, text)
            else:
                c.setFillColorRGB(*COLOR_GRAY)
                c.drawString(x + 10, y, "-")
            x += col_widths[i]

        y -= 11

    return y


def _draw_classification_table(c: Canvas, y: float, rows: list) -> float:
    """Draw the classification summary table with red for all abnormal results."""
    c.setFont("Helvetica-Bold", FONT_TABLE)
    c.setFillColorRGB(*COLOR_BLACK)

    headers = ["Membro", "Condição", "Classificação", "Bomba Muscular"]
    col_widths = [80, 80, 150, 120]
    x = MARGIN_LEFT
    for i, h in enumerate(headers):
        c.drawString(x + 3, y, h)
        x += col_widths[i]

    # Separator line below header (with proper spacing)
    y -= 4
    c.setStrokeColorRGB(*COLOR_GRAY)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, y, MARGIN_LEFT + sum(col_widths), y)
    y -= 9

    c.setFont("Helvetica", FONT_TABLE)
    for row in rows:
        x = MARGIN_LEFT
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(x + 3, y, row["limb"])
        x += col_widths[0]
        c.drawString(x + 3, y, row["tourniquet"])
        x += col_widths[1]

        # Color-code grade: green for Normal, red for ALL abnormal grades
        grade = row["grade"]
        if grade == "Normal":
            c.setFillColorRGB(0, 0.5, 0)
        else:
            c.setFillColorRGB(*COLOR_RED)
        c.drawString(x + 3, y, grade)
        x += col_widths[2]

        # Color-code pump: green for Adequada, red for Patológica
        pump = row["pump"]
        if pump == "Adequada":
            c.setFillColorRGB(0, 0.5, 0)
        else:
            c.setFillColorRGB(*COLOR_RED)
        c.drawString(x + 3, y, pump)

        y -= 11

    return y


def _wrap_text(text: str, max_width: float, font_name: str, font_size: float,
               canvas: Canvas) -> List[str]:
    """Simple word-wrap for text into lines that fit max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if canvas.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _placeholder_png(label_byte: int, w_in: float, h_in: float, dpi: int) -> bytes:
    """Generate a placeholder chart PNG for missing channels."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=dpi)
    desc = LABEL_DESCRIPTIONS.get(label_byte, f"0x{label_byte:02X}")
    ax.text(0.5, 0.5, f"{desc}\nSem dados", ha='center', va='center',
            fontsize=9, color='gray')
    ax.set_xticks([])
    ax.set_yticks([])
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()
