"""Reusable widgets for the D-PPG Manager GUI."""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np

from ..config import ESTIMATED_SAMPLING_RATE, ADC_TO_PPG_FACTOR, LABEL_DESCRIPTIONS
from ..models import PPGBlock, PPGParameters
from ..analysis import calculate_parameters, get_diagnostic_zone, bilateral_asymmetry, tourniquet_effect
from ..diagnosis.classifier import classify_channel, classify_pump, VenousGrade


class PPGCanvas(tk.Canvas):
    """Canvas widget that displays a single PPG channel waveform."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault('bg', 'white')
        kwargs.setdefault('height', 150)
        super().__init__(parent, **kwargs)
        self._block: Optional[PPGBlock] = None
        self._last_size = (0, 0)
        self.bind('<Configure>', self._on_configure)

    def _on_configure(self, event):
        """Redraw when canvas is resized."""
        new_size = (event.width, event.height)
        if self._block and new_size != self._last_size and event.width > 10:
            self._last_size = new_size
            self._render()

    def plot_block(self, block: PPGBlock):
        """Set block data and render (or defer if canvas not sized yet)."""
        self._block = block
        self._render()

    def _render(self):
        """Render the PPG plot using current canvas dimensions."""
        block = self._block
        if block is None:
            return

        self.delete("all")

        params = calculate_parameters(block)
        samples = block.samples

        if len(samples) < 2:
            return

        # Convert to %PPG
        baseline = params.baseline_value if params else float(np.median(samples[:10]))
        ppg = [(v - baseline) / ADC_TO_PPG_FACTOR for v in samples]

        width = self.winfo_width()
        height = self.winfo_height()
        if width < 20 or height < 20:
            return

        margin_left = 50
        margin_bottom = 22
        margin_top = 20
        margin_right = 12
        plot_w = width - margin_left - margin_right
        plot_h = height - margin_bottom - margin_top

        if plot_w < 10 or plot_h < 10:
            return

        sr = ESTIMATED_SAMPLING_RATE
        peak_idx = params.peak_index if params else len(samples) // 4

        # Y range: -2 to 8 %PPG
        y_min = min(-2, min(ppg) - 0.5)
        y_max = max(8, max(ppg) + 0.5)
        y_range = y_max - y_min

        def val_to_y(val):
            return margin_top + plot_h - ((val - y_min) / y_range) * plot_h

        def idx_to_x(idx):
            return margin_left + (idx / len(samples)) * plot_w

        # Grid
        self.create_line(margin_left, margin_top, margin_left, height - margin_bottom, fill='gray')
        self.create_line(margin_left, height - margin_bottom, width - margin_right, height - margin_bottom, fill='gray')

        # Y ticks
        for v in range(int(y_min), int(y_max) + 1, 2):
            y = val_to_y(v)
            self.create_line(margin_left, y, width - margin_right, y, fill='lightgray', dash=(2, 2))
            self.create_text(margin_left - 5, y, anchor='e', text=str(v),
                             font=('Helvetica', 9), fill='gray')

        # Baseline line
        y0 = val_to_y(0)
        self.create_line(margin_left, y0, width - margin_right, y0, fill='gray', dash=(3, 3))

        # X ticks (time relative to peak)
        time_range = len(samples) / sr
        tick_interval = 10 if time_range > 40 else 5
        for t in range(int(-peak_idx / sr) - tick_interval,
                       int((len(samples) - peak_idx) / sr) + tick_interval,
                       tick_interval):
            idx = peak_idx + t * sr
            if 0 <= idx < len(samples):
                x = idx_to_x(idx)
                self.create_text(x, height - margin_bottom + 11, text=f"{t}s",
                                 font=('Helvetica', 9), fill='gray')

        # PPG curve
        pts = []
        for i, val in enumerate(ppg):
            pts.extend([idx_to_x(i), val_to_y(val)])
        if len(pts) >= 4:
            self.create_line(pts, fill='blue', width=1.5)

        # Markers
        if params:
            # Peak X marker
            px = idx_to_x(params.peak_index)
            py = val_to_y(ppg[params.peak_index])
            sz = 6
            self.create_line(px - sz, py - sz, px + sz, py + sz, fill='red', width=2)
            self.create_line(px - sz, py + sz, px + sz, py - sz, fill='red', width=2)

            # Endpoint X marker
            end = min(params.To_end_index, len(samples) - 1)
            ex = idx_to_x(end)
            ey = val_to_y(ppg[end])
            self.create_line(ex - sz, ey - sz, ex + sz, ey + sz, fill='green', width=2)
            self.create_line(ex - sz, ey + sz, ex + sz, ey - sz, fill='green', width=2)

            # Parameters annotation
            info = f"To={params.To}s  Vo={params.Vo}%"
            self.create_text(width - margin_right - 5, margin_top + 2, anchor='ne',
                             text=info, font=('Helvetica', 9), fill='#555555')

        # Label
        desc = block.label_desc
        exam_str = f"  #{block.exam_number}" if block.exam_number else ""
        self.create_text(margin_left + 5, margin_top + 2, anchor='nw',
                         text=f"{desc}{exam_str}",
                         font=('Helvetica', 10, 'bold'), fill='darkcyan')


class DiagnosticChart(tk.Canvas):
    """Canvas widget for the Vo% x To diagnostic scatter chart."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault('bg', 'white')
        kwargs.setdefault('width', 280)
        kwargs.setdefault('height', 210)
        super().__init__(parent, **kwargs)
        self._points = None
        self._last_size = (0, 0)
        self.bind('<Configure>', self._on_configure)
        self.draw()

    def _on_configure(self, event):
        new_size = (event.width, event.height)
        if new_size != self._last_size and event.width > 10:
            self._last_size = new_size
            self.draw(self._points)

    def draw(self, points=None):
        """Draw the diagnostic chart with optional data points."""
        self._points = points
        self.delete("all")

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 30 or h < 30:
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()

        ml, mb, mt, mr = 40, 28, 15, 12
        pw = w - ml - mr
        ph = h - mt - mb
        max_to, max_vo = 50, 15

        if pw < 10 or ph < 10:
            return

        def to_x(v):
            return ml + (v / max_to) * pw

        def vo_y(v):
            return mt + ph - (v / max_vo) * ph

        # Zones
        self.create_rectangle(to_x(0), vo_y(max_vo), to_x(max_to), vo_y(0),
                              fill="#ccffcc", outline="")
        self.create_rectangle(to_x(20), vo_y(max_vo), to_x(24), vo_y(2),
                              fill="#ffffcc", outline="")
        self.create_polygon(to_x(24), vo_y(4), to_x(50), vo_y(2), to_x(24), vo_y(2),
                            fill="#ffffcc", outline="")
        self.create_rectangle(to_x(0), vo_y(max_vo), to_x(20), vo_y(0),
                              fill="#ffcccc", outline="")
        self.create_rectangle(to_x(0), vo_y(2), to_x(max_to), vo_y(0),
                              fill="#ffcccc", outline="")

        # Borders
        self.create_line(to_x(20), vo_y(0), to_x(20), vo_y(max_vo), fill="#cc0000")
        self.create_line(to_x(24), vo_y(2), to_x(24), vo_y(max_vo), fill="#cccc00")
        self.create_line(to_x(0), vo_y(2), to_x(max_to), vo_y(2), fill="#cc0000")
        self.create_line(to_x(24), vo_y(4), to_x(50), vo_y(2), fill="#cccc00")

        # Zone labels
        self.create_text(to_x(10), vo_y(12), text="abnormal",
                         font=("Helvetica", 10), fill="red")
        self.create_text(to_x(38), vo_y(12), text="normal",
                         font=("Helvetica", 10), fill="green")

        # Axes
        self.create_line(ml, h - mb, w - mr, h - mb, fill="black")
        self.create_line(ml, mt, ml, h - mb, fill="black")

        for v in [0, 25, 50]:
            x = to_x(v)
            self.create_line(x, h - mb, x, h - mb + 4, fill="black")
            self.create_text(x, h - mb + 14, text=str(v), font=("Helvetica", 10))
        self.create_text(w // 2, h - 3, text="To (s)", font=("Helvetica", 10))

        for v in [0, 5, 10, 15]:
            y = vo_y(v)
            self.create_line(ml - 4, y, ml, y, fill="black")
            self.create_text(ml - 8, y, anchor='e', text=str(v), font=("Helvetica", 10))
        self.create_text(14, h // 2, text="Vo%", font=("Helvetica", 10), angle=90)

        # Points
        if points:
            colors = ["blue", "red", "green", "orange"]
            for i, (to_val, vo_val, label) in enumerate(points):
                x, y = to_x(to_val), vo_y(vo_val)
                color = colors[i % len(colors)]
                self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=color, outline="black")
                self.create_text(x + 12, y - 10, text=f"{i+1} {label}",
                                 font=("Helvetica", 9, "bold"), fill=color, anchor='w')


class ParametersTable(ttk.Frame):
    """Widget displaying PPG parameters in a grid with per-cell red coloring for abnormal values."""

    _COL_HEADERS = ["Parâmetro", "MIE", "MID", "MIE Tq", "MID Tq"]
    _ROW_PARAMS = [
        ("To", "To (s)"),
        ("Th", "Th (s)"),
        ("Ti", "Ti (s)"),
        ("Vo", "Vo (%)"),
        ("Fo", "Fo (%s)"),
        ("tau", "\u03c4 (s)"),
    ]
    _COL_LABELS = [0xDF, 0xE1, 0xE0, 0xE2]  # MIE, MID, MIE Tq, MID Tq

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        font_header = ("Helvetica", 11, "bold")
        font_cell = ("Helvetica", 11)

        self._grid = tk.Frame(self, bg='white')
        self._grid.pack(fill=tk.BOTH, expand=True)

        # Header row
        for col, text in enumerate(self._COL_HEADERS):
            anchor = 'w' if col == 0 else 'center'
            lbl = tk.Label(self._grid, text=text, font=font_header, bg='white',
                           anchor=anchor, padx=8, pady=3)
            lbl.grid(row=0, column=col, sticky='ew')

        # Separator
        sep = ttk.Separator(self._grid, orient='horizontal')
        sep.grid(row=1, column=0, columnspan=5, sticky='ew', pady=1)

        # Data cells (store references for updating)
        self._cells = {}  # (attr, col_idx) -> Label
        for row_idx, (attr, label_text) in enumerate(self._ROW_PARAMS):
            r = row_idx + 2  # offset for header + separator
            param_lbl = tk.Label(self._grid, text=label_text, font=font_cell, bg='white',
                                 anchor='w', padx=8, pady=2)
            param_lbl.grid(row=r, column=0, sticky='ew')
            for col_idx in range(4):
                cell = tk.Label(self._grid, text="-", font=font_cell, bg='white',
                                fg='gray', anchor='center', padx=8, pady=2)
                cell.grid(row=r, column=col_idx + 1, sticky='ew')
                self._cells[(attr, col_idx)] = cell

        # Column weights
        self._grid.columnconfigure(0, weight=2)
        for c in range(1, 5):
            self._grid.columnconfigure(c, weight=1)

    def update_params(self, params_by_label: dict):
        """Update table from dict {label_byte: PPGParameters}."""
        for attr, _ in self._ROW_PARAMS:
            for col_idx, lb in enumerate(self._COL_LABELS):
                cell = self._cells[(attr, col_idx)]
                p = params_by_label.get(lb)
                if p:
                    v = getattr(p, attr, None)
                    if v is not None:
                        text = str(int(v)) if attr == "Fo" else str(v)
                        # Red for abnormal To or Vo; tau always cyan
                        is_abnormal = False
                        if attr == "To" and classify_channel(v) != VenousGrade.NORMAL:
                            is_abnormal = True
                        elif attr == "Vo" and classify_pump(v) != "normal":
                            is_abnormal = True
                        cell.config(text=text, fg='red' if is_abnormal else '#008099')
                    else:
                        cell.config(text="-", fg='gray')
                else:
                    cell.config(text="-", fg='gray')


class AdvancedAnalysisPanel(ttk.LabelFrame):
    """Panel showing bilateral asymmetry and tourniquet effect."""

    # Label bytes: MIE s/Tq, MID s/Tq, MIE c/Tq, MID c/Tq
    _MIE_SEM = 0xDF
    _MID_SEM = 0xE1
    _MIE_COM = 0xE0
    _MID_COM = 0xE2

    def __init__(self, parent, **kwargs):
        kwargs.setdefault('text', 'Análise Avançada')
        super().__init__(parent, **kwargs)
        self._text_widget = tk.Text(
            self, wrap=tk.WORD, height=8, font=("Helvetica", 10),
            bg='#f9f9f9', relief=tk.FLAT, state=tk.DISABLED,
            padx=6, pady=4,
        )
        self._text_widget.pack(fill=tk.BOTH, expand=True)
        self._text_widget.tag_configure('header', font=("Helvetica", 10, "bold"))
        self._text_widget.tag_configure('significant', foreground='red')
        self._text_widget.tag_configure('normal', foreground='#008099')

    def update_analysis(self, params: dict):
        """Update from dict {label_byte: PPGParameters}."""
        self._text_widget.config(state=tk.NORMAL)
        self._text_widget.delete('1.0', tk.END)

        has_content = False

        # --- Bilateral Asymmetry ---
        p_mie = params.get(self._MIE_SEM)
        p_mid = params.get(self._MID_SEM)
        if p_mie and p_mid:
            asym = bilateral_asymmetry(p_mie, p_mid)
            if asym:
                has_content = True
                self._text_widget.insert(tk.END, "Assimetria Bilateral\n", 'header')
                for attr, pct in asym.items():
                    val_mie = getattr(p_mie, attr)
                    val_mid = getattr(p_mid, attr)
                    unit = "s" if attr in ("To", "tau") else "%"
                    label = "\u03c4" if attr == "tau" else attr
                    tag = 'significant' if pct > 20 else 'normal'
                    severity = ""
                    if pct > 40:
                        severity = " (muito significativa)"
                    elif pct > 20:
                        severity = " (significativa)"
                    line = (f"  {label}: MIE {val_mie}{unit} vs MID {val_mid}{unit}"
                            f" \u2192 {pct}%{severity}\n")
                    self._text_widget.insert(tk.END, line, tag)
                self._text_widget.insert(tk.END, "\n")

        # --- Tourniquet Effect ---
        tq_data = []
        for limb, lb_sem, lb_com in [("MIE", self._MIE_SEM, self._MIE_COM),
                                      ("MID", self._MID_SEM, self._MID_COM)]:
            p_sem = params.get(lb_sem)
            p_com = params.get(lb_com)
            if p_sem and p_com:
                eff = tourniquet_effect(p_sem, p_com)
                if eff:
                    tq_data.append((limb, p_sem, p_com, eff))

        if tq_data:
            has_content = True
            self._text_widget.insert(tk.END, "Efeito do Garrote\n", 'header')
            for limb, p_sem, p_com, eff in tq_data:
                to_pct = eff.get("To_pct", 0)
                sign = "+" if to_pct >= 0 else ""
                if abs(to_pct) > 15:
                    if to_pct > 0:
                        interp = "melhora significativa"
                    else:
                        interp = "piora significativa"
                    tag = 'significant' if to_pct < 0 else 'normal'
                else:
                    interp = "sem alteração significativa"
                    tag = 'normal'
                line = (f"  {limb}: To {p_sem.To}s \u2192 {p_com.To}s "
                        f"({sign}{to_pct}%) {interp}\n")
                self._text_widget.insert(tk.END, line, tag)

        if not has_content:
            self._text_widget.insert(tk.END, "Dados insuficientes para análise avançada.\n")

        self._text_widget.config(state=tk.DISABLED)
