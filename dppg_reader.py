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
import queue
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List
import numpy as np
import json
import os


class NumpyJSONEncoder(json.JSONEncoder):
    """Encoder JSON que converte automaticamente tipos numpy para tipos Python nativos"""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, (np.bool_, np.bool8)):
            return bool(obj)
        if hasattr(obj, 'item'):
            return obj.item()
        return super().default(obj)


# Mapeamento de labels para descrições (baseado no laudo oficial)
LABEL_DESCRIPTIONS = {
    0xE2: "MID c/ Tq",   # Membro Inferior Direito, com Tourniquet
    0xE1: "MID s/ Tq",   # Membro Inferior Direito, sem Tourniquet
    0xE0: "MIE c/ Tq",   # Membro Inferior Esquerdo, com Tourniquet
    0xDF: "MIE s/ Tq",   # Membro Inferior Esquerdo, sem Tourniquet
    0xDE: "Canal 5",     # A ser identificado
}

# Taxa de amostragem (Hz)
# CONFIRMADO pela análise do protocolo:
# - Exercício: 8 movimentos em 16 segundos = 64 amostras
# - 64 amostras / 16 segundos = 4 Hz
# Nota: Os 32.5 Hz no binário são a taxa interna do hardware,
# mas os dados exportados são a 4 Hz.
ESTIMATED_SAMPLING_RATE = 4.0  # Hz

# Fator de conversão ADC para %PPG (calibrado com laudo oficial)
ADC_TO_PPG_FACTOR = 27.0  # ~27 unidades ADC = 1% PPG


@dataclass
class PPGParameters:
    """Parâmetros quantitativos calculados da curva D-PPG"""
    To: float  # Venous refilling time (s) - tempo de reenchimento venoso
    Th: float  # Venous half amplitude time (s) - tempo de meia amplitude
    Ti: float  # Initial inflow time (s) - tempo de influxo inicial
    Vo: float  # Venous pump power (%) - potência da bomba venosa
    Fo: float  # Venous pump capacity (%·s) - capacidade da bomba venosa

    # Índices para debugging/visualização
    peak_index: int = 0           # Índice do pico máximo (momento zero)
    To_end_index: int = 0         # Índice do fim do To (retorno ao baseline)
    exercise_start_index: int = 0 # Índice do início do exercício
    baseline_value: float = 0.0   # Valor do baseline em ADC
    peak_value: float = 0.0       # Valor do pico em ADC


class PPGBlock:
    """Representa um bloco de dados PPG do Vasoquant"""
    def __init__(self, label_byte, samples, exam_number=None, metadata_raw=None):
        self.label_byte = label_byte  # Ex: 0xE2 para "â", 0xE1 para "á"
        self.label_char = chr(label_byte) if 0x20 <= label_byte <= 0xFF else f"0x{label_byte:02X}"
        self.label_desc = LABEL_DESCRIPTIONS.get(label_byte, "Desconhecido")
        self.samples_raw = samples  # Amostras originais
        self.samples = self._trim_trailing_artifacts(samples)  # Amostras limpas
        self.exam_number = exam_number  # Número do exame extraído dos metadados
        self.metadata_raw = metadata_raw  # Bytes brutos de metadados para análise
        self.timestamp = datetime.now()
        self.trimmed_count = len(samples) - len(self.samples)

    def _trim_trailing_artifacts(self, samples):
        """Remove artefatos do final do bloco (bytes de controle interpretados como dados)"""
        if len(samples) < 15:
            return samples

        # Usar dados principais (excluindo últimos 5) para calcular estatísticas
        main_samples = samples[:-5]
        if len(main_samples) < 10:
            return samples

        # Usar mediana e IQR para ser mais robusto contra outliers
        sorted_main = sorted(main_samples)
        n = len(sorted_main)
        median = sorted_main[n // 2]
        q1 = sorted_main[n // 4]
        q3 = sorted_main[3 * n // 4]
        iqr = q3 - q1 if q3 > q1 else 50  # IQR mínimo de 50

        # Threshold: valores fora de 2.5 * IQR da mediana são outliers
        lower_bound = median - 2.5 * iqr
        upper_bound = median + 2.5 * iqr

        # Verificar os últimos 5 valores - encontrar o primeiro outlier
        trim_from = len(samples)
        for i in range(len(samples) - 5, len(samples)):
            val = samples[i]
            if val < lower_bound or val > upper_bound:
                trim_from = i
                break

        # Se encontrou outlier, remover desse ponto em diante
        if trim_from < len(samples):
            return samples[:trim_from]

        # Verificação adicional: grande variação nos últimos valores indica artefatos
        last_5 = samples[-5:]
        last_range = max(last_5) - min(last_5)
        main_range = max(main_samples[-20:]) - min(main_samples[-20:]) if len(main_samples) >= 20 else iqr

        # Se a variação dos últimos 5 for muito maior que a variação recente, são artefatos
        if last_range > main_range * 2:
            # Encontrar onde começa a instabilidade
            for i in range(len(samples) - 5, len(samples)):
                if abs(samples[i] - median) > 1.5 * iqr:
                    return samples[:i]

        return samples

    def to_ppg_percent(self):
        """Converte amostras ADC para %PPG (baseado no laudo oficial)"""
        if not self.samples:
            return []
        # Baseline = primeiros 10 valores (antes da deflexão venosa)
        baseline = sum(self.samples[:10]) / min(10, len(self.samples))
        # Fator de conversão: ~27 unidades ADC = 1% PPG (estimado do laudo)
        return [(val - baseline) / ADC_TO_PPG_FACTOR for val in self.samples]

    def get_duration_seconds(self):
        """Retorna duração estimada do bloco em segundos"""
        return len(self.samples) / ESTIMATED_SAMPLING_RATE

    def calculate_parameters(self) -> Optional[PPGParameters]:
        """
        Calcula os parâmetros quantitativos da curva D-PPG.

        MÉTODO: Detecção direta de cruzamento (crossing detection)
        Baseado na engenharia reversa do Vasoview original.

        Em casos com torniquete, o sinal pode não retornar ao baseline
        original. Usamos o valor estável final como referência para tempos.
        """
        samples = np.array(self.samples, dtype=float)

        if len(samples) < 40:
            return None

        # 1. BASELINES
        # Inicial: antes do exercício (para Vo)
        initial_baseline = float(np.median(samples[:10]))
        # Estável: valor final (para tempos de recuperação)
        stable_baseline = float(np.median(samples[-20:]))

        # 2. DETECÇÃO DO PICO
        # O pico ocorre no final do exercício de dorsiflexão.
        # Usamos duas estratégias dependendo da amplitude do sinal:
        # - Alta amplitude: suavização para evitar ruído
        # - Baixa amplitude: máximo global na janela de exercício

        # Primeiro, estimar amplitude para escolher método
        global_max = float(np.max(samples))
        estimated_amplitude = global_max - initial_baseline

        # Janela típica de exercício: 5-25 segundos (índices 20-100 a 4Hz)
        exercise_start = 5
        exercise_end = min(25 * int(ESTIMATED_SAMPLING_RATE), len(samples) - 10)

        if exercise_end <= exercise_start:
            return None

        # Para sinais de baixa amplitude (< 3% Vo), usar máximo na janela de exercício
        # pois a suavização pode esconder picos isolados
        estimated_vo = (estimated_amplitude / initial_baseline) * 100.0 if initial_baseline > 0 else 0

        if estimated_vo < 3.0:
            # Baixa amplitude: usar máximo global na janela de exercício
            peak_idx = int(exercise_start + np.argmax(samples[exercise_start:exercise_end]))
        else:
            # Alta amplitude: usar suavização para robustez
            window = 5
            smoothed = np.convolve(samples, np.ones(window)/window, mode='valid')
            offset = (window - 1) // 2

            # Buscar pico na região central (10% a 90% do sinal)
            search_start = max(10, int(len(smoothed) * 0.1))
            search_end = int(len(smoothed) * 0.9)

            if search_end <= search_start:
                return None

            peak_idx_smooth = int(np.argmax(smoothed[search_start:search_end]) + search_start)
            peak_idx = peak_idx_smooth + offset

        peak_idx = min(peak_idx, len(samples) - 1)  # Garantir índice válido
        peak_value = float(samples[peak_idx])

        # 3. CÁLCULO DE Vo (% do baseline INICIAL)
        amplitude_vo = peak_value - initial_baseline
        if amplitude_vo <= 0 or initial_baseline <= 0:
            return None

        Vo = (amplitude_vo / initial_baseline) * 100.0
        if Vo < 0.5:
            return None

        # 4. DETECÇÃO DOS TEMPOS POR CRUZAMENTO
        recovery_start = peak_idx
        recovery_samples = samples[recovery_start:]

        if len(recovery_samples) < 10:
            return None

        # Amplitude de recuperação até baseline de REFERÊNCIA
        # Para casos "s/ Tq", o sinal pode retornar ao baseline inicial ou ultrapassá-lo
        reference_baseline = max(stable_baseline, initial_baseline)
        amplitude_ref = peak_value - reference_baseline
        if amplitude_ref <= 0:
            amplitude_ref = amplitude_vo
            reference_baseline = initial_baseline

        # NÍVEIS DE CRUZAMENTO (extraído via disassembly da DLL dppg_2.dll)
        # Th: 50% de recuperação relativo ao baseline INICIAL
        level_Th = initial_baseline + amplitude_vo * 0.50

        # Ti: 87.5% de recuperação relativo ao baseline de REFERÊNCIA (12.5% restante)
        level_Ti = reference_baseline + amplitude_ref * 0.125

        # To: 97% de recuperação relativo ao baseline de REFERÊNCIA (3% restante)
        level_To = reference_baseline + amplitude_ref * 0.03

        # Encontrar cruzamentos
        Th_samples = self._find_crossing(recovery_samples, level_Th)
        Ti_samples = self._find_crossing(recovery_samples, level_Ti)
        To_samples = self._find_crossing(recovery_samples, level_To)

        # Extrapolar se necessário
        if Th_samples is None:
            Th_samples = self._extrapolate_crossing(recovery_samples, level_Th)
        if Ti_samples is None:
            Ti_samples = self._extrapolate_crossing(recovery_samples, level_Ti)
        if To_samples is None:
            To_samples = self._extrapolate_crossing(recovery_samples, level_To)

        sample_time = 1.0 / ESTIMATED_SAMPLING_RATE
        Th = Th_samples * sample_time if Th_samples else None
        Ti = Ti_samples * sample_time if Ti_samples else None
        To = To_samples * sample_time if To_samples else None

        if Th is None or Ti is None or To is None:
            return None
        if To <= 0 or Th <= 0 or Ti <= 0:
            return None

        # 5. CÁLCULO DE Fo (Venous Refill Surface)
        # Fo = Vo × Th (confirmado pela análise da DLL - unidade %s)
        Fo = Vo * Th

        # 6. ÍNDICES PARA VISUALIZAÇÃO
        To_end_index = min(recovery_start + (int(To_samples) if To_samples else len(recovery_samples) - 1), len(samples) - 1)

        exercise_threshold = initial_baseline + amplitude_vo * 0.10
        exercise_start_index = 0
        for i in range(peak_idx):
            if samples[i] >= exercise_threshold:
                exercise_start_index = i
                break

        return PPGParameters(
            To=round(To, 1),
            Th=round(Th, 1),
            Ti=round(Ti, 1),
            Vo=round(Vo, 1),
            Fo=round(Fo, 0),
            peak_index=peak_idx,
            To_end_index=To_end_index,
            exercise_start_index=exercise_start_index,
            baseline_value=initial_baseline,
            peak_value=peak_value
        )

    def _find_crossing(self, samples, level):
        """Encontra índice onde o sinal cruza um nível (descendente)."""
        for i in range(len(samples) - 1):
            if samples[i] >= level and samples[i + 1] < level:
                frac = (samples[i] - level) / (samples[i] - samples[i + 1])
                return i + frac
        return None

    def _extrapolate_crossing(self, samples, level):
        """Extrapola linearmente para encontrar cruzamento."""
        if len(samples) < 10:
            return None
        n_fit = max(10, len(samples) // 5)
        fit_samples = samples[-n_fit:]
        fit_indices = np.arange(len(samples) - n_fit, len(samples))
        try:
            slope, intercept = np.polyfit(fit_indices, fit_samples, 1)
        except:
            return None
        if abs(slope) < 1e-6:
            return None
        crossing_idx = (level - intercept) / slope
        if crossing_idx < 0 or crossing_idx > len(samples) * 2:
            return None
        return crossing_idx

    def __repr__(self):
        exam_str = f", exam={self.exam_number}" if self.exam_number else ""
        return f"PPGBlock(L{self.label_char}, {len(self.samples)} amostras{exam_str})"


class DPPGReader:
    # Configurações padrão
    DEFAULT_HOST = "192.168.0.234"
    DEFAULT_PORT = 1100

    # Constantes do protocolo
    ESC = 0x1B
    SOH = 0x01
    EOT = 0x04
    ACK = 0x06
    NAK = 0x15
    DLE = 0x10
    ENQ = 0x05  # Enquiry - usado para polling
    STX = 0x02  # Start of Text
    ETX = 0x03  # End of Text
    GS = 0x1D
    CR = 0x0D  # Carriage Return para protocolo ASCII

    # Comandos de polling
    CMD_CHECK = b"TST:CHECK\r"  # Protocolo ASCII
    CMD_ENQ = bytes([0x05])     # Polling binário simples (ENQ)
    CMD_DLE_ENQ = bytes([0x10, 0x05])  # Polling DLE-framed
    # Baseado na análise do API Monitor: Vasoview usa timeouts muito longos/infinitos
    # e não faz polling ativo - apenas responde ao polling DLE do dispositivo
    KEEPALIVE_INTERVAL_MS = 5000  # 5 segundos - polling passivo (só se necessário)
    SOCKET_TIMEOUT = 3.0  # 3 segundos - timeout maior para reads mais estáveis

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("D-PPG Vasoquant 1000 Reader")
        self.root.geometry("1000x800")

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

        # Thread safety: queue para dados recebidos
        self.data_queue = queue.Queue()
        self.buffer_lock = threading.Lock()

        # Buffer para dados recebidos
        self.data_buffer = bytearray()

        # Blocos de dados PPG parseados
        self.ppg_blocks = []

        # Amostras brutas (fallback)
        self.raw_samples = []

        # Captura bruta para análise de protocolo
        self.raw_capture_file = None
        self.capture_enabled = False

        # Opções de visualização
        self.show_ppg_percent = tk.BooleanVar(value=True)

        # Opção de protocolo de keep-alive/polling
        # Modos: "Passivo" (só ACK), "ENQ" (binário), "TST:CHECK" (ASCII), "Desativado"
        # Baseado na análise do Vasoview: modo passivo é mais estável
        self.polling_mode = tk.StringVar(value="Passivo")  # Passivo = sem polling, só ACK
        self.keepalive_timer_id = None

        # Auto-reconexão
        self.auto_reconnect = tk.BooleanVar(value=True)  # Habilitado por padrão
        self.reconnect_timer_id = None
        self.reconnect_delay_ms = 3000  # 3 segundos entre tentativas

        # Debug: pausa do auto-ACK para testes
        self.auto_ack_paused = False
        self.auto_ack_resume_time = None

        self.setup_ui()

        # Timer para processar dados da queue
        self.root.after(50, self._process_queue)

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

        ttk.Label(config_frame, text="Polling:").grid(row=0, column=6, padx=(10, 0))
        polling_combo = ttk.Combobox(config_frame, textvariable=self.polling_mode,
                                      values=["Passivo", "ENQ", "TST:CHECK", "Desativado"], width=10, state="readonly")
        polling_combo.grid(row=0, column=7, padx=5)

        ttk.Checkbutton(config_frame, text="Auto-reconectar", variable=self.auto_reconnect).grid(row=0, column=8, padx=10)

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

        self.capture_btn = ttk.Button(data_frame, text="● Captura Raw", command=self.toggle_raw_capture)
        self.capture_btn.pack(side=tk.LEFT, padx=5)

        self.blocks_label = ttk.Label(data_frame, text="Blocos: 0", font=("Helvetica", 11, "bold"))
        self.blocks_label.pack(side=tk.LEFT, padx=20)

        self.samples_label = ttk.Label(data_frame, text="Amostras: 0", font=("Helvetica", 11, "bold"))
        self.samples_label.pack(side=tk.LEFT, padx=10)

        self.rate_label = ttk.Label(data_frame, text=f"Taxa: {ESTIMATED_SAMPLING_RATE:.1f} Hz", font=("Helvetica", 10))
        self.rate_label.pack(side=tk.LEFT, padx=10)

        ttk.Checkbutton(data_frame, text="%PPG", variable=self.show_ppg_percent,
                        command=self._refresh_plot).pack(side=tk.LEFT, padx=10)

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

        # ============================================================
        # PAINEL DE DEBUG - Teste de comandos do protocolo
        # ============================================================
        debug_frame = ttk.LabelFrame(self.root, text="Debug - Teste de Comandos (observe o display do aparelho)", padding=10)
        debug_frame.pack(fill=tk.X, padx=10, pady=5)

        # Linha 1: Protocolo DLE/ACK (modo impressora) - FUNCIONA
        row1 = ttk.Frame(debug_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="DLE/ACK:", width=10).pack(side=tk.LEFT)
        ttk.Label(row1, text="(só ACK após DLE!)", foreground="gray").pack(side=tk.LEFT)

        ttk.Button(row1, text="ACK (0x06)", width=12,
                   command=lambda: self.debug_send(b'\x06', "ACK")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="NAK (0x15)", width=12,
                   command=lambda: self.debug_send(b'\x15', "NAK ⚠offline")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="DLE (0x10)", width=12,
                   command=lambda: self.debug_send(b'\x10', "DLE ⚠offline")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="ENQ (0x05)", width=12,
                   command=lambda: self.debug_send(b'\x05', "ENQ ⚠offline")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="EOT (0x04)", width=12,
                   command=lambda: self.debug_send(b'\x04', "EOT ⚠offline")).pack(side=tk.LEFT, padx=2)

        # Linha 2: Protocolo STX/ETX (modo VL320) - da análise da DLL
        row2 = ttk.Frame(debug_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="STX/ETX:", width=10).pack(side=tk.LEFT)
        ttk.Label(row2, text="(pacotes binários)", foreground="gray").pack(side=tk.LEFT)

        ttk.Button(row2, text="STX+NULL+ETX", width=14,
                   command=lambda: self.debug_send(b'\x02\x00\x03', "Keep-alive")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="STX+ACK+ETX", width=14,
                   command=lambda: self.debug_send(b'\x02\x06\x03', "ACK binário")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="STX+ENQ+ETX", width=14,
                   command=lambda: self.debug_send(b'\x02\x05\x03', "ENQ binário")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="STX+QRY+ETX", width=14,
                   command=lambda: self.debug_send(b'\x02QRY\x03', "Query")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="STX+EOT+ETX", width=14,
                   command=lambda: self.debug_send(b'\x02\x04\x03', "EOT binário")).pack(side=tk.LEFT, padx=2)

        # Linha 3: Comandos ASCII (terminados por CR=0x0D, não \r)
        row3 = ttk.Frame(debug_frame)
        row3.pack(fill=tk.X, pady=2)

        ttk.Label(row3, text="ASCII+CR:", width=10).pack(side=tk.LEFT)
        ttk.Label(row3, text="(CR=0x0D)", foreground="gray").pack(side=tk.LEFT)

        ttk.Button(row3, text="TST:CHECK", width=12,
                   command=lambda: self.debug_send(b'TST:CHECK\x0D', "TST:CHECK+CR")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row3, text="MSG:STAT/0", width=12,
                   command=lambda: self.debug_send(b'MSG:STAT/0\x0D', "MSG:STAT/0+CR")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row3, text="MSG:STAT/4", width=12,
                   command=lambda: self.debug_send(b'MSG:STAT/4\x0D', "MSG:STAT/4+CR")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row3, text="ACQ:START", width=12,
                   command=lambda: self.debug_send(b'ACQ:START\x0D', "ACQ:START+CR")).pack(side=tk.LEFT, padx=2)
        ttk.Button(row3, text="ACQ:STOP", width=12,
                   command=lambda: self.debug_send(b'ACQ:STOP\x0D', "ACQ:STOP+CR")).pack(side=tk.LEFT, padx=2)

        # Linha 4: Entrada customizada
        row4 = ttk.Frame(debug_frame)
        row4.pack(fill=tk.X, pady=2)

        ttk.Label(row4, text="Custom:", width=10).pack(side=tk.LEFT)

        self.debug_hex_entry = ttk.Entry(row4, width=25)
        self.debug_hex_entry.pack(side=tk.LEFT, padx=2)
        self.debug_hex_entry.insert(0, "02 00 03")  # Keep-alive por padrão

        ttk.Button(row4, text="Enviar HEX", width=10,
                   command=self.debug_send_custom_hex).pack(side=tk.LEFT, padx=2)

        self.debug_ascii_entry = ttk.Entry(row4, width=25)
        self.debug_ascii_entry.pack(side=tk.LEFT, padx=2)
        self.debug_ascii_entry.insert(0, "TST:CHECK")

        ttk.Button(row4, text="ASCII+CR", width=10,
                   command=self.debug_send_custom_ascii).pack(side=tk.LEFT, padx=2)

        ttk.Button(row4, text="STX+ASCII+ETX", width=12,
                   command=self.debug_send_custom_stx_etx).pack(side=tk.LEFT, padx=2)

        # Linha 5: Status e informações
        row5 = ttk.Frame(debug_frame)
        row5.pack(fill=tk.X, pady=2)

        ttk.Label(row5, text="Info:", width=10).pack(side=tk.LEFT)

        self.debug_last_rx = ttk.Label(row5, text="Último RX: -", font=("Courier", 9))
        self.debug_last_rx.pack(side=tk.LEFT, padx=5)

        self.debug_last_tx = ttk.Label(row5, text="Último TX: -", font=("Courier", 9))
        self.debug_last_tx.pack(side=tk.LEFT, padx=5)

        ttk.Button(row5, text="Pausar ACK 10s", width=14,
                   command=self.debug_pause_auto_ack).pack(side=tk.LEFT, padx=5)

        ttk.Button(row5, text="Pausar ACK 30s", width=14,
                   command=lambda: self.debug_pause_auto_ack(30)).pack(side=tk.LEFT, padx=5)

        # Frame de visualização de dados PPG
        ppg_frame = ttk.LabelFrame(self.root, text="Visualização PPG", padding=10)
        ppg_frame.pack(fill=tk.X, padx=10, pady=5)

        self.canvas = tk.Canvas(ppg_frame, height=150, bg="white")
        self.canvas.pack(fill=tk.X)

        # Frame inferior com parâmetros e gráfico diagnóstico lado a lado
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Frame de parâmetros quantitativos (esquerda)
        params_frame = ttk.LabelFrame(bottom_frame, text="Parâmetros Quantitativos", padding=10)
        params_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Tabela de parâmetros usando Treeview
        columns = ("param", "mie", "mid", "mie_tq", "mid_tq")
        self.params_tree = ttk.Treeview(params_frame, columns=columns, show="headings", height=6)

        self.params_tree.heading("param", text="Parâmetro")
        self.params_tree.heading("mie", text="MIE")
        self.params_tree.heading("mid", text="MID")
        self.params_tree.heading("mie_tq", text="MIE Tq")
        self.params_tree.heading("mid_tq", text="MID Tq")

        self.params_tree.column("param", width=140, anchor="w")
        self.params_tree.column("mie", width=60, anchor="center")
        self.params_tree.column("mid", width=60, anchor="center")
        self.params_tree.column("mie_tq", width=60, anchor="center")
        self.params_tree.column("mid_tq", width=60, anchor="center")

        self.params_tree.pack(fill=tk.BOTH, expand=True)

        # Inserir linhas da tabela
        self.params_tree.insert("", "end", iid="To", values=("To (s) - Refilling time", "-", "-", "-", "-"))
        self.params_tree.insert("", "end", iid="Th", values=("Th (s) - Half ampl. time", "-", "-", "-", "-"))
        self.params_tree.insert("", "end", iid="Ti", values=("Ti (s) - Initial inflow", "-", "-", "-", "-"))
        self.params_tree.insert("", "end", iid="Vo", values=("Vo (%) - Pump power", "-", "-", "-", "-"))
        self.params_tree.insert("", "end", iid="Fo", values=("Fo (%s) - Pump capacity", "-", "-", "-", "-"))

        # Frame do gráfico diagnóstico Vo vs To (direita)
        diag_frame = ttk.LabelFrame(bottom_frame, text="Diagnóstico Vo% × To(s)", padding=10)
        diag_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))

        self.diag_canvas = tk.Canvas(diag_frame, width=250, height=180, bg="white")
        self.diag_canvas.pack()

        # Desenhar gráfico diagnóstico inicial
        self._draw_diagnostic_chart()

    def log(self, message, tag="info"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def toggle_raw_capture(self):
        """Alterna captura bruta de todos os dados recebidos/enviados"""
        if self.capture_enabled:
            # Parar captura
            self.capture_enabled = False
            if self.raw_capture_file:
                self.raw_capture_file.close()
                self.raw_capture_file = None
            self.capture_btn.config(text="● Captura Raw")
            self.log("Captura bruta finalizada", "info")
        else:
            # Iniciar captura
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_capture_{timestamp}.bin"
            try:
                self.raw_capture_file = open(filename, "wb")
                self.capture_enabled = True
                self.capture_btn.config(text="■ Parar Captura")
                self.log(f"Captura bruta iniciada: {filename}", "info")
                self.log("Todos os bytes RX/TX serão salvos!", "info")
            except Exception as e:
                self.log(f"Erro ao iniciar captura: {e}", "error")

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
        # Atualizar tabela de parâmetros e gráfico diagnóstico
        self._update_parameters_table()

    def _refresh_blocks_list(self):
        """Atualiza a listbox com informações atualizadas dos blocos"""
        self.blocks_listbox.delete(0, tk.END)
        for i, block in enumerate(self.ppg_blocks):
            exam_str = f" (#{block.exam_number} {block.label_desc})" if block.exam_number else f" ({block.label_desc})"
            self.blocks_listbox.insert(tk.END,
                f"Bloco {i+1}: L{block.label_char} - {len(block.samples)} amostras{exam_str}")

    def on_block_select(self, event):
        """Quando usuário seleciona um bloco, mostrar no gráfico"""
        selection = self.blocks_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.ppg_blocks):
                self.plot_block(self.ppg_blocks[idx])

    def _refresh_plot(self):
        """Atualiza o gráfico quando as opções mudam"""
        selection = self.blocks_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.ppg_blocks):
                self.plot_block(self.ppg_blocks[idx])

    def _draw_diagnostic_chart(self, points=None):
        """Desenha o gráfico diagnóstico Vo% vs To(s) com zonas de referência"""
        self.diag_canvas.delete("all")

        width = 250
        height = 180
        margin_left = 35
        margin_bottom = 25
        margin_top = 15
        margin_right = 10

        plot_width = width - margin_left - margin_right
        plot_height = height - margin_top - margin_bottom

        # Escalas: To (0-50s), Vo (0-15%)
        max_to = 50
        max_vo = 15

        def to_x(to_val):
            return margin_left + (to_val / max_to) * plot_width

        def vo_y(vo_val):
            return margin_top + plot_height - (vo_val / max_vo) * plot_height

        # =====================================================
        # ZONAS DE REFERÊNCIA (baseado no laudo oficial):
        # - VERMELHO (abnormal): To <= 20 OU Vo <= 2
        # - AMARELO (borderline): (To > 20 e To <= 24 e Vo > 2)
        #                         OU triângulo (24,4)-(50,2)-(24,2)
        # - VERDE (normal): restante
        # =====================================================

        # 1. Fundo verde (toda a área normal)
        self.diag_canvas.create_rectangle(
            to_x(0), vo_y(max_vo), to_x(max_to), vo_y(0),
            fill="#ccffcc", outline=""
        )

        # 2. Zona amarela - faixa vertical To 20-24, Vo > 2
        self.diag_canvas.create_rectangle(
            to_x(20), vo_y(max_vo), to_x(24), vo_y(2),
            fill="#ffffcc", outline=""
        )

        # 3. Zona amarela - triângulo de (24,4) a (50,2) a (24,2)
        # Linha: de To=24,Vo=4 até To=50,Vo=2
        # Equação: Vo = 4 - (To-24)*(4-2)/(50-24) = 4 - (To-24)*2/26
        self.diag_canvas.create_polygon(
            to_x(24), vo_y(4),    # ponto superior esquerdo
            to_x(50), vo_y(2),    # ponto inferior direito
            to_x(24), vo_y(2),    # ponto inferior esquerdo
            fill="#ffffcc", outline=""
        )

        # 4. Zona vermelha - To <= 20 (toda a faixa vertical esquerda)
        self.diag_canvas.create_rectangle(
            to_x(0), vo_y(max_vo), to_x(20), vo_y(0),
            fill="#ffcccc", outline=""
        )

        # 5. Zona vermelha - Vo <= 2 (toda a faixa horizontal inferior)
        self.diag_canvas.create_rectangle(
            to_x(0), vo_y(2), to_x(max_to), vo_y(0),
            fill="#ffcccc", outline=""
        )

        # Desenhar hachuras para melhor visualização
        # Hachuras vermelhas (horizontais)
        for vo_val in range(0, max_vo + 1, 1):
            y = vo_y(vo_val)
            # Hachuras na zona To <= 20
            self.diag_canvas.create_line(to_x(0), y, to_x(20), y, fill="#ff9999", width=1)
        for to_val in range(0, 21, 2):
            x = to_x(to_val)
            self.diag_canvas.create_line(x, vo_y(0), x, vo_y(max_vo), fill="#ff9999", width=1)

        # Hachuras na zona Vo <= 2 (direita de To=20)
        for to_val in range(20, max_to + 1, 2):
            x = to_x(to_val)
            self.diag_canvas.create_line(x, vo_y(0), x, vo_y(2), fill="#ff9999", width=1)

        # Hachuras amarelas (diagonais) na faixa 20-24
        for i in range(-20, 30, 3):
            x1 = to_x(20)
            y1 = vo_y(2 + i * 0.5)
            x2 = to_x(24)
            y2 = vo_y(2 + i * 0.5 + 2)
            self.diag_canvas.create_line(x1, y1, x2, y2, fill="#cccc00", width=1)

        # Hachuras amarelas no triângulo
        for to_val in range(24, 51, 3):
            # Limite superior do triângulo: Vo = 4 - (To-24)*2/26
            vo_limit = 4 - (to_val - 24) * 2 / 26
            if vo_limit > 2:
                x = to_x(to_val)
                self.diag_canvas.create_line(x, vo_y(2), x, vo_y(vo_limit), fill="#cccc00", width=1)

        # Hachuras verdes (diagonais na direção oposta)
        for i in range(-30, 50, 3):
            # Zona normal: To > 24 e Vo > linha do triângulo
            for to_val in range(24, 51, 1):
                vo_limit = 4 - (to_val - 24) * 2 / 26
                x = to_x(to_val)
                y_bottom = vo_y(max(vo_limit, 2))
                y_top = vo_y(max_vo)
                # Diagonal
                if to_val % 3 == 0:
                    self.diag_canvas.create_line(x, y_bottom, x + 5, y_top, fill="#66cc66", width=1)

        # Linhas de fronteira
        # Linha vertical em To=20 (vermelho/amarelo)
        self.diag_canvas.create_line(to_x(20), vo_y(0), to_x(20), vo_y(max_vo),
                                     fill="#cc0000", width=1)
        # Linha vertical em To=24 (amarelo/verde)
        self.diag_canvas.create_line(to_x(24), vo_y(2), to_x(24), vo_y(max_vo),
                                     fill="#cccc00", width=1)
        # Linha horizontal em Vo=2
        self.diag_canvas.create_line(to_x(0), vo_y(2), to_x(max_to), vo_y(2),
                                     fill="#cc0000", width=1)
        # Linha diagonal do triângulo amarelo
        self.diag_canvas.create_line(to_x(24), vo_y(4), to_x(50), vo_y(2),
                                     fill="#cccc00", width=1)

        # Labels das zonas
        self.diag_canvas.create_text(to_x(10), vo_y(12), text="abnormal",
                                     font=("Helvetica", 8), fill="red")
        self.diag_canvas.create_text(to_x(38), vo_y(12), text="normal",
                                     font=("Helvetica", 8), fill="green")
        self.diag_canvas.create_text(to_x(30), vo_y(3), text="Border line",
                                     font=("Helvetica", 7), fill="#999900")

        # Eixos
        # Eixo X (To)
        self.diag_canvas.create_line(margin_left, height - margin_bottom,
                                     width - margin_right, height - margin_bottom, fill="black")
        # Eixo Y (Vo)
        self.diag_canvas.create_line(margin_left, margin_top,
                                     margin_left, height - margin_bottom, fill="black")

        # Marcadores eixo X (0, 25, 50)
        for to_val in [0, 25, 50]:
            x = to_x(to_val)
            self.diag_canvas.create_line(x, height - margin_bottom, x, height - margin_bottom + 4, fill="black")
            self.diag_canvas.create_text(x, height - margin_bottom + 12, text=str(to_val),
                                         font=("Helvetica", 8))
        self.diag_canvas.create_text(width // 2, height - 5, text="To s", font=("Helvetica", 8))

        # Marcadores eixo Y (0, 5, 10, 15)
        for vo_val in [0, 5, 10, 15]:
            y = vo_y(vo_val)
            self.diag_canvas.create_line(margin_left - 4, y, margin_left, y, fill="black")
            self.diag_canvas.create_text(margin_left - 15, y, text=str(vo_val),
                                         font=("Helvetica", 8))
        self.diag_canvas.create_text(12, height // 2, text="Vo%", font=("Helvetica", 8), angle=90)

        # Plotar pontos se houver
        if points:
            colors = ["blue", "red", "green", "orange"]
            for i, (to_val, vo_val, label) in enumerate(points):
                x = to_x(to_val)
                y = vo_y(vo_val)
                color = colors[i % len(colors)]

                # Desenhar ponto
                self.diag_canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                            fill=color, outline="black")
                # Número do ponto
                self.diag_canvas.create_text(x + 10, y - 8, text=str(i + 1),
                                            font=("Helvetica", 8, "bold"), fill=color)

    def _update_parameters_table(self):
        """Atualiza a tabela de parâmetros com os valores calculados de cada bloco"""
        # Mapear blocos por tipo (label_byte)
        # 0xDF = MIE s/Tq, 0xE0 = MIE c/Tq, 0xE1 = MID s/Tq, 0xE2 = MID c/Tq
        params_by_type = {
            0xDF: None,  # MIE s/Tq
            0xE1: None,  # MID s/Tq
            0xE0: None,  # MIE c/Tq
            0xE2: None,  # MID c/Tq
        }

        for block in self.ppg_blocks:
            if block.label_byte in params_by_type:
                params = block.calculate_parameters()
                if params:
                    params_by_type[block.label_byte] = params

        # Mapear para colunas da tabela
        mie = params_by_type.get(0xDF)      # MIE sem Tq
        mid = params_by_type.get(0xE1)      # MID sem Tq
        mie_tq = params_by_type.get(0xE0)   # MIE com Tq
        mid_tq = params_by_type.get(0xE2)   # MID com Tq

        def fmt(val):
            return str(val) if val is not None else "-"

        # Atualizar cada linha da tabela
        self.params_tree.item("To", values=(
            "To (s) - Refilling time",
            fmt(mie.To if mie else None),
            fmt(mid.To if mid else None),
            fmt(mie_tq.To if mie_tq else None),
            fmt(mid_tq.To if mid_tq else None)
        ))
        self.params_tree.item("Th", values=(
            "Th (s) - Half ampl. time",
            fmt(mie.Th if mie else None),
            fmt(mid.Th if mid else None),
            fmt(mie_tq.Th if mie_tq else None),
            fmt(mid_tq.Th if mid_tq else None)
        ))
        self.params_tree.item("Ti", values=(
            "Ti (s) - Initial inflow",
            fmt(mie.Ti if mie else None),
            fmt(mid.Ti if mid else None),
            fmt(mie_tq.Ti if mie_tq else None),
            fmt(mid_tq.Ti if mid_tq else None)
        ))
        self.params_tree.item("Vo", values=(
            "Vo (%) - Pump power",
            fmt(mie.Vo if mie else None),
            fmt(mid.Vo if mid else None),
            fmt(mie_tq.Vo if mie_tq else None),
            fmt(mid_tq.Vo if mid_tq else None)
        ))
        self.params_tree.item("Fo", values=(
            "Fo (%s) - Pump capacity",
            fmt(int(mie.Fo) if mie else None),
            fmt(int(mid.Fo) if mid else None),
            fmt(int(mie_tq.Fo) if mie_tq else None),
            fmt(int(mid_tq.Fo) if mid_tq else None)
        ))

        # Atualizar gráfico diagnóstico com os pontos
        points = []
        labels = [
            (0xDF, "MIE"),
            (0xE1, "MID"),
            (0xE0, "MIE Tq"),
            (0xE2, "MID Tq"),
        ]
        for label_byte, label_name in labels:
            p = params_by_type.get(label_byte)
            if p:
                points.append((p.To, p.Vo, label_name))

        self._draw_diagnostic_chart(points)

    def plot_block(self, block):
        """Plota um bloco específico no gráfico"""
        self.canvas.delete("all")

        # Escolher dados: %PPG ou ADC bruto
        if self.show_ppg_percent.get():
            samples = block.to_ppg_percent()
            y_label = "% PPG"
            y_format = "{:.1f}"
        else:
            samples = block.samples
            y_label = "ADC"
            y_format = "{:.0f}"

        if len(samples) < 2:
            return

        width = self.canvas.winfo_width() or 900
        height = 150
        margin_left = 55  # Margem para escala vertical
        margin_bottom = 25  # Margem para escala horizontal
        plot_width = width - margin_left - 20
        plot_height = height - margin_bottom - 15

        min_val = min(samples)
        max_val = max(samples)
        val_range = max_val - min_val if max_val != min_val else 1

        # Ajustar range para %PPG (como no laudo: -2 a 8)
        if self.show_ppg_percent.get():
            min_val = min(-2, min_val)
            max_val = max(8, max_val)
            val_range = max_val - min_val

        # Calcular parâmetros para obter índice do pico (t=0)
        params = block.calculate_parameters()
        peak_idx = params.peak_index if params else len(samples) // 4

        # Tempo relativo ao pico: pico = 0s, antes = negativo, depois = positivo
        sample_time = 1.0 / ESTIMATED_SAMPLING_RATE
        time_at_start = -peak_idx * sample_time  # Tempo no início (negativo)
        time_at_end = (len(samples) - 1 - peak_idx) * sample_time  # Tempo no fim (positivo)

        # Função para converter valor em coordenada Y
        def val_to_y(val):
            return 10 + plot_height - ((val - min_val) / val_range) * plot_height

        # Função para converter índice em coordenada X (tempo relativo ao pico)
        def idx_to_x(idx):
            return margin_left + (idx / len(samples)) * plot_width

        # Função para converter tempo relativo em coordenada X
        def time_to_x(t):
            # t=0 está no pico, que está em peak_idx
            idx = peak_idx + t * ESTIMATED_SAMPLING_RATE
            return margin_left + (idx / len(samples)) * plot_width

        # Desenhar escala vertical (eixo Y)
        self.canvas.create_line(margin_left, 10, margin_left, height - margin_bottom, fill="gray")

        # Desenhar marcadores da escala Y (6 níveis)
        num_y_ticks = 5
        for i in range(num_y_ticks + 1):
            val = min_val + (val_range * i / num_y_ticks)
            y = val_to_y(val)
            # Linha de grade horizontal
            self.canvas.create_line(margin_left, y, width - 20, y, fill="lightgray", dash=(2, 2))
            # Marcador e valor
            self.canvas.create_line(margin_left - 5, y, margin_left, y, fill="gray")
            self.canvas.create_text(margin_left - 8, y, anchor="e",
                                    text=y_format.format(val), font=("Courier", 8), fill="gray")

        # Label do eixo Y
        self.canvas.create_text(10, height / 2, anchor="w", angle=90,
                                text=y_label, font=("Courier", 8), fill="gray")

        # Desenhar escala horizontal (eixo X - tempo relativo ao pico)
        self.canvas.create_line(margin_left, height - margin_bottom, width - 20, height - margin_bottom, fill="gray")

        # Calcular ticks de tempo (relativo ao pico = 0s)
        # Arredondar para múltiplos de 5 ou 10
        time_range = time_at_end - time_at_start
        tick_interval = 10 if time_range > 40 else 5
        first_tick = int(time_at_start / tick_interval) * tick_interval
        last_tick = int(time_at_end / tick_interval + 1) * tick_interval

        for t in range(first_tick, last_tick + 1, tick_interval):
            if time_at_start <= t <= time_at_end:
                x = time_to_x(t)
                self.canvas.create_line(x, height - margin_bottom, x, height - margin_bottom + 5, fill="gray")
                self.canvas.create_text(x, height - margin_bottom + 8, anchor="n",
                                        text=f"{t}s", font=("Courier", 8), fill="gray")

        # Desenhar linha vertical em t=0 (pico)
        x_zero = time_to_x(0)
        self.canvas.create_line(x_zero, 10, x_zero, height - margin_bottom, fill="red", dash=(3, 3))

        # Desenhar sinal PPG
        points = []
        for i, val in enumerate(samples):
            x = idx_to_x(i)
            y = val_to_y(val)
            points.extend([x, y])

        if len(points) >= 4:
            self.canvas.create_line(points, fill="blue", width=2)

        # Desenhar marcadores se temos parâmetros
        if params:
            # Desenhar X vermelho no PICO (t=0)
            peak_x = idx_to_x(params.peak_index)
            peak_y = val_to_y(samples[params.peak_index])
            x_size = 6
            self.canvas.create_line(peak_x - x_size, peak_y - x_size,
                                   peak_x + x_size, peak_y + x_size,
                                   fill="red", width=2)
            self.canvas.create_line(peak_x - x_size, peak_y + x_size,
                                   peak_x + x_size, peak_y - x_size,
                                   fill="red", width=2)
            # Label do pico (t=0)
            self.canvas.create_text(peak_x, peak_y - 12, anchor="s",
                                   text="t=0",
                                   font=("Courier", 7), fill="red")

            # Desenhar X verde no FIM DO To (retorno ao baseline)
            to_end_idx = min(params.To_end_index, len(samples) - 1)
            to_end_x = idx_to_x(to_end_idx)
            to_end_y = val_to_y(samples[to_end_idx])
            self.canvas.create_line(to_end_x - x_size, to_end_y - x_size,
                                   to_end_x + x_size, to_end_y + x_size,
                                   fill="green", width=2)
            self.canvas.create_line(to_end_x - x_size, to_end_y + x_size,
                                   to_end_x + x_size, to_end_y - x_size,
                                   fill="green", width=2)
            # Label do fim To (tempo relativo ao pico)
            to_relative_time = (to_end_idx - params.peak_index) / ESTIMATED_SAMPLING_RATE
            self.canvas.create_text(to_end_x, to_end_y - 12, anchor="s",
                                   text=f"To={to_relative_time:.1f}s",
                                   font=("Courier", 7), fill="green")

        # Mostrar estatísticas no topo
        exam_str = f" | #{block.exam_number}" if block.exam_number else ""
        desc_str = f" ({block.label_desc})" if block.label_desc != "Desconhecido" else ""
        trim_str = f" | {block.trimmed_count} rem." if block.trimmed_count > 0 else ""
        duration = block.get_duration_seconds()
        duration_str = f" | {duration:.1f}s"
        params_str = f" | To={params.To}s Vo={params.Vo}%" if params else ""
        self.canvas.create_text(margin_left + 5, 3, anchor="nw",
                                text=f"L{block.label_char}{desc_str}{exam_str}{duration_str}{trim_str}{params_str}",
                                font=("Courier", 9, "bold"))

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
                f.write("block,exam_number,label,sample_index,value\n")

                # Salvar blocos parseados
                for block_idx, block in enumerate(self.ppg_blocks):
                    exam_str = str(block.exam_number) if block.exam_number else ""
                    for sample_idx, val in enumerate(block.samples):
                        f.write(f"{block_idx},{exam_str},L{block.label_char},{sample_idx},{val}\n")

                # Salvar amostras brutas (se houver)
                if self.raw_samples:
                    for sample_idx, val in enumerate(self.raw_samples):
                        f.write(f"raw,,raw,{sample_idx},{val}\n")

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
            blocks_data = []
            for i, b in enumerate(self.ppg_blocks):
                params = b.calculate_parameters()
                # Converter TUDO para tipos Python nativos (evita erros com numpy int64/float64)
                samples_list = [int(x) for x in b.samples]
                samples_raw_list = [int(x) for x in b.samples_raw] if b.trimmed_count > 0 else None
                ppg_percent_list = [float(x) for x in b.to_ppg_percent()]
                block_data = {
                    "index": int(i),
                    "label": f"L{b.label_char}",
                    "label_byte": int(b.label_byte),
                    "label_desc": str(b.label_desc),
                    "exam_number": int(b.exam_number) if b.exam_number else None,
                    "timestamp": b.timestamp.isoformat(),
                    "duration_seconds": float(b.get_duration_seconds()),
                    "sample_count": int(len(b.samples)),
                    "samples": samples_list,
                    "samples_ppg_percent": ppg_percent_list,
                    "trimmed_count": int(b.trimmed_count),
                    "samples_raw": samples_raw_list,
                    "metadata_hex": b.metadata_raw.hex() if b.metadata_raw else None,
                    "parameters": {
                        "To_s": float(params.To),
                        "Th_s": float(params.Th),
                        "Ti_s": float(params.Ti),
                        "Vo_percent": float(params.Vo),
                        "Fo_percent_s": float(params.Fo),
                        "peak_index": int(params.peak_index),
                        "baseline_adc": float(params.baseline_value),
                        "peak_adc": float(params.peak_value)
                    } if params else None
                }
                blocks_data.append(block_data)

            data = {
                "export_timestamp": datetime.now().isoformat(),
                "sampling_rate_hz": ESTIMATED_SAMPLING_RATE,
                "blocks": blocks_data,
                "raw_samples": self.raw_samples if self.raw_samples else None
            }

            # Usar encoder customizado para converter tipos numpy automaticamente
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, cls=NumpyJSONEncoder)

            self.log(f"JSON salvo em {filename}", "info")
        except Exception as e:
            import traceback
            self.log(f"Erro ao salvar JSON: {e}", "error")
            self.log(f"Detalhes: {traceback.format_exc()}", "error")

    # ============================================================
    # FUNÇÕES DE DEBUG - Teste de comandos do protocolo
    # ============================================================

    def debug_send(self, data: bytes, description: str):
        """Envia dados de debug e registra no log"""
        if not self.connected or not self.socket:
            self.log("Não conectado - conecte primeiro", "error")
            return

        try:
            self.socket.send(data)
            hex_str = ' '.join(f'{b:02X}' for b in data)
            self.log(f"DEBUG TX: {description} [{hex_str}]", "sent")
            self.debug_last_tx.config(text=f"Último TX: {description} [{hex_str}]")
        except Exception as e:
            self.log(f"Erro ao enviar debug: {e}", "error")

    def debug_send_custom_hex(self):
        """Envia bytes customizados em formato hexadecimal"""
        hex_str = self.debug_hex_entry.get().strip()
        try:
            # Remover espaços e converter para bytes
            hex_str = hex_str.replace(' ', '').replace('0x', '').replace(',', '')
            data = bytes.fromhex(hex_str)
            self.debug_send(data, f"Custom HEX ({len(data)} bytes)")
        except ValueError as e:
            self.log(f"HEX inválido: {e}", "error")

    def debug_send_custom_ascii(self):
        """Envia texto ASCII customizado + CR (0x0D)"""
        text = self.debug_ascii_entry.get()
        data = text.encode('ascii') + b'\x0D'  # CR = 0x0D (não \r)
        self.debug_send(data, f"ASCII+CR: {text}")

    def debug_send_custom_stx_etx(self):
        """Envia texto ASCII envolvido em STX/ETX"""
        text = self.debug_ascii_entry.get()
        data = b'\x02' + text.encode('ascii') + b'\x03'  # STX + texto + ETX
        self.debug_send(data, f"STX+{text}+ETX")

    def debug_pause_auto_ack(self, seconds=10):
        """Pausa o envio automático de ACK por N segundos"""
        self.auto_ack_paused = True
        self.auto_ack_resume_time = time.time() + seconds
        self.log(f"Auto-ACK PAUSADO por {seconds} segundos - observe o display do aparelho", "info")
        self.root.after(seconds * 1000, self._resume_auto_ack)

    def _resume_auto_ack(self):
        """Retoma o envio automático de ACK"""
        self.auto_ack_paused = False
        self.auto_ack_resume_time = None
        self.log("Auto-ACK RETOMADO", "info")

    def debug_update_last_rx(self, data: bytes):
        """Atualiza o display do último dado recebido"""
        if len(data) <= 20:
            hex_str = ' '.join(f'{b:02X}' for b in data)
        else:
            hex_str = ' '.join(f'{b:02X}' for b in data[:20]) + '...'
        self.debug_last_rx.config(text=f"Último RX: [{hex_str}] ({len(data)} bytes)")

    def _send_keepalive(self):
        """Envia comando de polling para manter conexão ativa"""
        mode = self.polling_mode.get()
        # Passivo e Desativado: não enviar nada
        if not self.connected or not self.socket or mode in ["Desativado", "Passivo"]:
            return

        try:
            if mode == "ENQ":
                # Polling binário - ENQ (0x05)
                # Mais compatível com modo de emulação de impressora
                self.socket.send(self.CMD_ENQ)
                self.log("TX: ENQ (polling)", "sent")
            elif mode == "TST:CHECK":
                # Protocolo ASCII alternativo
                self.socket.send(self.CMD_CHECK)
                self.log("TX: TST:CHECK", "sent")
        except Exception as e:
            self.log(f"Erro ao enviar polling: {e}", "error")

        # Reagendar próximo keepalive (apenas para modos ativos)
        if self.connected and mode not in ["Desativado", "Passivo"]:
            self.keepalive_timer_id = self.root.after(self.KEEPALIVE_INTERVAL_MS, self._send_keepalive)

    def _start_keepalive(self):
        """Inicia o timer de keep-alive/polling"""
        mode = self.polling_mode.get()
        if mode == "Passivo":
            # Modo passivo: baseado na análise do Vasoview, não faz polling ativo
            # Apenas responde ACK quando recebe dados (tratado em process_received_data)
            self.log("Modo passivo: aguardando polling do dispositivo (DLE)", "info")
        elif mode != "Desativado":
            self.log(f"Iniciando polling ativo (modo: {mode}, intervalo: {self.KEEPALIVE_INTERVAL_MS/1000:.1f}s)", "info")
            self._send_keepalive()

    def _stop_keepalive(self):
        """Para o timer de keep-alive TST:CHECK"""
        if self.keepalive_timer_id:
            self.root.after_cancel(self.keepalive_timer_id)
            self.keepalive_timer_id = None

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

            # Habilitar TCP keep-alive para manter conexão ativa
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # No macOS/Linux, configurar intervalos mais agressivos
            try:
                import platform
                if platform.system() == 'Darwin':  # macOS
                    # TCP_KEEPALIVE = intervalo em segundos
                    self.socket.setsockopt(socket.IPPROTO_TCP, 0x10, 5)  # TCP_KEEPALIVE = 5s
                elif platform.system() == 'Linux':
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            except (AttributeError, OSError):
                pass  # Ignorar se não suportado

            # TCP_NODELAY: desabilitar Nagle para respostas mais rápidas
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            self.socket.settimeout(5)
            self.socket.connect((host, port))
            # Baseado na análise do Vasoview: usar timeout maior para reads mais estáveis
            # Vasoview usa timeouts infinitos, mas 3s é um bom compromisso
            self.socket.settimeout(self.SOCKET_TIMEOUT)

            self.connected = True
            self.running = True
            self.printer_online = False

            self.connect_btn.config(text="Desconectar")
            self.status_label.config(text="TCP OK - Aguardando...", foreground="orange")
            self.log(f"TCP conectado - aguardando dados do Vasoquant...", "info")

            # Iniciar thread de recepção
            self.receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
            self.receive_thread.start()

            # Iniciar keep-alive TST:CHECK se habilitado
            self._start_keepalive()

        except socket.timeout:
            self.log("Timeout ao conectar - verifique IP e porta", "error")
        except Exception as e:
            self.log(f"Erro ao conectar: {e}", "error")

    def disconnect(self, schedule_reconnect=False):
        self.running = False
        self.connected = False
        self.printer_online = False

        # Parar keep-alive
        self._stop_keepalive()

        # Cancelar reconexão pendente (se disconnect manual)
        if not schedule_reconnect and self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
            self.reconnect_timer_id = None

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

        # Agendar reconexão automática se habilitada
        if schedule_reconnect and self.auto_reconnect.get():
            self.log(f"Reconectando em {self.reconnect_delay_ms/1000:.1f}s...", "info")
            self.status_label.config(text="Reconectando...", foreground="orange")
            self.reconnect_timer_id = self.root.after(self.reconnect_delay_ms, self._attempt_reconnect)

    def _attempt_reconnect(self):
        """Tenta reconectar automaticamente"""
        self.reconnect_timer_id = None
        if not self.connected:
            self.log("Tentando reconectar...", "info")
            self.connect()

    def receive_loop(self):
        while self.running:
            try:
                data = self.socket.recv(1024)
                if data:
                    self.process_received_data(data)
                elif data == b'':
                    # Conexão fechada pelo servidor - agendar reconexão
                    self.root.after(0, lambda: self.disconnect(schedule_reconnect=True))
                    break
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.root.after(0, lambda err=e: self.log(f"Erro de recepção: {err}", "error"))
                    # Erro de rede - agendar reconexão
                    self.root.after(0, lambda: self.disconnect(schedule_reconnect=True))
                break

    def _process_queue(self):
        """Processa dados da queue de forma thread-safe (chamado pelo timer do Tk)"""
        try:
            while True:
                data = self.data_queue.get_nowait()
                with self.buffer_lock:
                    self.data_buffer.extend(data)
                self.parse_buffer()
        except queue.Empty:
            pass
        finally:
            # Reagendar o timer
            if self.running or self.connected:
                self.root.after(50, self._process_queue)
            else:
                self.root.after(500, self._process_queue)

    def process_received_data(self, data):
        """Thread de rede: recebe dados e coloca na queue"""
        # Atualizar status para "Online" quando receber dados
        self.last_data_time = datetime.now()
        if not self.printer_online:
            self.printer_online = True
            self.root.after(0, lambda: self.status_label.config(text="Printer Online", foreground="green"))
            self.root.after(0, lambda: self.log("Vasoquant conectado!", "info"))

        # Captura bruta - salvar em arquivo binário
        if self.capture_enabled and self.raw_capture_file:
            try:
                # Formato: [timestamp 4 bytes][direção 1 byte][tamanho 2 bytes][dados]
                import struct
                import time
                ts = int(time.time() * 1000) & 0xFFFFFFFF  # timestamp em ms
                self.raw_capture_file.write(struct.pack('<IBH', ts, 0x52, len(data)))  # 0x52 = 'R' (RX)
                self.raw_capture_file.write(data)
                self.raw_capture_file.flush()
            except:
                pass

        # Log resumido dos dados
        hex_preview = ' '.join(f'{b:02X}' for b in data[:20])
        if len(data) > 20:
            hex_preview += "..."
        self.root.after(0, lambda d=data, h=hex_preview: self.log(f"RX ({len(d)} bytes): {h}", "received"))

        # Atualizar display de debug
        self.root.after(0, lambda d=data: self.debug_update_last_rx(d))

        # Auto-ACK: SEMPRE responder com ACK para manter impressora "online"
        # O ACK é necessário para o protocolo de impressora, independente do TST:CHECK
        # A menos que o modo de debug tenha pausado o auto-ACK
        if self.socket and not self.auto_ack_paused:
            try:
                self.socket.send(b'\x06')
                # Captura bruta - salvar TX também
                if self.capture_enabled and self.raw_capture_file:
                    try:
                        import struct
                        import time
                        ts = int(time.time() * 1000) & 0xFFFFFFFF
                        self.raw_capture_file.write(struct.pack('<IBH', ts, 0x54, 1))  # 0x54 = 'T' (TX)
                        self.raw_capture_file.write(b'\x06')
                        self.raw_capture_file.flush()
                    except:
                        pass
                if len(data) <= 3:
                    self.root.after(0, lambda: self.log("TX: ACK", "sent"))
            except Exception as e:
                self.root.after(0, lambda e=e: self.log(f"Erro ao enviar ACK: {e}", "error"))
        elif self.auto_ack_paused:
            self.root.after(0, lambda: self.log("Auto-ACK pausado - NÃO enviando ACK", "info"))

        # Adicionar à queue (thread-safe)
        self.data_queue.put(bytes(data))

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

                # Verificar se há metadados suficientes (pelo menos 10 bytes para o padrão)
                # OU se há um novo bloco começando (ESC após os dados)
                metadata_min_size = 10  # 1D XX XX 00 00 00 1D YY YY + margem
                has_next_block = False
                for i in range(data_end, min(data_end + 30, len(self.data_buffer))):
                    if self.data_buffer[i] == self.ESC:
                        has_next_block = True
                        break

                if not has_next_block and (data_end + metadata_min_size) > len(self.data_buffer):
                    break  # Aguardar mais dados para os metadados

                # Extrair amostras
                samples = []
                for i in range(data_start, data_end, 2):
                    if i + 1 < len(self.data_buffer):
                        low = self.data_buffer[i]
                        high = self.data_buffer[i + 1]
                        value = low | (high << 8)
                        samples.append(value)

                # Capturar metadados brutos para análise
                metadata_start = data_end
                metadata_end = min(metadata_start + 40, len(self.data_buffer))
                metadata_raw = bytes(self.data_buffer[metadata_start:metadata_end])

                # Tentar extrair número do exame dos metadados
                # Padrão observado: 1D XX XX 00 00 00 1D YY YY
                # O número do exame está no SEGUNDO GS (após 00 00 00)
                exam_number = None
                for i in range(len(metadata_raw) - 5):
                    if (metadata_raw[i] == 0x00 and
                        metadata_raw[i + 1] == 0x00 and
                        metadata_raw[i + 2] == 0x00 and
                        metadata_raw[i + 3] == self.GS):
                        # Bytes i+4 e i+5 são o número do exame (little-endian)
                        exam_low = metadata_raw[i + 4]
                        exam_high = metadata_raw[i + 5]
                        exam_number = exam_low | (exam_high << 8)
                        # Validar: números de exame típicos são 1-9999
                        if 1 <= exam_number <= 9999:
                            break
                        else:
                            exam_number = None

                # Criar bloco com metadados
                block = PPGBlock(label_byte, samples, exam_number, metadata_raw)
                self.ppg_blocks.append(block)

                # Se encontrou exam_number, aplicar retroativamente a blocos sem número
                if exam_number:
                    for prev_block in self.ppg_blocks[:-1]:
                        if prev_block.exam_number is None:
                            prev_block.exam_number = exam_number
                    # Atualizar listbox para blocos anteriores
                    self._refresh_blocks_list()

                # Log dos metadados para análise
                if metadata_raw:
                    meta_hex = ' '.join(f'{b:02X}' for b in metadata_raw[:20])
                    self.log(f"Metadata L{block.label_char}: {meta_hex}...", "data")

                # Atualizar UI
                exam_str = f" (#{exam_number} {block.label_desc})" if exam_number else f" ({block.label_desc})"
                trim_str = f" [{block.trimmed_count} rem]" if block.trimmed_count > 0 else ""
                if not exam_number:
                    self.blocks_listbox.insert(tk.END,
                        f"Bloco {len(self.ppg_blocks)}: L{block.label_char} - {len(block.samples)} amostras{exam_str}")
                self.log(f"Bloco: L{block.label_char} {block.label_desc} | {len(block.samples)} amostras{' | #'+str(exam_number) if exam_number else ''}{trim_str}", "block")

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
