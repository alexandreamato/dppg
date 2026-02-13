"""
Modelos de dados para o D-PPG Vasoquant 1000 Reader.

Define as estruturas de dados para parâmetros PPG e blocos de dados.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from .config import (
    LABEL_DESCRIPTIONS,
    ESTIMATED_SAMPLING_RATE,
    ADC_TO_PPG_FACTOR,
)


@dataclass
class PPGParameters:
    """
    Parâmetros quantitativos calculados da curva D-PPG.

    Attributes:
        To: Venous refilling time (s) - tempo de reenchimento venoso
        Th: Venous half amplitude time (s) - tempo de meia amplitude
        Ti: Initial inflow time (s) - tempo de influxo inicial
        Vo: Venous pump power (%) - potência da bomba venosa
        Fo: Venous pump capacity (%·s) - capacidade da bomba venosa
        tau: Exponential time constant (s) - constante de tempo exponencial
        peak_index: Índice do pico máximo (momento zero)
        To_end_index: Índice do fim do To (retorno ao baseline)
        exercise_start_index: Índice do início do exercício
        baseline_value: Valor do baseline em ADC
        peak_value: Valor do pico em ADC
    """
    To: float
    Th: float
    Ti: float
    Vo: float
    Fo: float
    tau: Optional[float] = None
    peak_index: int = 0
    To_end_index: int = 0
    exercise_start_index: int = 0
    baseline_value: float = 0.0
    peak_value: float = 0.0

    def to_dict(self) -> dict:
        """Converte para dicionário (útil para exportação JSON)."""
        d = {
            "To_s": self.To,
            "Th_s": self.Th,
            "Ti_s": self.Ti,
            "Vo_percent": self.Vo,
            "Fo_percent_s": self.Fo,
            "peak_index": self.peak_index,
            "baseline_adc": self.baseline_value,
            "peak_adc": self.peak_value,
        }
        if self.tau is not None:
            d["tau_s"] = self.tau
        return d


class PPGBlock:
    """
    Representa um bloco de dados PPG do Vasoquant.

    Um bloco contém as amostras de uma medição, juntamente com
    metadados como label, número do exame e timestamp.
    """

    def __init__(
        self,
        label_byte: int,
        samples: List[int],
        exam_number: Optional[int] = None,
        metadata_raw: Optional[bytes] = None
    ):
        """
        Inicializa um bloco PPG.

        Args:
            label_byte: Byte identificador do canal (ex: 0xE2 para "â")
            samples: Lista de amostras ADC brutas
            exam_number: Número do exame extraído dos metadados
            metadata_raw: Bytes brutos de metadados para análise
        """
        self.label_byte = label_byte
        self.label_char = chr(label_byte) if 0x20 <= label_byte <= 0xFF else f"0x{label_byte:02X}"
        self.label_desc = LABEL_DESCRIPTIONS.get(label_byte, "Desconhecido")
        self.samples_raw = samples
        self.samples = self._trim_trailing_artifacts(samples)
        self.exam_number = exam_number
        self.metadata_raw = metadata_raw
        self.timestamp = datetime.now()
        self.trimmed_count = len(samples) - len(self.samples)
        self._cached_parameters: Optional[PPGParameters] = None

        # Hardware-provided values from metadata (decoded from protocol)
        self.hw_baseline: Optional[int] = None      # Baseline ADC value
        self.hw_peak_index: Optional[int] = None     # Peak sample index (peak_raw + 7)
        self.hw_end_index: Optional[int] = None      # End index (peak_index + To_samples)
        self.hw_amplitude: Optional[int] = None      # Peak - baseline (ADC units)
        self.hw_To_samples: Optional[int] = None     # To in samples (end - peak)
        self.hw_Th_samples: Optional[int] = None     # Th in samples
        self.hw_Ti: Optional[int] = None             # Ti in seconds (integer)
        self.hw_Fo_x100: Optional[int] = None        # Fo × 100 (0.01 %·s units)
        self.hw_flags: Optional[int] = None          # Flags (0x00=normal, 0x80=no endpoint)

    def _trim_trailing_artifacts(self, samples: List[int]) -> List[int]:
        """
        Remove artefatos do final do bloco.

        Bytes de controle do protocolo às vezes são interpretados como
        dados, criando outliers no final do bloco.

        Args:
            samples: Lista de amostras original

        Returns:
            Lista de amostras sem artefatos finais
        """
        if len(samples) < 15:
            return samples

        # Usar dados principais (excluindo últimos 5) para estatísticas
        main_samples = samples[:-5]
        if len(main_samples) < 10:
            return samples

        # Usar mediana e IQR para robustez contra outliers
        sorted_main = sorted(main_samples)
        n = len(sorted_main)
        median = sorted_main[n // 2]
        q1 = sorted_main[n // 4]
        q3 = sorted_main[3 * n // 4]
        iqr = q3 - q1 if q3 > q1 else 50

        # Threshold: valores fora de 2.5 * IQR são outliers
        lower_bound = median - 2.5 * iqr
        upper_bound = median + 2.5 * iqr

        # Verificar últimos 5 valores - encontrar primeiro outlier
        trim_from = len(samples)
        for i in range(len(samples) - 5, len(samples)):
            val = samples[i]
            if val < lower_bound or val > upper_bound:
                trim_from = i
                break

        if trim_from < len(samples):
            return samples[:trim_from]

        # Verificação adicional: grande variação nos últimos valores
        last_5 = samples[-5:]
        last_range = max(last_5) - min(last_5)
        main_range = max(main_samples[-20:]) - min(main_samples[-20:]) if len(main_samples) >= 20 else iqr

        if last_range > main_range * 2:
            for i in range(len(samples) - 5, len(samples)):
                if abs(samples[i] - median) > 1.5 * iqr:
                    return samples[:i]

        return samples

    def to_ppg_percent(self) -> List[float]:
        """
        Converte amostras ADC para %PPG.

        Returns:
            Lista de valores em %PPG (relativo ao baseline)
        """
        if not self.samples:
            return []

        baseline = sum(self.samples[:10]) / min(10, len(self.samples))
        return [(val - baseline) / ADC_TO_PPG_FACTOR for val in self.samples]

    def get_duration_seconds(self) -> float:
        """Retorna duração estimada do bloco em segundos."""
        return len(self.samples) / ESTIMATED_SAMPLING_RATE

    def __repr__(self) -> str:
        exam_str = f", exam={self.exam_number}" if self.exam_number else ""
        return f"PPGBlock(L{self.label_char}, {len(self.samples)} amostras{exam_str})"
