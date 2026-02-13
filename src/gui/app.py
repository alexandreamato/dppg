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

APP_VERSION = "1.0"
AUTHOR_NAME = "Dr. Alexandre Amato"


class DPPGManagerApp:
    """Main application class for D-PPG Manager."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"D-PPG Manager - Vasoquant 1000 - {AUTHOR_NAME}")
        self.root.geometry("1050x780")

        self.db = DatabaseOps()

        # Menu bar
        self._build_menu()

        # Container for switching views
        self.container = ttk.Frame(self.root)
        self.container.pack(fill=tk.BOTH, expand=True)

        # Current view
        self._current_view: Optional[ttk.Frame] = None
        self._current_patient: Optional[Patient] = None

        # Show patient list
        self._show_patient_list()

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Configurações", command=self._show_settings)
        menubar.add_cascade(label="Editar", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Sobre", command=self._show_about)
        menubar.add_cascade(label="Ajuda", menu=help_menu)

        self.root.config(menu=menubar)

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

    def _show_about(self):
        about = tk.Toplevel(self.root)
        about.title("Sobre")
        about.resizable(False, False)
        about.transient(self.root)
        about.grab_set()

        frame = ttk.Frame(about, padding=20)
        frame.pack()

        ttk.Label(frame, text="D-PPG Manager", font=("Helvetica", 16, "bold")).pack(pady=(0, 5))
        ttk.Label(frame, text=f"Versao {APP_VERSION}", font=("Helvetica", 10)).pack()
        ttk.Label(frame, text="Vasoquant 1000 Digital Photoplethysmography",
                  font=("Helvetica", 10)).pack(pady=(5, 10))

        sep = ttk.Separator(frame, orient="horizontal")
        sep.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text=AUTHOR_NAME, font=("Helvetica", 12, "bold")).pack(pady=(5, 2))
        ttk.Label(frame, text="Instituto Amato de Medicina Avancada",
                  font=("Helvetica", 10)).pack()
        ttk.Label(frame, text="software.amato.com.br", font=("Helvetica", 9),
                  foreground="gray").pack(pady=(2, 10))

        ttk.Button(frame, text="OK", command=about.destroy).pack()

        # Center on parent
        about.update_idletasks()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        px = self.root.winfo_x()
        py = self.root.winfo_y()
        aw = about.winfo_width()
        ah = about.winfo_height()
        about.geometry(f"+{px + (pw - aw) // 2}+{py + (ph - ah) // 2}")

    # ================================================================
    # Run
    # ================================================================

    def run(self):
        self.root.mainloop()
        self.db.close()
