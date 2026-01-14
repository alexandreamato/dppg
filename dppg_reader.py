#!/usr/bin/env python3
"""
D-PPG Vasoquant 1000 Reader
Conecta ao aparelho Elcat Vasoquant 1000 via conversor Serial-WiFi WS1C

Configuração padrão:
- IP: 192.168.0.234
- Porta TCP: 1100
- Baud rate no conversor: 9600, 8N1, sem controle de fluxo
"""

import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
import json


class PPGBlock:
    """Representa um bloco de dados PPG do Vasoquant"""
    def __init__(self, label_byte, samples):
        self.label_byte = label_byte  # Ex: 0xE2 para "â", 0xE1 para "á"
        self.label_char = chr(label_byte) if 0x20 <= label_byte <= 0xFF else f"0x{label_byte:02X}"
        self.samples = samples
        self.timestamp = datetime.now()

    def __repr__(self):
        return f"PPGBlock(L{self.label_char}, {len(self.samples)} amostras)"


class DPPGReader:
    # Configurações padrão
    DEFAULT_HOST = "192.168.0.234"
    DEFAULT_PORT = 1100

    # Constantes do protocolo
    ESC = 0x1B
    SOH = 0x01
    EOT = 0x04
    ACK = 0x06
    DLE = 0x10
    GS = 0x1D

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("D-PPG Vasoquant 1000 Reader")
        self.root.geometry("950x750")

        # Configurações de conexão
        self.host = tk.StringVar(value=self.DEFAULT_HOST)
        self.port = tk.IntVar(value=self.DEFAULT_PORT)

        # Estado da conexão
        self.socket = None
        self.connected = False
        self.printer_online = False
        self.receive_thread = None
        self.running = False
        self.last_data_time = None

        # Buffer para dados recebidos
        self.data_buffer = bytearray()

        # Blocos de dados PPG parseados
        self.ppg_blocks = []

        # Amostras brutas (fallback)
        self.raw_samples = []

        self.setup_ui()

    def setup_ui(self):
        # Frame de configuração
        config_frame = ttk.LabelFrame(self.root, text="Conexão", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(config_frame, text="IP:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(config_frame, textvariable=self.host, width=15).grid(row=0, column=1, padx=5)

        ttk.Label(config_frame, text="Porta:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Entry(config_frame, textvariable=self.port, width=8).grid(row=0, column=3, padx=5)

        self.connect_btn = ttk.Button(config_frame, text="Conectar", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=20)

        self.status_label = ttk.Label(config_frame, text="Desconectado", foreground="red")
        self.status_label.grid(row=0, column=5, padx=10)

        # Frame de dados PPG
        data_frame = ttk.LabelFrame(self.root, text="Dados PPG", padding=10)
        data_frame.pack(fill=tk.X, padx=10, pady=5)

        self.save_btn = ttk.Button(data_frame, text="Salvar CSV", command=self.save_data)
        self.save_btn.pack(side=tk.LEFT, padx=5)

        self.save_json_btn = ttk.Button(data_frame, text="Salvar JSON", command=self.save_json)
        self.save_json_btn.pack(side=tk.LEFT, padx=5)

        self.clear_data_btn = ttk.Button(data_frame, text="Limpar Dados", command=self.clear_data)
        self.clear_data_btn.pack(side=tk.LEFT, padx=5)

        self.clear_log_btn = ttk.Button(data_frame, text="Limpar Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT, padx=5)

        self.blocks_label = ttk.Label(data_frame, text="Blocos: 0", font=("Helvetica", 11, "bold"))
        self.blocks_label.pack(side=tk.LEFT, padx=20)

        self.samples_label = ttk.Label(data_frame, text="Amostras: 0", font=("Helvetica", 11, "bold"))
        self.samples_label.pack(side=tk.LEFT, padx=10)

        # Frame de blocos detectados
        blocks_frame = ttk.LabelFrame(self.root, text="Blocos Detectados", padding=10)
        blocks_frame.pack(fill=tk.X, padx=10, pady=5)

        self.blocks_listbox = tk.Listbox(blocks_frame, height=4, font=("Courier", 10))
        self.blocks_listbox.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.blocks_listbox.bind('<<ListboxSelect>>', self.on_block_select)

        blocks_scroll = ttk.Scrollbar(blocks_frame, orient=tk.VERTICAL, command=self.blocks_listbox.yview)
        blocks_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.blocks_listbox.config(yscrollcommand=blocks_scroll.set)

        # Área de log
        log_frame = ttk.LabelFrame(self.root, text="Log de Comunicação", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, font=("Courier", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configurar tags de cor
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("sent", foreground="green")
        self.log_text.tag_config("received", foreground="black")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("data", foreground="orange")
        self.log_text.tag_config("block", foreground="purple")

        # Frame de visualização de dados PPG
        ppg_frame = ttk.LabelFrame(self.root, text="Visualização PPG", padding=10)
        ppg_frame.pack(fill=tk.X, padx=10, pady=5)

        self.canvas = tk.Canvas(ppg_frame, height=150, bg="white")
        self.canvas.pack(fill=tk.X)

    def log(self, message, tag="info"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def clear_data(self):
        self.ppg_blocks = []
        self.raw_samples = []
        self.data_buffer = bytearray()
        self.blocks_listbox.delete(0, tk.END)
        self.update_labels()
        self.canvas.delete("all")
        self.log("Dados limpos", "info")

    def update_labels(self):
        total_samples = sum(len(b.samples) for b in self.ppg_blocks) + len(self.raw_samples)
        self.blocks_label.config(text=f"Blocos: {len(self.ppg_blocks)}")
        self.samples_label.config(text=f"Amostras: {total_samples}")

    def on_block_select(self, event):
        """Quando usuário seleciona um bloco, mostrar no gráfico"""
        selection = self.blocks_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.ppg_blocks):
                self.plot_block(self.ppg_blocks[idx])

    def plot_block(self, block):
        """Plota um bloco específico no gráfico"""
        self.canvas.delete("all")
        samples = block.samples

        if len(samples) < 2:
            return

        width = self.canvas.winfo_width() or 800
        height = 140

        min_val = min(samples)
        max_val = max(samples)
        val_range = max_val - min_val if max_val != min_val else 1

        # Desenhar grade
        self.canvas.create_line(0, height/2, width, height/2, fill="lightgray", dash=(2, 2))

        # Desenhar sinal PPG
        points = []
        for i, val in enumerate(samples):
            x = (i / len(samples)) * width
            y = height - ((val - min_val) / val_range) * (height - 20) - 10
            points.extend([x, y])

        if len(points) >= 4:
            self.canvas.create_line(points, fill="blue", width=2)

        # Mostrar estatísticas
        self.canvas.create_text(5, 10, anchor="nw",
                                text=f"Bloco L{block.label_char}: {len(samples)} amostras | Min: {min_val} | Max: {max_val}",
                                font=("Courier", 9))

    def save_data(self):
        """Salva todos os blocos em CSV"""
        total_samples = sum(len(b.samples) for b in self.ppg_blocks) + len(self.raw_samples)
        if total_samples == 0:
            self.log("Nenhum dado para salvar!", "error")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ppg_data_{timestamp}.csv"

        try:
            with open(filename, 'w') as f:
                f.write("block,label,sample_index,value\n")

                # Salvar blocos parseados
                for block_idx, block in enumerate(self.ppg_blocks):
                    for sample_idx, val in enumerate(block.samples):
                        f.write(f"{block_idx},L{block.label_char},{sample_idx},{val}\n")

                # Salvar amostras brutas (se houver)
                if self.raw_samples:
                    for sample_idx, val in enumerate(self.raw_samples):
                        f.write(f"raw,raw,{sample_idx},{val}\n")

            self.log(f"Dados salvos em {filename} ({len(self.ppg_blocks)} blocos, {total_samples} amostras)", "info")
        except Exception as e:
            self.log(f"Erro ao salvar: {e}", "error")

    def save_json(self):
        """Salva dados em formato JSON estruturado"""
        if not self.ppg_blocks and not self.raw_samples:
            self.log("Nenhum dado para salvar!", "error")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ppg_data_{timestamp}.json"

        try:
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "blocks": [
                    {
                        "index": i,
                        "label": f"L{b.label_char}",
                        "label_byte": b.label_byte,
                        "timestamp": b.timestamp.isoformat(),
                        "sample_count": len(b.samples),
                        "samples": b.samples
                    }
                    for i, b in enumerate(self.ppg_blocks)
                ],
                "raw_samples": self.raw_samples if self.raw_samples else None
            }

            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)

            self.log(f"JSON salvo em {filename}", "info")
        except Exception as e:
            self.log(f"Erro ao salvar JSON: {e}", "error")

    def toggle_connection(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        try:
            host = self.host.get()
            port = self.port.get()

            self.log(f"Conectando a {host}:{port}...")

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((host, port))
            self.socket.settimeout(0.5)

            self.connected = True
            self.running = True
            self.printer_online = False

            self.connect_btn.config(text="Desconectar")
            self.status_label.config(text="TCP OK - Aguardando...", foreground="orange")
            self.log(f"TCP conectado - aguardando dados do Vasoquant...", "info")

            # Iniciar thread de recepção
            self.receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
            self.receive_thread.start()

        except socket.timeout:
            self.log("Timeout ao conectar - verifique IP e porta", "error")
        except Exception as e:
            self.log(f"Erro ao conectar: {e}", "error")

    def disconnect(self):
        self.running = False
        self.connected = False
        self.printer_online = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        # Processar buffer restante
        if self.data_buffer:
            self.parse_buffer()

        self.connect_btn.config(text="Conectar")
        self.status_label.config(text="Desconectado", foreground="red")
        self.log("Desconectado", "info")

    def receive_loop(self):
        while self.running:
            try:
                data = self.socket.recv(1024)
                if data:
                    self.process_received_data(data)
                elif data == b'':
                    self.root.after(0, self.disconnect)
                    break
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.root.after(0, lambda: self.log(f"Erro de recepção: {e}", "error"))
                break

    def process_received_data(self, data):
        # Atualizar status para "Online" quando receber dados
        self.last_data_time = datetime.now()
        if not self.printer_online:
            self.printer_online = True
            self.root.after(0, lambda: self.status_label.config(text="Printer Online", foreground="green"))
            self.root.after(0, lambda: self.log("Vasoquant conectado!", "info"))

        # Log resumido dos dados
        hex_preview = ' '.join(f'{b:02X}' for b in data[:20])
        if len(data) > 20:
            hex_preview += "..."
        self.root.after(0, lambda: self.log(f"RX ({len(data)} bytes): {hex_preview}", "received"))

        # Auto-ACK: responder SEMPRE com ACK para manter impressora "online"
        if self.socket:
            try:
                self.socket.send(b'\x06')
                if len(data) <= 3:
                    self.root.after(0, lambda: self.log("TX: ACK", "sent"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Erro ao enviar ACK: {e}", "error"))

        # Adicionar ao buffer
        self.data_buffer.extend(data)

        # Tentar parsear blocos completos
        self.root.after(0, self.parse_buffer)

    def parse_buffer(self):
        """Parseia o buffer procurando por blocos de dados PPG completos"""

        while True:
            # Procurar início de bloco: ESC (0x1B) + 'L' (0x4C)
            try:
                esc_pos = self.data_buffer.index(self.ESC)
            except ValueError:
                break  # Não encontrou ESC

            # Verificar se há bytes suficientes para o header
            if esc_pos + 10 > len(self.data_buffer):
                break  # Buffer incompleto

            # Verificar se é início de bloco válido: ESC + 'L' + label + EOT + SOH + GS
            if (self.data_buffer[esc_pos + 1] == 0x4C and  # 'L'
                self.data_buffer[esc_pos + 3] == self.EOT and
                self.data_buffer[esc_pos + 4] == self.SOH and
                self.data_buffer[esc_pos + 5] == self.GS):

                label_byte = self.data_buffer[esc_pos + 2]

                # Extrair tamanho (bytes 7 e 8, little-endian)
                # Formato: GS 00 LL HH onde HHLL é o tamanho
                size_low = self.data_buffer[esc_pos + 7]
                size_high = self.data_buffer[esc_pos + 8]
                num_samples = size_low | (size_high << 8)

                # Calcular posição dos dados
                data_start = esc_pos + 9
                data_end = data_start + (num_samples * 2)

                # Verificar se temos todos os dados
                if data_end > len(self.data_buffer):
                    break  # Buffer incompleto, aguardar mais dados

                # Extrair amostras
                samples = []
                for i in range(data_start, data_end, 2):
                    if i + 1 < len(self.data_buffer):
                        low = self.data_buffer[i]
                        high = self.data_buffer[i + 1]
                        value = low | (high << 8)
                        samples.append(value)

                # Criar bloco
                block = PPGBlock(label_byte, samples)
                self.ppg_blocks.append(block)

                # Atualizar UI
                self.blocks_listbox.insert(tk.END,
                    f"Bloco {len(self.ppg_blocks)}: L{block.label_char} - {len(samples)} amostras")
                self.log(f"Bloco detectado: L{block.label_char} com {len(samples)} amostras", "block")

                # Remover dados processados do buffer
                # Procurar próximo ESC ou fim do bloco
                next_start = data_end
                # Pular metadados até próximo ESC ou fim
                while next_start < len(self.data_buffer) and self.data_buffer[next_start] != self.ESC:
                    next_start += 1

                self.data_buffer = self.data_buffer[next_start:]

                # Atualizar labels e gráfico
                self.update_labels()
                if self.ppg_blocks:
                    self.plot_block(self.ppg_blocks[-1])

            else:
                # Não é um bloco válido, remover o ESC e continuar
                self.data_buffer = self.data_buffer[esc_pos + 1:]

    def update_ppg_plot(self):
        """Atualiza o gráfico com o último bloco ou amostras brutas"""
        if self.ppg_blocks:
            self.plot_block(self.ppg_blocks[-1])
        elif self.raw_samples:
            self.canvas.delete("all")
            samples = self.raw_samples[-300:]
            if len(samples) < 2:
                return

            width = self.canvas.winfo_width() or 800
            height = 140
            min_val = min(samples)
            max_val = max(samples)
            val_range = max_val - min_val if max_val != min_val else 1

            points = []
            for i, val in enumerate(samples):
                x = (i / len(samples)) * width
                y = height - ((val - min_val) / val_range) * (height - 20) - 10
                points.extend([x, y])

            if len(points) >= 4:
                self.canvas.create_line(points, fill="blue", width=2)

    def run(self):
        self.log("D-PPG Vasoquant 1000 Reader", "info")
        self.log("=" * 40, "info")
        self.log("1. Clique em 'Conectar'", "info")
        self.log("2. Aguarde 'printer online' no Vasoquant", "info")
        self.log("3. No Vasoquant, exporte um exame", "info")
        self.log("4. Blocos serão detectados automaticamente", "info")
        self.log("=" * 40, "info")
        self.root.mainloop()

        # Cleanup
        self.running = False
        if self.socket:
            self.socket.close()


if __name__ == "__main__":
    app = DPPGReader()
    app.run()
