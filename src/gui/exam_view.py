"""Exam visualization screen - shows PPG charts, parameters, and diagnostic chart."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Callable, Dict

from ..db.operations import DatabaseOps
from ..db.schema import Exam, ExamChannel, Patient
from ..models import PPGBlock, PPGParameters
from ..analysis import calculate_parameters
from ..exporters import export_csv, export_json
from .widgets import PPGCanvas, DiagnosticChart, ParametersTable


class ExamView(ttk.Frame):
    """Exam visualization with 4 PPG charts, parameters table, and diagnostic chart."""

    def __init__(self, parent, db: DatabaseOps, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.exam: Optional[Exam] = None
        self.patient: Optional[Patient] = None
        self.blocks: Dict[int, PPGBlock] = {}
        self.params: Dict[int, PPGParameters] = {}

        # Callbacks
        self.on_back: Optional[Callable] = None
        self.on_generate_report: Optional[Callable] = None

        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(top, text="< Voltar", command=self._go_back).pack(side=tk.LEFT)

        self.header_label = ttk.Label(top, text="", font=("Helvetica", 13, "bold"))
        self.header_label.pack(side=tk.LEFT, padx=20)

        # Buttons
        btn_frame = ttk.Frame(top)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Gerar Laudo", command=self._on_report).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="CSV", command=self._export_csv).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="JSON", command=self._export_json).pack(side=tk.LEFT, padx=3)

        # Charts grid (2x2)
        charts_frame = ttk.Frame(self)
        charts_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Grid layout: row0=MIE, row1=MID; col0=s/Tq, col1=c/Tq
        chart_labels = [
            [(0xDF, "MIE s/ Tq"), (0xE0, "MIE c/ Tq")],
            [(0xE1, "MID s/ Tq"), (0xE2, "MID c/ Tq")],
        ]

        self.charts: Dict[int, PPGCanvas] = {}
        for row_idx, row in enumerate(chart_labels):
            for col_idx, (lb, title) in enumerate(row):
                frame = ttk.LabelFrame(charts_frame, text=title, padding=3)
                frame.grid(row=row_idx, column=col_idx, sticky='nsew', padx=3, pady=3)
                canvas = PPGCanvas(frame, height=120)
                canvas.pack(fill=tk.BOTH, expand=True)
                self.charts[lb] = canvas

        charts_frame.columnconfigure(0, weight=1)
        charts_frame.columnconfigure(1, weight=1)
        charts_frame.rowconfigure(0, weight=1)
        charts_frame.rowconfigure(1, weight=1)

        # Bottom area: params table + diagnostic chart
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=5)

        # Parameters table
        params_frame = ttk.LabelFrame(bottom, text="Parâmetros", padding=5)
        params_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.params_table = ParametersTable(params_frame)
        self.params_table.pack(fill=tk.BOTH, expand=True)

        # Diagnostic chart
        diag_frame = ttk.LabelFrame(bottom, text="Diagnóstico Vo% × To(s)", padding=5)
        diag_frame.pack(side=tk.RIGHT, padx=(5, 0))
        self.diag_chart = DiagnosticChart(diag_frame, width=260, height=185)
        self.diag_chart.pack()

    def load_exam(self, exam: Exam, patient: Patient):
        """Load an exam and display all channels."""
        self.exam = exam
        self.patient = patient
        self.blocks.clear()
        self.params.clear()

        self.header_label.config(
            text=f"{patient.full_name} - {exam.exam_date.strftime('%d/%m/%Y')}")

        # Load channels
        for ch in exam.channels:
            block = self.db.channel_to_block(ch)
            self.blocks[ch.label_byte] = block
            p = calculate_parameters(block)
            if p:
                self.params[ch.label_byte] = p

        # Set block data on each chart canvas — actual rendering happens
        # on <Configure> once tkinter assigns the real canvas size.
        for lb, canvas in self.charts.items():
            canvas.delete("all")
            if lb in self.blocks:
                canvas.plot_block(self.blocks[lb])

        # Update parameters table
        self.params_table.update_params(self.params)

        # Update diagnostic chart
        points = []
        labels_order = [(0xDF, "MIE"), (0xE1, "MID"), (0xE0, "MIE Tq"), (0xE2, "MID Tq")]
        for lb, lbl in labels_order:
            p = self.params.get(lb)
            if p:
                points.append((p.To, p.Vo, lbl))
        self.diag_chart.draw(points)

    def _go_back(self):
        if self.on_back:
            self.on_back()

    def _on_report(self):
        if self.on_generate_report and self.exam:
            self.on_generate_report(self.exam)

    def _export_csv(self):
        if not self.blocks:
            return
        blocks_list = list(self.blocks.values())
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"exam_{self.exam.id}.csv", parent=self)
        if filepath:
            try:
                export_csv(blocks_list, filename=filepath)
                messagebox.showinfo("Exportado", f"CSV salvo em {filepath}", parent=self)
            except Exception as e:
                messagebox.showerror("Erro", str(e), parent=self)

    def _export_json(self):
        if not self.blocks:
            return
        blocks_list = list(self.blocks.values())
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=f"exam_{self.exam.id}.json", parent=self)
        if filepath:
            try:
                export_json(blocks_list, filename=filepath)
                messagebox.showinfo("Exportado", f"JSON salvo em {filepath}", parent=self)
            except Exception as e:
                messagebox.showerror("Erro", str(e), parent=self)
