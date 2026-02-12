"""Settings dialog for clinic, doctor, connection, and report configuration."""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..db.operations import DatabaseOps


class SettingsDialog(tk.Toplevel):
    """Modal dialog for application settings."""

    def __init__(self, parent, db: DatabaseOps):
        super().__init__(parent)
        self.db = db
        self.title("Configurações")
        self.geometry("500x430")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 4}

        # Clinic section
        clinic_frame = ttk.LabelFrame(self, text="Clínica", padding=10)
        clinic_frame.pack(fill=tk.X, **pad)

        ttk.Label(clinic_frame, text="Nome:").grid(row=0, column=0, sticky='w')
        self.clinic_name = ttk.Entry(clinic_frame, width=45)
        self.clinic_name.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(clinic_frame, text="Registro:").grid(row=1, column=0, sticky='w')
        self.clinic_id = ttk.Entry(clinic_frame, width=45)
        self.clinic_id.grid(row=1, column=1, padx=5, pady=2)

        # Doctor section
        doctor_frame = ttk.LabelFrame(self, text="Médico", padding=10)
        doctor_frame.pack(fill=tk.X, **pad)

        ttk.Label(doctor_frame, text="Nome:").grid(row=0, column=0, sticky='w')
        self.doctor_name = ttk.Entry(doctor_frame, width=45)
        self.doctor_name.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(doctor_frame, text="CRM:").grid(row=1, column=0, sticky='w')
        self.doctor_crm = ttk.Entry(doctor_frame, width=45)
        self.doctor_crm.grid(row=1, column=1, padx=5, pady=2)

        # Report header section
        report_frame = ttk.LabelFrame(self, text="Cabeçalho do Laudo", padding=10)
        report_frame.pack(fill=tk.X, **pad)

        ttk.Label(report_frame, text="Título:").grid(row=0, column=0, sticky='w')
        self.report_title = ttk.Entry(report_frame, width=45)
        self.report_title.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(report_frame, text="Subtítulo:").grid(row=1, column=0, sticky='w')
        self.report_app_line = ttk.Entry(report_frame, width=45)
        self.report_app_line.grid(row=1, column=1, padx=5, pady=2)

        # Connection section
        conn_frame = ttk.LabelFrame(self, text="Conexão", padding=10)
        conn_frame.pack(fill=tk.X, **pad)

        ttk.Label(conn_frame, text="IP:").grid(row=0, column=0, sticky='w')
        self.conn_ip = ttk.Entry(conn_frame, width=20)
        self.conn_ip.grid(row=0, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(conn_frame, text="Porta:").grid(row=0, column=2, sticky='w', padx=(10, 0))
        self.conn_port = ttk.Entry(conn_frame, width=8)
        self.conn_port.grid(row=0, column=3, padx=5, pady=2, sticky='w')

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(btn_frame, text="Salvar", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)

    def _load_settings(self):
        self.clinic_name.insert(0, self.db.get_setting("clinic_name"))
        self.clinic_id.insert(0, self.db.get_setting("clinic_id"))
        self.doctor_name.insert(0, self.db.get_setting("doctor_name"))
        self.doctor_crm.insert(0, self.db.get_setting("doctor_crm"))
        self.report_title.insert(0, self.db.get_setting("report_title", "D-PPG"))
        self.report_app_line.insert(0, self.db.get_setting("report_app_line",
                                                            "D-PPG Digital Photoplethysmography"))
        self.conn_ip.insert(0, self.db.get_setting("conn_ip", "192.168.0.234"))
        self.conn_port.insert(0, self.db.get_setting("conn_port", "1100"))

    def _save(self):
        self.db.set_setting("clinic_name", self.clinic_name.get())
        self.db.set_setting("clinic_id", self.clinic_id.get())
        self.db.set_setting("doctor_name", self.doctor_name.get())
        self.db.set_setting("doctor_crm", self.doctor_crm.get())
        self.db.set_setting("report_title", self.report_title.get())
        self.db.set_setting("report_app_line", self.report_app_line.get())
        self.db.set_setting("conn_ip", self.conn_ip.get())
        self.db.set_setting("conn_port", self.conn_port.get())
        self.destroy()
