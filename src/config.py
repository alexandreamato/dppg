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
