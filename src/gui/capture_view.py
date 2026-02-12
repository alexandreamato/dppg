"""Capture view - data acquisition from the Vasoquant 1000 device."""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from typing import Optional, Callable, List

from ..db.operations import DatabaseOps
from ..db.schema import Patient
from ..capture.connection import TCPConnection
from ..capture.receiver import DataReceiver
from ..models import PPGBlock
from ..config import LABEL_DESCRIPTIONS


class CaptureView(ttk.Frame):
    """Capture view for acquiring data from the device."""

    def __init__(self, parent, db: DatabaseOps, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.connection: Optional[TCPConnection] = None
        self.receiver = DataReceiver()
        self.receiver.on_block = self._on_block_received

        # Callbacks
        self.on_back: Optional[Callable] = None
        self.on_exam_saved: Optional[Callable] = None

        # Block groups for auto-grouping
        self._pending_blocks: List[PPGBlock] = []

        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(top, text="< Voltar", command=self._go_back).pack(side=tk.LEFT)

        ttk.Label(top, text="Captura de Dados", font=("Helvetica", 14, "bold")).pack(side=tk.LEFT, padx=20)

        # Connection frame
        conn_frame = ttk.LabelFrame(self, text="Conexão", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(conn_frame, text="IP:").grid(row=0, column=0)
        self.ip_var = tk.StringVar(value=self.db.get_setting("conn_ip", "192.168.0.234"))
        ttk.Entry(conn_frame, textvariable=self.ip_var, width=15).grid(row=0, column=1, padx=5)

        ttk.Label(conn_frame, text="Porta:").grid(row=0, column=2, padx=(10, 0))
        self.port_var = tk.StringVar(value=self.db.get_setting("conn_port", "1100"))
        ttk.Entry(conn_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5)

        self.connect_btn = ttk.Button(conn_frame, text="Conectar", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=20)

        self.status_label = ttk.Label(conn_frame, text="Desconectado", foreground="red")
        self.status_label.grid(row=0, column=5, padx=10)

        # Log
        log_frame = ttk.LabelFrame(self, text="Log de Comunicação", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("block", foreground="purple")
        self.log_text.tag_config("error", foreground="red")

        # Blocks list
        blocks_frame = ttk.LabelFrame(self, text="Blocos Recebidos", padding=5)
        blocks_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.blocks_listbox = tk.Listbox(blocks_frame, height=6, font=("Courier", 10),
                                         selectmode=tk.EXTENDED)
        self.blocks_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        sb = ttk.Scrollbar(blocks_frame, orient=tk.VERTICAL, command=self.blocks_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.blocks_listbox.config(yscrollcommand=sb.set)

        # Save section
        save_frame = ttk.LabelFrame(self, text="Salvar Exame", padding=10)
        save_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(save_frame, text="Paciente:").grid(row=0, column=0, sticky='w')
        self.patient_var = tk.StringVar()
        self.patient_combo = ttk.Combobox(save_frame, textvariable=self.patient_var, width=35)
        self.patient_combo.grid(row=0, column=1, padx=5, sticky='w')
        self._refresh_patients()

        ttk.Button(save_frame, text="Novo Paciente...",
                   command=self._new_patient).grid(row=0, column=2, padx=5)

        ttk.Button(save_frame, text="Salvar Exame",
                   command=self._save_exam).grid(row=0, column=3, padx=20)

        ttk.Button(save_frame, text="Limpar",
                   command=self._clear_blocks).grid(row=0, column=4)

    def _log(self, msg, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self.log_text.see(tk.END)

    def _toggle_connection(self):
        if self.connection and self.connection.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        try:
            host = self.ip_var.get()
            port = int(self.port_var.get())
            self._log(f"Conectando a {host}:{port}...")

            self.connection = TCPConnection(host, port)
            self.connection.on_data = self._on_data
            self.connection.on_disconnect = lambda: self.after(0, self._on_disconnect)
            self.connection.connect()

            self.connect_btn.config(text="Desconectar")
            self.status_label.config(text="Conectado", foreground="green")
            self._log("Conectado - aguardando dados...")
        except Exception as e:
            self._log(f"Erro: {e}", "error")

    def _disconnect(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None
        self.receiver.flush_buffer()
        self.connect_btn.config(text="Conectar")
        self.status_label.config(text="Desconectado", foreground="red")
        self._log("Desconectado")

    def _on_disconnect(self):
        self.connect_btn.config(text="Conectar")
        self.status_label.config(text="Desconectado", foreground="red")
        self._log("Conexão perdida")

    def _on_data(self, data: bytes):
        """Called from connection thread - feed to receiver."""
        self.receiver.feed(data)

    def _on_block_received(self, block: PPGBlock):
        """Called when a complete PPG block is parsed."""
        self._pending_blocks.append(block)
        self.after(0, lambda b=block: self._add_block_to_list(b))

    def _add_block_to_list(self, block: PPGBlock):
        idx = len(self._pending_blocks)
        exam_str = f"#{block.exam_number} " if block.exam_number else ""
        self.blocks_listbox.insert(tk.END,
            f"Bloco {idx}: {exam_str}{block.label_desc} - {len(block.samples)} amostras")
        self._log(f"Bloco: {block.label_desc} | {len(block.samples)} amostras | "
                  f"{'#' + str(block.exam_number) if block.exam_number else 'sem num'}", "block")

    def _refresh_patients(self):
        patients = self.db.list_patients()
        self._patients_map = {}
        values = []
        for p in patients:
            display = f"{p.full_name} (ID: {p.id})"
            values.append(display)
            self._patients_map[display] = p.id
        self.patient_combo['values'] = values

    def select_patient(self, patient):
        """Pre-select a patient in the combo box."""
        display = f"{patient.full_name} (ID: {patient.id})"
        if display in self._patients_map:
            self.patient_var.set(display)

    def _new_patient(self):
        from .patient_form import PatientFormDialog
        def on_save(patient):
            self._refresh_patients()
            display = f"{patient.full_name} (ID: {patient.id})"
            self.patient_var.set(display)
            self._patients_map[display] = patient.id
        PatientFormDialog(self, self.db, on_save=on_save)

    def _save_exam(self):
        if not self._pending_blocks:
            messagebox.showwarning("Sem dados", "Nenhum bloco recebido para salvar.", parent=self)
            return

        patient_display = self.patient_var.get()
        patient_id = self._patients_map.get(patient_display)
        if not patient_id:
            messagebox.showwarning("Paciente", "Selecione um paciente.", parent=self)
            return

        # Get selected blocks or all
        selection = self.blocks_listbox.curselection()
        if selection:
            blocks = [self._pending_blocks[i] for i in selection]
        else:
            blocks = list(self._pending_blocks)

        try:
            exam = self.db.add_exam(patient_id)
            for block in blocks:
                self.db.add_channel_from_block(exam.id, block)

            self._log(f"Exame salvo: {len(blocks)} canais para paciente {patient_display}")
            messagebox.showinfo("Salvo", f"Exame salvo com {len(blocks)} canais.", parent=self)

            if self.on_exam_saved:
                self.on_exam_saved()
        except Exception as e:
            self._log(f"Erro ao salvar: {e}", "error")
            messagebox.showerror("Erro", str(e), parent=self)

    def _clear_blocks(self):
        self._pending_blocks.clear()
        self.receiver.clear()
        self.blocks_listbox.delete(0, tk.END)
        self._log("Blocos limpos")

    def _go_back(self):
        self._disconnect()
        if self.on_back:
            self.on_back()

    def destroy(self):
        self._disconnect()
        super().destroy()
