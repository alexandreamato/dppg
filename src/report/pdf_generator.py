"""PDF report generator using reportlab — single-page layout."""

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

BIBLIOGRAPHY = (
    "Amato ACM. Propedêutica vascular. São Paulo: Amato - Instituto de Medicina "
    "Avançada; 2024. Capítulo 8, Propedêutica arterial armada; p. 106-167."
)


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
    """Generate a single-page PDF report."""
    c = Canvas(filepath, pagesize=A4)
    w, h = A4
    y = h - MARGIN_TOP
    dpi = 150

    # ================================================================
    # 1. HEADER
    # ================================================================
    c.setFont("Helvetica-Bold", FONT_TITLE)
    c.setFillColorRGB(*COLOR_CYAN)
    c.drawString(MARGIN_LEFT, y, report_title)
    y -= 14

    c.setFont("Helvetica", FONT_SMALL)
    c.setFillColorRGB(*COLOR_GRAY)
    if clinic_name:
        c.drawString(MARGIN_LEFT, y, clinic_name)
        y -= 9
    if doctor_name:
        label = f"Examinador: {doctor_name}"
        if doctor_crm:
            label += f"  CRM {doctor_crm}"
        c.drawString(MARGIN_LEFT, y, label)
        y -= 9

    y -= 3
    c.setStrokeColorRGB(*COLOR_CYAN)
    c.setLineWidth(1)
    c.line(MARGIN_LEFT, y, w - MARGIN_RIGHT, y)
    y -= 10

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
    y -= 14

    # ================================================================
    # 3. APPLICATION LINE
    # ================================================================
    c.setFont("Helvetica", FONT_BODY)
    c.setFillColorRGB(*COLOR_GRAY)
    c.drawString(MARGIN_LEFT, y, report_app_line)
    c.drawRightString(w - MARGIN_RIGHT, y, f"Data: {exam_date.strftime('%d/%m/%Y')}")
    y -= 14

    # ================================================================
    # 4. PPG CHARTS (2x2 grid) — reduced height for single page
    # ================================================================
    chart_w_pt = CONTENT_WIDTH / 2 - 5
    chart_h_pt = 82
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

        y -= chart_h_pt + 5

    y -= 3

    # ================================================================
    # 5. PARAMETERS TABLE + DIAGNOSTIC CHART (side by side)
    # ================================================================
    params_by_label = {}
    for label_byte, block in blocks.items():
        p = calculate_parameters(block)
        if p:
            params_by_label[label_byte] = p

    # --- Left: params table (narrower columns) ---
    table_col_widths = [95, 55, 55, 55, 55]
    table_w = sum(table_col_widths)
    y_table_start = y
    y_after_table = _draw_params_table(c, y, params_by_label, table_col_widths)

    # --- Right: diagnostic chart ---
    diag_points = []
    labels_order = [(0xDF, "1-MIE"), (0xE1, "2-MID"), (0xE0, "3-MIE Tq"), (0xE2, "4-MID Tq")]
    for lb, lbl in labels_order:
        p = params_by_label.get(lb)
        if p:
            diag_points.append((p.To, p.Vo, lbl))

    diag_gap = 15
    diag_w_pt = CONTENT_WIDTH - table_w - diag_gap
    diag_h_pt = 110
    diag_w_in = diag_w_pt / 72
    diag_h_in = diag_h_pt / 72

    if diag_points:
        diag_png = render_diagnostic_chart(diag_points, diag_w_in, diag_h_in, dpi)
        diag_x = MARGIN_LEFT + table_w + diag_gap
        c.drawImage(ImageReader(io.BytesIO(diag_png)), diag_x,
                     y_table_start - diag_h_pt, diag_w_pt, diag_h_pt)

    y = min(y_after_table, y_table_start - diag_h_pt) - 6

    # ================================================================
    # 6. METHOD TEXT + CLASSIFICATION TABLE (side by side)
    # ================================================================
    # Left: method text (narrower)
    method_w = CONTENT_WIDTH * 0.55
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColorRGB(*COLOR_GRAY)
    wrapped_method = _wrap_text(METHOD_TEXT, method_w, "Helvetica-Oblique", 6.5, c)
    text_obj = c.beginText(MARGIN_LEFT, y)
    text_obj.setFont("Helvetica-Oblique", 6.5)
    text_obj.setFillColorRGB(*COLOR_GRAY)
    for line in wrapped_method:
        text_obj.textLine(line)
    c.drawText(text_obj)
    y_after_method = y - (6.5 + 1.5) * len(wrapped_method)

    # Right: classification table
    channels_dict = {}
    for lb, p in params_by_label.items():
        channels_dict[lb] = {"To": p.To, "Th": p.Th, "Ti": p.Ti, "Vo": p.Vo, "Fo": p.Fo}
    class_rows = generate_classification_table(channels_dict)
    if class_rows:
        class_x = MARGIN_LEFT + CONTENT_WIDTH * 0.58
        y_after_class = _draw_classification_table(c, y, class_rows,
                                                    x_offset=class_x)
    else:
        y_after_class = y

    y = min(y_after_method, y_after_class) - 6

    # ================================================================
    # 7. COMPLAINTS
    # ================================================================
    if complaints:
        c.setFont("Helvetica-Bold", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(MARGIN_LEFT, y, "Queixas:")
        y -= 11
        c.setFont("Helvetica", FONT_BODY)
        for line in _wrap_text(complaints, CONTENT_WIDTH, "Helvetica", FONT_BODY, c):
            c.drawString(MARGIN_LEFT, y, line)
            y -= 10
        y -= 3

    # ================================================================
    # 8. DIAGNOSIS
    # ================================================================
    if diagnosis_text:
        c.setFont("Helvetica-Bold", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(MARGIN_LEFT, y, "Diagnóstico:")
        y -= 11
        c.setFont("Helvetica", FONT_BODY)
        for para in diagnosis_text.split("\n\n"):
            for line in _wrap_text(para.strip(), CONTENT_WIDTH, "Helvetica", FONT_BODY, c):
                c.drawString(MARGIN_LEFT, y, line)
                y -= 10
            y -= 3

    # ================================================================
    # 9. SIGNATURE
    # ================================================================
    if doctor_name:
        sig_y = max(y - 25, MARGIN_BOTTOM + 35)
        c.setStrokeColorRGB(*COLOR_BLACK)
        c.line(MARGIN_LEFT + 100, sig_y, MARGIN_LEFT + 350, sig_y)
        sig_y -= 10
        c.setFont("Helvetica", FONT_BODY)
        c.setFillColorRGB(*COLOR_BLACK)
        sig_text = doctor_name
        if doctor_crm:
            sig_text += f" - CRM {doctor_crm}"
        c.drawCentredString(MARGIN_LEFT + 225, sig_y, sig_text)

    # ================================================================
    # 10. BIBLIOGRAPHY (footer)
    # ================================================================
    bib_y = MARGIN_BOTTOM + 10
    c.setFont("Helvetica-Oblique", 6)
    c.setFillColorRGB(*COLOR_GRAY)
    c.drawString(MARGIN_LEFT, bib_y, f"Ref: {BIBLIOGRAPHY}")

    c.save()


def _draw_params_table(c: Canvas, y: float, params: Dict,
                       col_widths: List[int] = None) -> float:
    """Draw the parameters table with red coloring for abnormal values."""
    col_labels = ["Parâmetro", "MIE", "MID", "MIE Tq", "MID Tq"]
    col_bytes = [None, 0xDF, 0xE1, 0xE0, 0xE2]
    if col_widths is None:
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
        c.drawString(x + 2, y, label)
        x += col_widths[i]

    # Separator line
    y -= 4
    c.setStrokeColorRGB(*COLOR_GRAY)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, y, MARGIN_LEFT + sum(col_widths), y)
    y -= 8

    # Data rows
    c.setFont("Helvetica", FONT_TABLE)
    for row_label, attr in rows:
        x = MARGIN_LEFT
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(x + 2, y, row_label)
        x += col_widths[0]

        for i in range(1, 5):
            lb = col_bytes[i]
            p = params.get(lb)
            val = getattr(p, attr, None) if p else None
            if val is not None:
                text = str(int(val)) if attr == "Fo" else str(val)
                is_abnormal = False
                if attr == "To" and classify_channel(val) != VenousGrade.NORMAL:
                    is_abnormal = True
                elif attr == "Vo" and classify_pump(val) != "normal":
                    is_abnormal = True
                if is_abnormal:
                    c.setFillColorRGB(*COLOR_RED)
                else:
                    c.setFillColorRGB(*COLOR_CYAN)
                c.drawString(x + 8, y, text)
            else:
                c.setFillColorRGB(*COLOR_GRAY)
                c.drawString(x + 8, y, "-")
            x += col_widths[i]

        y -= 10

    return y


def _draw_classification_table(c: Canvas, y: float, rows: list,
                                x_offset: float = None) -> float:
    """Draw the classification summary table with red for all abnormal results."""
    x0 = x_offset if x_offset is not None else MARGIN_LEFT

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColorRGB(*COLOR_BLACK)

    headers = ["Membro", "Cond.", "Classif.", "Bomba"]
    col_widths = [40, 40, 65, 60]
    x = x0
    for i, h in enumerate(headers):
        c.drawString(x + 2, y, h)
        x += col_widths[i]

    y -= 3
    c.setStrokeColorRGB(*COLOR_GRAY)
    c.setLineWidth(0.5)
    c.line(x0, y, x0 + sum(col_widths), y)
    y -= 8

    c.setFont("Helvetica", 7.5)
    for row in rows:
        x = x0
        c.setFillColorRGB(*COLOR_BLACK)
        c.drawString(x + 2, y, row["limb"])
        x += col_widths[0]
        c.drawString(x + 2, y, row["tourniquet"])
        x += col_widths[1]

        grade = row["grade"]
        if grade == "Normal":
            c.setFillColorRGB(0, 0.5, 0)
        else:
            c.setFillColorRGB(*COLOR_RED)
        c.drawString(x + 2, y, grade)
        x += col_widths[2]

        pump = row["pump"]
        if pump == "Adequada":
            c.setFillColorRGB(0, 0.5, 0)
        else:
            c.setFillColorRGB(*COLOR_RED)
        c.drawString(x + 2, y, pump)

        y -= 10

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
