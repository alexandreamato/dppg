"""
Configurações e constantes do D-PPG Vasoquant 1000 Reader.

Este módulo centraliza todas as constantes de configuração,
parâmetros de calibração e mapeamentos do protocolo.
"""

# =============================================================================
# CONFIGURAÇÕES DE CONEXÃO
# =============================================================================

DEFAULT_HOST = "192.168.0.234"
DEFAULT_PORT = 1100

# =============================================================================
# CONSTANTES DO PROTOCOLO SERIAL
# =============================================================================

class Protocol:
    """Constantes do protocolo de comunicação com o Vasoquant."""
    ESC = 0x1B  # Escape - início de comando/label
    SOH = 0x01  # Start of Header
    EOT = 0x04  # End of Transmission
    ACK = 0x06  # Acknowledge
    DLE = 0x10  # Data Link Escape - polling de status
    GS = 0x1D   # Group Separator - header com tamanho


# =============================================================================
# PARÂMETROS DE AMOSTRAGEM E CALIBRAÇÃO
# =============================================================================

# Taxa de amostragem (Hz)
# CONFIRMADO pela análise do protocolo:
# - Exercício: 8 movimentos em 16 segundos
# - Amostras no período de exercício: ~64
# - 64 amostras / 16 segundos = 4 Hz
# Nota: Os 32.5 Hz encontrados no binário são a taxa interna do hardware,
# mas os dados exportados são a 4 Hz.
ESTIMATED_SAMPLING_RATE = 4.0

# Fator de conversão ADC para %PPG
# ~27 unidades ADC correspondem a 1% de variação PPG
ADC_TO_PPG_FACTOR = 27.0


# =============================================================================
# MAPEAMENTO DE LABELS
# =============================================================================

# Mapeamento de bytes de label para descrições clínicas
LABEL_DESCRIPTIONS = {
    0xE2: "MID c/ Tq",   # Membro Inferior Direito, com Tourniquet
    0xE1: "MID s/ Tq",   # Membro Inferior Direito, sem Tourniquet
    0xE0: "MIE c/ Tq",   # Membro Inferior Esquerdo, com Tourniquet
    0xDF: "MIE s/ Tq",   # Membro Inferior Esquerdo, sem Tourniquet
    0xDE: "Canal 5",     # A ser identificado
}

# Mapeamento de label_byte para colunas na tabela de parâmetros
LABEL_TO_COLUMN = {
    0xDF: "mie",      # MIE sem Torniquete
    0xE1: "mid",      # MID sem Torniquete
    0xE0: "mie_tq",   # MIE com Torniquete
    0xE2: "mid_tq",   # MID com Torniquete
}


# =============================================================================
# PARÂMETROS DO ALGORITMO DE CÁLCULO
# =============================================================================

class AnalysisParams:
    """Parâmetros para o algoritmo de cálculo dos parâmetros PPG."""

    # Número de amostras para calcular baseline inicial
    BASELINE_SAMPLES = 10

    # Janela de suavização (média móvel)
    SMOOTHING_WINDOW = 5

    # Limiar mínimo de amplitude (Vo) para análise válida
    MIN_AMPLITUDE = 0.5

    # Margem para seleção da região de decaimento
    DECAY_START_OFFSET = 5   # Amostras após o pico
    DECAY_END_OFFSET = 25    # Amostras antes do fim

    # Mínimo de pontos para regressão válida
    MIN_REGRESSION_POINTS = 5

    # Coeficientes para cálculo de To (baseado em análise de laudos)
    # To = tau * TO_COEFFICIENT
    TO_COEFFICIENT = 2.6

    # =========================================================================
    # THRESHOLDS PARA CÁLCULO DE PARÂMETROS
    # Confirmados via pseudocódigo de dppg 2.dll (fcn.100182c0)
    # =========================================================================

    # To: 97% de recuperação
    # Usamos threshold crossing porque não temos end marker do hardware.
    # No original, To = (end_marker - peak) / sr (markers do hardware).
    THRESHOLD_TO = 0.03

    # Th: 50% de recuperação (shift-right por 1 = divisão por 2)
    # Confirmado: sar eax,1 em 0x100183AF
    THRESHOLD_TH = 0.50

    # =========================================================================
    # PARÂMETROS DO Ti (Extrapolação Linear Adaptativa)
    # Ti NÃO usa threshold crossing. Usa extrapolação linear do slope
    # inicial de recuperação (confirmado no pseudocódigo de dppg 2.dll).
    # =========================================================================

    # Limiar de queda em 3 segundos para escolher janela (em unidades ADC)
    # Se queda >= 10 ADC em 3s: usa janela de 3s (decaimento rápido)
    # Se queda < 10 ADC em 3s: usa janela de 6s (decaimento lento)
    TI_DELTA_THRESHOLD = 10

    # Janelas de tempo para extrapolação (em segundos)
    TI_FAST_WINDOW = 3   # Para sinais com decaimento rápido
    TI_SLOW_WINDOW = 6   # Para sinais com decaimento lento

    # Valor máximo de Ti (em segundos)
    TI_MAX_SECONDS = 120

    # Limiar de Vo para escolher método de detecção de pico
    # Abaixo deste valor, usa máximo global (sinais patológicos)
    # Acima, usa suavização (sinais normais)
    LOW_AMPLITUDE_VO_THRESHOLD = 3.0

    # =========================================================================
    # PARÂMETROS DE EXTRAPOLAÇÃO
    # Quando o sinal não cruza o threshold, usa extrapolação linear
    # =========================================================================

    # Tempo máximo de extrapolação em segundos (cap do Vasoview)
    # Análise do banco de dados mostrou que 120s é o valor máximo usado
    MAX_EXTRAPOLATION_TIME = 120.0

    # Número de amostras para calcular o slope de extrapolação
    # Usa os últimos N pontos para estimar a taxa de recuperação
    EXTRAPOLATION_FIT_SAMPLES = 10
