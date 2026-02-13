"""Report editor screen - complaints, diagnosis text, and PDF generation."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Callable, Dict
from datetime import date

from ..db.operations import DatabaseOps
from ..db.schema import Exam, Patient
from ..models import PPGBlock, PPGParameters
from ..analysis import calculate_parameters
from ..diagnosis.text_generator import generate_diagnosis
from ..report.pdf_generator import generate_report_pdf


class ReportEditorView(ttk.Frame):
    """Report editor with complaints, auto-generated diagnosis, and PDF generation."""

    def __init__(self, parent, db: DatabaseOps, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.exam: Optional[Exam] = None
        self.patient: Optional[Patient] = None
        self.blocks: Dict[int, PPGBlock] = {}

        # Callbacks
        self.on_back: Optional[Callable] = None

        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(top, text="< Voltar", command=self._go_back).pack(side=tk.LEFT)
        self.header_label = ttk.Label(top, text="Editor de Laudo", font=("Helvetica", 13, "bold"))
        self.header_label.pack(side=tk.LEFT, padx=20)

        # Complaints
        complaints_frame = ttk.LabelFrame(self, text="Queixas do Paciente", padding=5)
        complaints_frame.pack(fill=tk.X, padx=10, pady=5)

        self.complaints_text = tk.Text(complaints_frame, height=3, font=("Helvetica", 10))
        self.complaints_text.pack(fill=tk.X)

        # Diagnosis
        diag_frame = ttk.LabelFrame(self, text="Diagnóstico", padding=5)
        diag_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_bar = ttk.Frame(diag_frame)
        btn_bar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_bar, text="Regenerar Texto", command=self._regenerate).pack(side=tk.LEFT)

        self.diagnosis_text = tk.Text(diag_frame, font=("Courier", 10), wrap=tk.WORD)
        self.diagnosis_text.pack(fill=tk.BOTH, expand=True)

        # Bottom buttons
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(bottom, text="Salvar Textos", command=self._save_texts).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="Gerar PDF", command=self._generate_pdf).pack(side=tk.RIGHT, padx=5)

    def load_exam(self, exam: Exam, patient: Patient, blocks: Dict[int, PPGBlock]):
        """Load exam data for report editing."""
        self.exam = exam
        self.patient = patient
        self.blocks = blocks

        self.header_label.config(
            text=f"Laudo - {patient.full_name} - {exam.exam_date.strftime('%d/%m/%Y')}")

        # Load existing text or generate
        self.complaints_text.delete("1.0", tk.END)
        if exam.complaints:
            self.complaints_text.insert("1.0", exam.complaints)

        self.diagnosis_text.delete("1.0", tk.END)
        if exam.diagnosis_text:
            self.diagnosis_text.insert("1.0", exam.diagnosis_text)
        else:
            self._regenerate()

    def _regenerate(self):
        """Regenerate diagnosis text from channel parameters."""
        channels = {}
        params_objects = {}
        for lb, block in self.blocks.items():
            p = calculate_parameters(block)
            if p:
                channels[lb] = {"To": p.To, "Th": p.Th, "Ti": p.Ti, "Vo": p.Vo, "Fo": p.Fo}
                params_objects[lb] = p

        text = generate_diagnosis(channels, params_objects=params_objects)
        self.diagnosis_text.delete("1.0", tk.END)
        self.diagnosis_text.insert("1.0", text)

    def _save_texts(self):
        """Save complaints and diagnosis to database."""
        if not self.exam:
            return
        complaints = self.complaints_text.get("1.0", tk.END).strip()
        diagnosis = self.diagnosis_text.get("1.0", tk.END).strip()
        self.db.update_exam(self.exam.id, complaints=complaints, diagnosis_text=diagnosis)
        messagebox.showinfo("Salvo", "Textos salvos.", parent=self)

    def _generate_pdf(self):
        """Generate PDF report."""
        if not self.exam or not self.patient:
            return

        # Save texts first
        self._save_texts()

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"laudo_{self.patient.last_name}_{self.exam.exam_date.strftime('%Y%m%d')}.pdf",
            parent=self,
        )
        if not filepath:
            return

        try:
            settings = self.db.get_all_settings()
            dob_str = (self.patient.date_of_birth.strftime("%d/%m/%Y")
                       if self.patient.date_of_birth else "")

            generate_report_pdf(
                filepath=filepath,
                patient_name=self.patient.full_name,
                patient_dob=dob_str,
                patient_gender=self.patient.gender,
                patient_id=self.patient.id_number,
                exam_date=self.exam.exam_date,
                blocks=self.blocks,
                complaints=self.complaints_text.get("1.0", tk.END).strip(),
                diagnosis_text=self.diagnosis_text.get("1.0", tk.END).strip(),
                clinic_name=settings.get("clinic_name", ""),
                doctor_name=settings.get("doctor_name", ""),
                doctor_crm=settings.get("doctor_crm", ""),
                report_title=settings.get("report_title", "D-PPG"),
                report_app_line=settings.get("report_app_line",
                                             "D-PPG Digital Photoplethysmography"),
            )
            messagebox.showinfo("PDF Gerado", f"Laudo salvo em:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao gerar PDF:\n{e}", parent=self)

    def _go_back(self):
        if self.on_back:
            self.on_back()
