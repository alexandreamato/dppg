"""
Interface gráfica do D-PPG Vasoquant 1000 Reader.

Este módulo implementa a GUI usando Tkinter, incluindo:
- Controles de conexão TCP
- Log de comunicação
- Visualização do sinal PPG
- Tabela de parâmetros quantitativos
- Gráfico diagnóstico Vo x To
"""

import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from typing import List, Optional

from .config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ESTIMATED_SAMPLING_RATE,
    Protocol,
    LABEL_TO_COLUMN,
)
from .models import PPGBlock
from .analysis import calculate_parameters
from .protocol import parse_buffer
from .exporters import export_csv, export_json


class DPPGReaderApp:
    """
    Aplicação GUI para leitura do Vasoquant 1000.

    Gerencia conexão TCP, recepção de dados, parsing do protocolo
    e visualização dos resultados.
    """

    def __init__(self):
        """Inicializa a aplicação."""
        self.root = tk.Tk()
        self.root.title("D-PPG Vasoquant 1000 Reader")
        self.root.geometry("1000x800")

        # Variáveis de configuração
        self.host = tk.StringVar(value=DEFAULT_HOST)
        self.port = tk.IntVar(value=DEFAULT_PORT)

        # Estado da conexão
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.printer_online = False
        self.receive_thread: Optional[threading.Thread] = None
        self.running = False
        self.last_data_time: Optional[datetime] = None

        # Thread safety
        self.data_queue: queue.Queue = queue.Queue()
        self.buffer_lock = threading.Lock()

        # Buffers de dados
        self.data_buffer = bytearray()
        self.ppg_blocks: List[PPGBlock] = []
        self.raw_samples: List[int] = []

        # Opções de visualização
        self.show_ppg_percent = tk.BooleanVar(value=True)

        self._setup_ui()

        # Timer para processar dados da queue
        self.root.after(50, self._process_queue)

    def _setup_ui(self):
        """Configura todos os elementos da interface."""
        self._setup_connection_frame()
        self._setup_data_frame()
        self._setup_blocks_frame()
        self._setup_log_frame()
        self._setup_ppg_frame()
        self._setup_bottom_frame()

    def _setup_connection_frame(self):
        """Configura frame de conexão."""
        frame = ttk.LabelFrame(self.root, text="Conexão", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame, text="IP:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.host, width=15).grid(row=0, column=1, padx=5)

        ttk.Label(frame, text="Porta:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Entry(frame, textvariable=self.port, width=8).grid(row=0, column=3, padx=5)

        self.connect_btn = ttk.Button(frame, text="Conectar", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=20)

        self.status_label = ttk.Label(frame, text="Desconectado", foreground="red")
        self.status_label.grid(row=0, column=5, padx=10)

    def _setup_data_frame(self):
        """Configura frame de controles de dados."""
        frame = ttk.LabelFrame(self.root, text="Dados PPG", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(frame, text="Salvar CSV", command=self._save_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="Salvar JSON", command=self._save_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="Limpar Dados", command=self._clear_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="Limpar Log", command=self._clear_log).pack(side=tk.LEFT, padx=5)

        self.blocks_label = ttk.Label(frame, text="Blocos: 0", font=("Helvetica", 11, "bold"))
        self.blocks_label.pack(side=tk.LEFT, padx=20)

        self.samples_label = ttk.Label(frame, text="Amostras: 0", font=("Helvetica", 11, "bold"))
        self.samples_label.pack(side=tk.LEFT, padx=10)

        ttk.Label(frame, text=f"Taxa: {ESTIMATED_SAMPLING_RATE:.1f} Hz",
                  font=("Helvetica", 10)).pack(side=tk.LEFT, padx=10)

        ttk.Checkbutton(frame, text="%PPG", variable=self.show_ppg_percent,
                        command=self._refresh_plot).pack(side=tk.LEFT, padx=10)

    def _setup_blocks_frame(self):
        """Configura frame de lista de blocos."""
        frame = ttk.LabelFrame(self.root, text="Blocos Detectados", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.blocks_listbox = tk.Listbox(frame, height=4, font=("Courier", 10))
        self.blocks_listbox.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.blocks_listbox.bind('<<ListboxSelect>>', self._on_block_select)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.blocks_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.blocks_listbox.config(yscrollcommand=scrollbar.set)

    def _setup_log_frame(self):
        """Configura frame de log."""
        frame = ttk.LabelFrame(self.root, text="Log de Comunicação", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(frame, height=12, font=("Courier", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Tags de cor
        for tag, color in [("info", "blue"), ("sent", "green"), ("received", "black"),
                           ("error", "red"), ("data", "orange"), ("block", "purple")]:
            self.log_text.tag_config(tag, foreground=color)

    def _setup_ppg_frame(self):
        """Configura frame de visualização PPG."""
        frame = ttk.LabelFrame(self.root, text="Visualização PPG", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.canvas = tk.Canvas(frame, height=150, bg="white")
        self.canvas.pack(fill=tk.X)

    def _setup_bottom_frame(self):
        """Configura frame inferior com tabela e gráfico diagnóstico."""
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tabela de parâmetros (esquerda)
        params_frame = ttk.LabelFrame(frame, text="Parâmetros Quantitativos", padding=10)
        params_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        columns = ("param", "mie", "mid", "mie_tq", "mid_tq")
        self.params_tree = ttk.Treeview(params_frame, columns=columns, show="headings", height=6)

        for col, text, width in [("param", "Parâmetro", 140), ("mie", "MIE", 60),
                                  ("mid", "MID", 60), ("mie_tq", "MIE Tq", 60), ("mid_tq", "MID Tq", 60)]:
            self.params_tree.heading(col, text=text)
            self.params_tree.column(col, width=width, anchor="center" if col != "param" else "w")

        self.params_tree.pack(fill=tk.BOTH, expand=True)

        # Inserir linhas
        for iid, text in [("To", "To (s) - Refilling time"), ("Th", "Th (s) - Half ampl. time"),
                          ("Ti", "Ti (s) - Initial inflow"), ("Vo", "Vo (%) - Pump power"),
                          ("Fo", "Fo (%s) - Pump capacity")]:
            self.params_tree.insert("", "end", iid=iid, values=(text, "-", "-", "-", "-"))

        # Gráfico diagnóstico (direita)
        diag_frame = ttk.LabelFrame(frame, text="Diagnóstico Vo% × To(s)", padding=10)
        diag_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))

        self.diag_canvas = tk.Canvas(diag_frame, width=250, height=180, bg="white")
        self.diag_canvas.pack()

        self._draw_diagnostic_chart()

    # =========================================================================
    # LOGGING
    # =========================================================================

    def _log(self, message: str, tag: str = "info"):
        """Adiciona mensagem ao log."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)

    def _clear_log(self):
        """Limpa o log."""
        self.log_text.delete(1.0, tk.END)

    # =========================================================================
    # GERENCIAMENTO DE DADOS
    # =========================================================================

    def _clear_data(self):
        """Limpa todos os dados capturados."""
        self.ppg_blocks = []
        self.raw_samples = []
        self.data_buffer = bytearray()
        self.blocks_listbox.delete(0, tk.END)
        self._update_labels()
        self.canvas.delete("all")
        self._log("Dados limpos", "info")

    def _update_labels(self):
        """Atualiza labels de contagem."""
        total = sum(len(b.samples) for b in self.ppg_blocks) + len(self.raw_samples)
        self.blocks_label.config(text=f"Blocos: {len(self.ppg_blocks)}")
        self.samples_label.config(text=f"Amostras: {total}")
        self._update_parameters_table()

    def _refresh_blocks_list(self):
        """Atualiza listbox de blocos."""
        self.blocks_listbox.delete(0, tk.END)
        for i, block in enumerate(self.ppg_blocks):
            exam_str = f" (#{block.exam_number} {block.label_desc})" if block.exam_number else f" ({block.label_desc})"
            self.blocks_listbox.insert(tk.END, f"Bloco {i+1}: L{block.label_char} - {len(block.samples)} amostras{exam_str}")

    def _on_block_select(self, event):
        """Handler de seleção de bloco."""
        selection = self.blocks_listbox.curselection()
        if selection and selection[0] < len(self.ppg_blocks):
            self._plot_block(self.ppg_blocks[selection[0]])

    def _refresh_plot(self):
        """Atualiza plot quando opções mudam."""
        selection = self.blocks_listbox.curselection()
        if selection and selection[0] < len(self.ppg_blocks):
            self._plot_block(self.ppg_blocks[selection[0]])

    # =========================================================================
    # EXPORTAÇÃO
    # =========================================================================

    def _save_csv(self):
        """Salva dados em CSV."""
        try:
            filename = export_csv(self.ppg_blocks, self.raw_samples)
            total = sum(len(b.samples) for b in self.ppg_blocks)
            self._log(f"CSV salvo: {filename} ({len(self.ppg_blocks)} blocos, {total} amostras)", "info")
        except ValueError as e:
            self._log(str(e), "error")
        except Exception as e:
            self._log(f"Erro ao salvar CSV: {e}", "error")

    def _save_json(self):
        """Salva dados em JSON."""
        try:
            filename = export_json(self.ppg_blocks, self.raw_samples)
            self._log(f"JSON salvo: {filename}", "info")
        except ValueError as e:
            self._log(str(e), "error")
        except Exception as e:
            self._log(f"Erro ao salvar JSON: {e}", "error")

    # =========================================================================
    # CONEXÃO
    # =========================================================================

    def _toggle_connection(self):
        """Alterna estado de conexão."""
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        """Estabelece conexão TCP."""
        try:
            host = self.host.get()
            port = self.port.get()

            self._log(f"Conectando a {host}:{port}...")

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((host, port))
            self.socket.settimeout(0.5)

            self.connected = True
            self.running = True
            self.printer_online = False

            self.connect_btn.config(text="Desconectar")
            self.status_label.config(text="TCP OK - Aguardando...", foreground="orange")
            self._log(f"TCP conectado - aguardando dados...", "info")

            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()

        except socket.timeout:
            self._log("Timeout ao conectar", "error")
        except Exception as e:
            self._log(f"Erro ao conectar: {e}", "error")

    def _disconnect(self):
        """Encerra conexão."""
        self.running = False
        self.connected = False
        self.printer_online = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.data_buffer:
            self._parse_buffer()

        self.connect_btn.config(text="Conectar")
        self.status_label.config(text="Desconectado", foreground="red")
        self._log("Desconectado", "info")

    def _receive_loop(self):
        """Loop de recepção em thread separada."""
        while self.running:
            try:
                data = self.socket.recv(1024)
                if data:
                    self._process_received_data(data)
                elif data == b'':
                    self.root.after(0, self._disconnect)
                    break
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.root.after(0, lambda: self._log(f"Erro: {e}", "error"))
                break

    def _process_queue(self):
        """Processa dados da queue (chamado pelo timer Tk)."""
        try:
            while True:
                data = self.data_queue.get_nowait()
                with self.buffer_lock:
                    self.data_buffer.extend(data)
                self._parse_buffer()
        except queue.Empty:
            pass
        finally:
            interval = 50 if (self.running or self.connected) else 500
            self.root.after(interval, self._process_queue)

    def _process_received_data(self, data: bytes):
        """Processa dados recebidos (chamado da thread de rede)."""
        self.last_data_time = datetime.now()

        if not self.printer_online:
            self.printer_online = True
            self.root.after(0, lambda: self.status_label.config(text="Printer Online", foreground="green"))
            self.root.after(0, lambda: self._log("Vasoquant conectado!", "info"))

        # Log resumido
        hex_preview = ' '.join(f'{b:02X}' for b in data[:20])
        if len(data) > 20:
            hex_preview += "..."
        self.root.after(0, lambda: self._log(f"RX ({len(data)} bytes): {hex_preview}", "received"))

        # Auto-ACK
        if self.socket:
            try:
                self.socket.send(b'\x06')
                if len(data) <= 3:
                    self.root.after(0, lambda: self._log("TX: ACK", "sent"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Erro ACK: {e}", "error"))

        self.data_queue.put(bytes(data))

    def _parse_buffer(self):
        """Parseia o buffer procurando blocos completos."""
        blocks, remaining = parse_buffer(self.data_buffer)
        self.data_buffer = remaining

        for block in blocks:
            self.ppg_blocks.append(block)

            # Propagar número do exame para blocos anteriores
            if block.exam_number:
                for prev in self.ppg_blocks[:-1]:
                    if prev.exam_number is None:
                        prev.exam_number = block.exam_number
                self._refresh_blocks_list()

            # Log
            if block.metadata_raw:
                meta_hex = ' '.join(f'{b:02X}' for b in block.metadata_raw[:20])
                self._log(f"Metadata L{block.label_char}: {meta_hex}...", "data")

            exam_str = f" (#{block.exam_number} {block.label_desc})" if block.exam_number else f" ({block.label_desc})"
            trim_str = f" [{block.trimmed_count} rem]" if block.trimmed_count > 0 else ""

            if not block.exam_number:
                self.blocks_listbox.insert(tk.END,
                    f"Bloco {len(self.ppg_blocks)}: L{block.label_char} - {len(block.samples)} amostras{exam_str}")

            exam_log = f" | #{block.exam_number}" if block.exam_number else ""
            self._log(f"Bloco: L{block.label_char} {block.label_desc} | {len(block.samples)} amostras{exam_log}{trim_str}", "block")

        if blocks:
            self._update_labels()
            if self.ppg_blocks:
                self._plot_block(self.ppg_blocks[-1])

    # =========================================================================
    # VISUALIZAÇÃO
    # =========================================================================

    def _plot_block(self, block: PPGBlock):
        """Plota um bloco no canvas."""
        self.canvas.delete("all")

        if self.show_ppg_percent.get():
            samples = block.to_ppg_percent()
            y_label, y_format = "% PPG", "{:.1f}"
        else:
            samples = block.samples
            y_label, y_format = "ADC", "{:.0f}"

        if len(samples) < 2:
            return

        width = self.canvas.winfo_width() or 900
        height = 150
        margin_left, margin_bottom = 55, 25
        plot_width = width - margin_left - 20
        plot_height = height - margin_bottom - 15

        min_val, max_val = min(samples), max(samples)
        if self.show_ppg_percent.get():
            min_val, max_val = min(-2, min_val), max(8, max_val)
        val_range = max_val - min_val if max_val != min_val else 1

        duration = block.get_duration_seconds()

        def val_to_y(val):
            return 10 + plot_height - ((val - min_val) / val_range) * plot_height

        def idx_to_x(idx):
            return margin_left + (idx / len(samples)) * plot_width

        # Eixos
        self.canvas.create_line(margin_left, 10, margin_left, height - margin_bottom, fill="gray")
        self.canvas.create_line(margin_left, height - margin_bottom, width - 20, height - margin_bottom, fill="gray")

        # Escala Y
        for i in range(6):
            val = min_val + (val_range * i / 5)
            y = val_to_y(val)
            self.canvas.create_line(margin_left, y, width - 20, y, fill="lightgray", dash=(2, 2))
            self.canvas.create_line(margin_left - 5, y, margin_left, y, fill="gray")
            self.canvas.create_text(margin_left - 8, y, anchor="e", text=y_format.format(val), font=("Courier", 8))

        self.canvas.create_text(10, height / 2, anchor="w", angle=90, text=y_label, font=("Courier", 8), fill="gray")

        # Escala X
        for i in range(7):
            t = duration * i / 6
            x = margin_left + (i / 6) * plot_width
            self.canvas.create_line(x, height - margin_bottom, x, height - margin_bottom + 5, fill="gray")
            self.canvas.create_text(x, height - margin_bottom + 8, anchor="n", text=f"{t:.0f}s", font=("Courier", 8))

        # Sinal
        points = []
        for i, val in enumerate(samples):
            points.extend([idx_to_x(i), val_to_y(val)])
        if len(points) >= 4:
            self.canvas.create_line(points, fill="blue", width=2)

        # Marcadores
        params = calculate_parameters(block)
        if params:
            x_size = 6

            # Pico (vermelho)
            px, py = idx_to_x(params.peak_index), val_to_y(samples[params.peak_index])
            self.canvas.create_line(px - x_size, py - x_size, px + x_size, py + x_size, fill="red", width=2)
            self.canvas.create_line(px - x_size, py + x_size, px + x_size, py - x_size, fill="red", width=2)
            self.canvas.create_text(px, py - 12, anchor="s",
                text=f"Pico ({params.peak_index / ESTIMATED_SAMPLING_RATE:.1f}s)", font=("Courier", 7), fill="red")

            # Fim To (verde)
            to_idx = min(params.To_end_index, len(samples) - 1)
            tx, ty = idx_to_x(to_idx), val_to_y(samples[to_idx])
            self.canvas.create_line(tx - x_size, ty - x_size, tx + x_size, ty + x_size, fill="green", width=2)
            self.canvas.create_line(tx - x_size, ty + x_size, tx + x_size, ty - x_size, fill="green", width=2)
            self.canvas.create_text(tx, ty - 12, anchor="s",
                text=f"To ({to_idx / ESTIMATED_SAMPLING_RATE:.1f}s)", font=("Courier", 7), fill="green")

        # Título
        exam_str = f" | #{block.exam_number}" if block.exam_number else ""
        desc_str = f" ({block.label_desc})" if block.label_desc != "Desconhecido" else ""
        trim_str = f" | {block.trimmed_count} rem." if block.trimmed_count > 0 else ""
        params_str = f" | To={params.To}s Vo={params.Vo}%" if params else ""
        self.canvas.create_text(margin_left + 5, 3, anchor="nw",
            text=f"L{block.label_char}{desc_str}{exam_str} | {duration:.1f}s{trim_str}{params_str}",
            font=("Courier", 9, "bold"))

    def _update_parameters_table(self):
        """Atualiza tabela de parâmetros."""
        params_by_type = {0xDF: None, 0xE1: None, 0xE0: None, 0xE2: None}

        for block in self.ppg_blocks:
            if block.label_byte in params_by_type:
                params = calculate_parameters(block)
                if params:
                    params_by_type[block.label_byte] = params

        mie = params_by_type.get(0xDF)
        mid = params_by_type.get(0xE1)
        mie_tq = params_by_type.get(0xE0)
        mid_tq = params_by_type.get(0xE2)

        def fmt(val):
            return str(val) if val is not None else "-"

        self.params_tree.item("To", values=("To (s) - Refilling time",
            fmt(mie.To if mie else None), fmt(mid.To if mid else None),
            fmt(mie_tq.To if mie_tq else None), fmt(mid_tq.To if mid_tq else None)))
        self.params_tree.item("Th", values=("Th (s) - Half ampl. time",
            fmt(mie.Th if mie else None), fmt(mid.Th if mid else None),
            fmt(mie_tq.Th if mie_tq else None), fmt(mid_tq.Th if mid_tq else None)))
        self.params_tree.item("Ti", values=("Ti (s) - Initial inflow",
            fmt(mie.Ti if mie else None), fmt(mid.Ti if mid else None),
            fmt(mie_tq.Ti if mie_tq else None), fmt(mid_tq.Ti if mid_tq else None)))
        self.params_tree.item("Vo", values=("Vo (%) - Pump power",
            fmt(mie.Vo if mie else None), fmt(mid.Vo if mid else None),
            fmt(mie_tq.Vo if mie_tq else None), fmt(mid_tq.Vo if mid_tq else None)))
        self.params_tree.item("Fo", values=("Fo (%s) - Pump capacity",
            fmt(int(mie.Fo) if mie else None), fmt(int(mid.Fo) if mid else None),
            fmt(int(mie_tq.Fo) if mie_tq else None), fmt(int(mid_tq.Fo) if mid_tq else None)))

        # Atualizar gráfico diagnóstico
        points = []
        for label_byte, name in [(0xDF, "MIE"), (0xE1, "MID"), (0xE0, "MIE Tq"), (0xE2, "MID Tq")]:
            p = params_by_type.get(label_byte)
            if p:
                points.append((p.To, p.Vo, name))
        self._draw_diagnostic_chart(points)

    def _draw_diagnostic_chart(self, points=None):
        """Desenha gráfico diagnóstico Vo% vs To(s)."""
        self.diag_canvas.delete("all")

        width, height = 250, 180
        ml, mb, mt, mr = 35, 25, 15, 10
        pw, ph = width - ml - mr, height - mt - mb
        max_to, max_vo = 50, 15

        def to_x(v): return ml + (v / max_to) * pw
        def vo_y(v): return mt + ph - (v / max_vo) * ph

        # Zonas coloridas
        self.diag_canvas.create_rectangle(to_x(0), vo_y(max_vo), to_x(max_to), vo_y(0), fill="#ccffcc", outline="")
        self.diag_canvas.create_rectangle(to_x(20), vo_y(max_vo), to_x(24), vo_y(2), fill="#ffffcc", outline="")
        self.diag_canvas.create_polygon(to_x(24), vo_y(4), to_x(50), vo_y(2), to_x(24), vo_y(2), fill="#ffffcc", outline="")
        self.diag_canvas.create_rectangle(to_x(0), vo_y(max_vo), to_x(20), vo_y(0), fill="#ffcccc", outline="")
        self.diag_canvas.create_rectangle(to_x(0), vo_y(2), to_x(max_to), vo_y(0), fill="#ffcccc", outline="")

        # Linhas de fronteira
        self.diag_canvas.create_line(to_x(20), vo_y(0), to_x(20), vo_y(max_vo), fill="#cc0000", width=1)
        self.diag_canvas.create_line(to_x(24), vo_y(2), to_x(24), vo_y(max_vo), fill="#cccc00", width=1)
        self.diag_canvas.create_line(to_x(0), vo_y(2), to_x(max_to), vo_y(2), fill="#cc0000", width=1)
        self.diag_canvas.create_line(to_x(24), vo_y(4), to_x(50), vo_y(2), fill="#cccc00", width=1)

        # Labels
        self.diag_canvas.create_text(to_x(10), vo_y(12), text="abnormal", font=("Helvetica", 8), fill="red")
        self.diag_canvas.create_text(to_x(38), vo_y(12), text="normal", font=("Helvetica", 8), fill="green")
        self.diag_canvas.create_text(to_x(30), vo_y(3), text="Border line", font=("Helvetica", 7), fill="#999900")

        # Eixos
        self.diag_canvas.create_line(ml, height - mb, width - mr, height - mb, fill="black")
        self.diag_canvas.create_line(ml, mt, ml, height - mb, fill="black")

        for v in [0, 25, 50]:
            x = to_x(v)
            self.diag_canvas.create_line(x, height - mb, x, height - mb + 4, fill="black")
            self.diag_canvas.create_text(x, height - mb + 12, text=str(v), font=("Helvetica", 8))
        self.diag_canvas.create_text(width // 2, height - 5, text="To s", font=("Helvetica", 8))

        for v in [0, 5, 10, 15]:
            y = vo_y(v)
            self.diag_canvas.create_line(ml - 4, y, ml, y, fill="black")
            self.diag_canvas.create_text(ml - 15, y, text=str(v), font=("Helvetica", 8))
        self.diag_canvas.create_text(12, height // 2, text="Vo%", font=("Helvetica", 8), angle=90)

        # Pontos
        if points:
            colors = ["blue", "red", "green", "orange"]
            for i, (to_val, vo_val, label) in enumerate(points):
                x, y = to_x(to_val), vo_y(vo_val)
                self.diag_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=colors[i % 4], outline="black")
                self.diag_canvas.create_text(x + 10, y - 8, text=str(i + 1), font=("Helvetica", 8, "bold"), fill=colors[i % 4])

    # =========================================================================
    # EXECUÇÃO
    # =========================================================================

    def run(self):
        """Inicia a aplicação."""
        self._log("D-PPG Vasoquant 1000 Reader", "info")
        self._log("=" * 40, "info")
        self._log("1. Clique em 'Conectar'", "info")
        self._log("2. Aguarde 'printer online' no Vasoquant", "info")
        self._log("3. No Vasoquant, exporte um exame", "info")
        self._log("4. Blocos serão detectados automaticamente", "info")
        self._log("=" * 40, "info")

        self.root.mainloop()

        # Cleanup
        self.running = False
        if self.socket:
            self.socket.close()
