"""Patient registration/edit form."""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from typing import Optional, Callable

from ..db.operations import DatabaseOps
from ..db.schema import Patient


class PatientFormDialog(tk.Toplevel):
    """Modal dialog for creating/editing a patient."""

    def __init__(self, parent, db: DatabaseOps, patient: Optional[Patient] = None,
                 on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.db = db
        self.patient = patient
        self.on_save = on_save
        self.result: Optional[Patient] = None

        self.title("Editar Paciente" if patient else "Novo Paciente")
        self.geometry("450x350")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        if patient:
            self._load_patient()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Last name
        ttk.Label(frame, text="Sobrenome:").grid(row=0, column=0, sticky='w', pady=3)
        self.last_name = ttk.Entry(frame, width=35)
        self.last_name.grid(row=0, column=1, columnspan=2, pady=3, sticky='ew')

        # First name
        ttk.Label(frame, text="Nome:").grid(row=1, column=0, sticky='w', pady=3)
        self.first_name = ttk.Entry(frame, width=35)
        self.first_name.grid(row=1, column=1, columnspan=2, pady=3, sticky='ew')

        # Date of birth
        ttk.Label(frame, text="Nascimento:").grid(row=2, column=0, sticky='w', pady=3)
        self.dob = ttk.Entry(frame, width=12)
        self.dob.grid(row=2, column=1, pady=3, sticky='w')
        ttk.Label(frame, text="(DD/MM/AAAA)", foreground="gray").grid(row=2, column=2, sticky='w')

        # Gender
        ttk.Label(frame, text="Sexo:").grid(row=3, column=0, sticky='w', pady=3)
        self.gender = ttk.Combobox(frame, values=["M", "F"], width=5, state="readonly")
        self.gender.grid(row=3, column=1, pady=3, sticky='w')

        # ID number
        ttk.Label(frame, text="Documento:").grid(row=4, column=0, sticky='w', pady=3)
        self.id_number = ttk.Entry(frame, width=20)
        self.id_number.grid(row=4, column=1, columnspan=2, pady=3, sticky='ew')

        # Insurance
        ttk.Label(frame, text="Convênio:").grid(row=5, column=0, sticky='w', pady=3)
        self.insurance = ttk.Entry(frame, width=25)
        self.insurance.grid(row=5, column=1, columnspan=2, pady=3, sticky='ew')

        # Notes
        ttk.Label(frame, text="Observações:").grid(row=6, column=0, sticky='nw', pady=3)
        self.notes = tk.Text(frame, height=3, width=35)
        self.notes.grid(row=6, column=1, columnspan=2, pady=3, sticky='ew')

        frame.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        ttk.Button(btn_frame, text="Salvar", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)

        self.last_name.focus_set()

    def _load_patient(self):
        p = self.patient
        self.last_name.insert(0, p.last_name)
        self.first_name.insert(0, p.first_name)
        if p.date_of_birth:
            self.dob.insert(0, p.date_of_birth.strftime("%d/%m/%Y"))
        if p.gender:
            self.gender.set(p.gender)
        if p.id_number:
            self.id_number.insert(0, p.id_number)
        if p.insurance:
            self.insurance.insert(0, p.insurance)
        if p.notes:
            self.notes.insert("1.0", p.notes)

    def _parse_date(self, text: str) -> Optional[date]:
        text = text.strip()
        if not text:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _save(self):
        last = self.last_name.get().strip()
        first = self.first_name.get().strip()

        if not last or not first:
            messagebox.showwarning("Campos obrigatórios", "Nome e sobrenome são obrigatórios.",
                                   parent=self)
            return

        dob_text = self.dob.get().strip()
        dob = self._parse_date(dob_text)
        if dob_text and not dob:
            messagebox.showwarning("Data inválida", "Formato: DD/MM/AAAA", parent=self)
            return

        kwargs = dict(
            last_name=last,
            first_name=first,
            date_of_birth=dob,
            gender=self.gender.get() or None,
            id_number=self.id_number.get().strip() or None,
            insurance=self.insurance.get().strip() or None,
            notes=self.notes.get("1.0", tk.END).strip() or None,
        )

        if self.patient:
            self.db.update_patient(self.patient.id, **kwargs)
            self.result = self.db.get_patient(self.patient.id)
        else:
            self.result = self.db.add_patient(**kwargs)

        if self.on_save:
            self.on_save(self.result)
        self.destroy()
