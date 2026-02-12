"""Patient list screen - main screen of the application."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

from ..db.operations import DatabaseOps
from ..db.schema import Patient
from .patient_form import PatientFormDialog


class PatientListView(ttk.Frame):
    """Main patient list view with search and navigation."""

    def __init__(self, parent, db: DatabaseOps, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db

        # Callbacks set by app.py
        self.on_open_patient: Optional[Callable[[Patient], None]] = None
        self.on_capture: Optional[Callable[[], None]] = None
        self.on_settings: Optional[Callable[[], None]] = None

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(top, text="Buscar:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        search_entry = ttk.Entry(top, textvariable=self.search_var, width=25)
        search_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(top, text="Novo Paciente", command=self._new_patient).pack(side=tk.LEFT, padx=10)
        ttk.Button(top, text="Capturar", command=self._on_capture).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Configurações", command=self._on_settings).pack(side=tk.RIGHT, padx=5)

        # Patient list
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("name", "dob", "gender", "last_exam", "n_exams")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("name", text="Nome")
        self.tree.heading("dob", text="Nascimento")
        self.tree.heading("gender", text="Sexo")
        self.tree.heading("last_exam", text="Último Exame")
        self.tree.heading("n_exams", text="Exames")

        self.tree.column("name", width=250)
        self.tree.column("dob", width=100, anchor="center")
        self.tree.column("gender", width=50, anchor="center")
        self.tree.column("last_exam", width=100, anchor="center")
        self.tree.column("n_exams", width=60, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_double_click)

        # Bottom bar
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(bottom, text="Abrir", command=self._open_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="Editar", command=self._edit_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="Excluir", command=self._delete_selected).pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(bottom, text="")
        self.status_label.pack(side=tk.RIGHT)

    def refresh(self):
        """Refresh the patient list from database."""
        query = self.search_var.get().strip()
        patients = self.db.search_patients(query)

        self.tree.delete(*self.tree.get_children())
        for p in patients:
            dob_str = p.date_of_birth.strftime("%d/%m/%Y") if p.date_of_birth else ""
            exams = self.db.list_exams(p.id)
            last_exam = exams[0].exam_date.strftime("%d/%m/%Y") if exams else ""
            n_exams = len(exams)
            self.tree.insert("", "end", iid=str(p.id),
                             values=(p.full_name, dob_str, p.gender or "", last_exam, n_exams))

        self.status_label.config(text=f"{len(patients)} pacientes")

    def _get_selected_patient(self) -> Optional[Patient]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.db.get_patient(int(sel[0]))

    def _new_patient(self):
        PatientFormDialog(self, self.db, on_save=lambda _: self.refresh())

    def _edit_selected(self):
        p = self._get_selected_patient()
        if p:
            PatientFormDialog(self, self.db, patient=p, on_save=lambda _: self.refresh())

    def _delete_selected(self):
        p = self._get_selected_patient()
        if not p:
            return
        if messagebox.askyesno("Confirmar", f"Excluir paciente {p.full_name}?", parent=self):
            self.db.delete_patient(p.id)
            self.refresh()

    def _open_selected(self):
        p = self._get_selected_patient()
        if p and self.on_open_patient:
            self.on_open_patient(p)

    def _on_double_click(self, event):
        self._open_selected()

    def _on_capture(self):
        if self.on_capture:
            self.on_capture(self._get_selected_patient())

    def _on_settings(self):
        if self.on_settings:
            self.on_settings()
