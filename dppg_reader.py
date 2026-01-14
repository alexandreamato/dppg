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


class DPPGReader:
    # Configurações padrão que funcionam
    DEFAULT_HOST = "192.168.0.234"
    DEFAULT_PORT = 1100

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("D-PPG Vasoquant 1000 Reader")
        self.root.geometry("900x700")

        # Configurações de conexão
        self.host = tk.StringVar(value=self.DEFAULT_HOST)
        self.port = tk.IntVar(value=self.DEFAULT_PORT)

        # Estado da conexão
        self.socket = None
        self.connected = False
        self.receive_thread = None
        self.running = False

        # Buffer para dados recebidos
        self.data_buffer = bytearray()
        self.ppg_samples = []

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

        self.clear_data_btn = ttk.Button(data_frame, text="Limpar Dados", command=self.clear_data)
        self.clear_data_btn.pack(side=tk.LEFT, padx=5)

        self.clear_log_btn = ttk.Button(data_frame, text="Limpar Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT, padx=5)

        self.samples_label = ttk.Label(data_frame, text="Amostras: 0", font=("Helvetica", 11, "bold"))
        self.samples_label.pack(side=tk.LEFT, padx=20)

        ttk.Label(data_frame, text="(Captura automática ao exportar do Vasoquant)",
                  foreground="gray").pack(side=tk.RIGHT, padx=10)

        # Área de log
        log_frame = ttk.LabelFrame(self.root, text="Log de Comunicação", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Courier", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configurar tags de cor
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("sent", foreground="green")
        self.log_text.tag_config("received", foreground="black")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("data", foreground="orange")

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
        self.ppg_samples = []
        self.data_buffer = bytearray()
        self.samples_label.config(text="Amostras: 0")
        self.canvas.delete("all")
        self.log("Dados limpos", "info")

    def save_data(self):
        if not self.ppg_samples:
            self.log("Nenhum dado para salvar!", "error")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ppg_data_{timestamp}.csv"

        try:
            with open(filename, 'w') as f:
                f.write("sample_index,value\n")
                for i, val in enumerate(self.ppg_samples):
                    f.write(f"{i},{val}\n")
            self.log(f"Dados salvos em {filename} ({len(self.ppg_samples)} amostras)", "info")
        except Exception as e:
            self.log(f"Erro ao salvar: {e}", "error")

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

            self.connect_btn.config(text="Desconectar")
            self.status_label.config(text="Conectado", foreground="green")
            self.log(f"Conectado - aguarde 'printer online' no Vasoquant", "info")

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

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

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

        # Extrair amostras PPG dos dados
        self.extract_ppg_samples(data)

    def extract_ppg_samples(self, data):
        """Extrai amostras PPG dos dados (valores de 16 bits little-endian)"""
        self.data_buffer.extend(data)

        samples_found = []
        i = 0

        while i < len(self.data_buffer) - 1:
            low_byte = self.data_buffer[i]
            high_byte = self.data_buffer[i + 1]
            value = low_byte | (high_byte << 8)

            # Valores PPG típicos: 2000-3500
            if 2000 <= value <= 3500:
                samples_found.append(value)
                i += 2
            else:
                i += 1

        if samples_found:
            self.ppg_samples.extend(samples_found)
            count = len(self.ppg_samples)
            self.root.after(0, lambda: self.samples_label.config(text=f"Amostras: {count}"))
            self.root.after(0, lambda: self.log(f"Extraídas {len(samples_found)} amostras PPG", "data"))
            self.root.after(0, self.update_ppg_plot)

        # Limpar buffer processado
        if len(self.data_buffer) > 100:
            self.data_buffer = self.data_buffer[-10:]

    def update_ppg_plot(self):
        """Atualiza o gráfico PPG"""
        self.canvas.delete("all")

        if len(self.ppg_samples) < 2:
            return

        samples = self.ppg_samples[-300:]  # Últimas 300 amostras
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
                                text=f"Max: {max_val}  Min: {min_val}  Amostras: {len(samples)}",
                                font=("Courier", 9))

    def run(self):
        self.log("D-PPG Vasoquant 1000 Reader", "info")
        self.log("=" * 40, "info")
        self.log("1. Clique em 'Conectar'", "info")
        self.log("2. Aguarde 'printer online' no Vasoquant", "info")
        self.log("3. No Vasoquant, exporte um exame", "info")
        self.log("4. Dados são capturados automaticamente", "info")
        self.log("=" * 40, "info")
        self.root.mainloop()

        # Cleanup
        self.running = False
        if self.socket:
            self.socket.close()


if __name__ == "__main__":
    app = DPPGReader()
    app.run()
