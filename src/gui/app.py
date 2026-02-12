"""Main application window with navigation between screens."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict

from ..db.operations import DatabaseOps
from ..db.schema import Patient, Exam
from ..models import PPGBlock
from ..analysis import calculate_parameters
from .patient_list import PatientListView
from .capture_view import CaptureView
from .exam_view import ExamView
from .report_editor import ReportEditorView
from .settings_view import SettingsDialog


class DPPGManagerApp:
    """Main application class for D-PPG Manager."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("D-PPG Manager - Vasoquant 1000")
        self.root.geometry("1050x780")

        self.db = DatabaseOps()

        # Container for switching views
        self.container = ttk.Frame(self.root)
        self.container.pack(fill=tk.BOTH, expand=True)

        # Current view
        self._current_view: Optional[ttk.Frame] = None
        self._current_patient: Optional[Patient] = None

        # Show patient list
        self._show_patient_list()

    def _clear_container(self):
        if self._current_view:
            self._current_view.destroy()
            self._current_view = None

    # ================================================================
    # Navigation
    # ================================================================

    def _show_patient_list(self):
        self._clear_container()
        view = PatientListView(self.container, self.db)
        view.on_open_patient = self._open_patient_exams
        view.on_capture = self._show_capture
        view.on_settings = self._show_settings
        view.pack(fill=tk.BOTH, expand=True)
        self._current_view = view

    def _open_patient_exams(self, patient: Patient):
        """Show exam list for a patient. If exams exist, show the most recent."""
        self._current_patient = patient
        exams = self.db.list_exams(patient.id)
        if exams:
            self._show_exam_view(exams[0], patient)
        else:
            messagebox.showinfo("Sem exames",
                                f"Paciente {patient.full_name} não tem exames.\n"
                                "Use 'Capturar' para adquirir dados.",
                                parent=self.root)

    def _show_capture(self, patient: Patient = None):
        self._clear_container()
        view = CaptureView(self.container, self.db)
        view.on_back = self._show_patient_list
        view.on_exam_saved = self._show_patient_list
        if patient:
            view.select_patient(patient)
        view.pack(fill=tk.BOTH, expand=True)
        self._current_view = view

    def _show_exam_view(self, exam: Exam, patient: Patient):
        self._clear_container()
        view = ExamView(self.container, self.db)
        view.on_back = self._show_patient_list
        view.on_generate_report = lambda e: self._show_report_editor(e, patient)
        view.load_exam(exam, patient)
        view.pack(fill=tk.BOTH, expand=True)
        self._current_view = view

    def _show_report_editor(self, exam: Exam, patient: Patient):
        """Open report editor for an exam."""
        # Load blocks from db
        blocks: Dict[int, PPGBlock] = {}
        for ch in exam.channels:
            block = self.db.channel_to_block(ch)
            blocks[ch.label_byte] = block

        self._clear_container()
        view = ReportEditorView(self.container, self.db)
        view.on_back = lambda: self._show_exam_view(exam, patient)
        view.load_exam(exam, patient, blocks)
        view.pack(fill=tk.BOTH, expand=True)
        self._current_view = view

    def _show_settings(self):
        SettingsDialog(self.root, self.db)

    # ================================================================
    # Run
    # ================================================================

    def run(self):
        self.root.mainloop()
        self.db.close()
