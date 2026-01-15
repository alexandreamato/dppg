"""
Análise e cálculo de parâmetros do sinal D-PPG.

Este módulo implementa os algoritmos de processamento de sinal
para extrair os parâmetros quantitativos da curva PPG.

MÉTODO: Detecção direta de cruzamento (crossing detection)
Baseado na engenharia reversa do Vasoview original, que NÃO usa
fitting exponencial, mas detecta diretamente quando o sinal
cruza os níveis de 50%, 90% e 100% de recuperação.

Referência: Vasoview_Analise_Tecnica_Detalhada.docx
"""

from typing import Optional, List, Tuple
import numpy as np

from .config import ESTIMATED_SAMPLING_RATE
from .models import PPGParameters, PPGBlock


def calculate_parameters(block: PPGBlock) -> Optional[PPGParameters]:
    """
    Calcula os parâmetros quantitativos da curva D-PPG.

    Usa DETECÇÃO DIRETA DE CRUZAMENTO para encontrar To, Th, Ti.
    Este é o método usado pelo software original Vasoview.

    IMPORTANTE: Em casos com torniquete, o sinal pode não retornar ao baseline
    original. Neste caso, usamos o valor estável final (asymptotic baseline)
    como referência para os tempos de recuperação.

    Parâmetros calculados:
        - To: Tempo até 100% de recuperação (retorno ao baseline estável)
        - Th: Tempo até 50% de recuperação
        - Ti: Tempo até 90% de recuperação (fase inicial de influxo)
        - Vo: Amplitude máxima em % do baseline INICIAL
        - Fo: Área sob a curva de recuperação (integral)

    Args:
        block: Bloco PPG com as amostras

    Returns:
        PPGParameters com os valores calculados, ou None se inválido
    """
    samples = np.array(block.samples, dtype=float)

    if len(samples) < 40:
        return None

    # ================================================================
    # 1. DETECÇÃO DOS BASELINES
    # ================================================================
    # Baseline inicial: antes do exercício (para cálculo de Vo)
    initial_baseline = np.median(samples[:10])

    # Baseline estável: valor final de estabilização (para tempos)
    # Em casos com torniquete, pode ser diferente do inicial
    stable_baseline = np.median(samples[-20:])

    # ================================================================
    # 2. DETECÇÃO DO PICO (máximo esvaziamento venoso)
    # ================================================================
    window = 5
    if len(samples) > window:
        smoothed = np.convolve(samples, np.ones(window)/window, mode='valid')
        offset = (window - 1) // 2
    else:
        smoothed = samples
        offset = 0

    search_start = max(10, int(len(smoothed) * 0.1))
    search_end = int(len(smoothed) * 0.9)

    if search_start >= search_end:
        return None

    # O sinal SOBE durante exercício (polaridade invertida)
    peak_idx_smooth = np.argmax(smoothed[search_start:search_end]) + search_start
    peak_idx = peak_idx_smooth + offset
    peak_value = samples[peak_idx]

    # ================================================================
    # 3. CÁLCULO DE Vo (Venous Pump Power)
    # ================================================================
    # Vo usa o baseline INICIAL (estado antes do exercício)
    # Fórmula: Vo = (Vpeak - Vbaseline) / Vbaseline × 100
    amplitude_vo = peak_value - initial_baseline
    if amplitude_vo <= 0 or initial_baseline <= 0:
        return None

    Vo = (amplitude_vo / initial_baseline) * 100.0

    if Vo < 0.5:  # Amplitude muito baixa
        return None

    # ================================================================
    # 4. DETECÇÃO DOS TEMPOS POR CRUZAMENTO DE NÍVEIS
    # ================================================================
    recovery_start = peak_idx
    recovery_samples = samples[recovery_start:]

    if len(recovery_samples) < 10:
        return None

    # Amplitude de recuperação: do pico até o baseline de REFERÊNCIA
    # Para casos "s/ Tq" (sem torniquete), o sinal pode retornar ao baseline inicial
    # ou até ultrapassá-lo. Usamos o MAIOR dos dois baselines como referência.
    reference_baseline = max(stable_baseline, initial_baseline)
    amplitude_ref = peak_value - reference_baseline

    if amplitude_ref <= 0:
        # Se não há recuperação significativa, usar baseline inicial
        amplitude_ref = amplitude_vo
        reference_baseline = initial_baseline

    # ================================================================
    # NÍVEIS DE CRUZAMENTO (calibrado com laudos originais)
    # ================================================================
    # Th: 50% de recuperação relativo ao baseline INICIAL
    # (Half-amplitude time mede metade da amplitude total)
    level_Th = initial_baseline + amplitude_vo * 0.50

    # Ti: 90% de recuperação relativo ao baseline de REFERÊNCIA
    # (Initial inflow mede até próximo do ponto de estabilização)
    level_Ti = reference_baseline + amplitude_ref * 0.10

    # To: ~97% de recuperação relativo ao baseline de REFERÊNCIA
    # (Não usa 100% porque o sinal pode não retornar completamente)
    level_To = reference_baseline + amplitude_ref * 0.03

    # Encontrar cruzamentos
    Th_samples = _find_crossing(recovery_samples, level_Th, direction='down')
    Ti_samples = _find_crossing(recovery_samples, level_Ti, direction='down')
    To_samples = _find_crossing(recovery_samples, level_To, direction='down')

    sample_time = 1.0 / ESTIMATED_SAMPLING_RATE

    # Extrapolar se necessário (raro com baseline estável)
    if Th_samples is None:
        Th_samples = _extrapolate_crossing(recovery_samples, level_Th)
    if Ti_samples is None:
        Ti_samples = _extrapolate_crossing(recovery_samples, level_Ti)
    if To_samples is None:
        To_samples = _extrapolate_crossing(recovery_samples, level_To)

    Th = Th_samples * sample_time if Th_samples else None
    Ti = Ti_samples * sample_time if Ti_samples else None
    To = To_samples * sample_time if To_samples else None

    # Validar resultados
    if Th is None or Ti is None or To is None:
        return None
    if To <= 0 or Th <= 0 or Ti <= 0:
        return None

    # ================================================================
    # 5. CÁLCULO DE Fo (Venous Refill Surface)
    # ================================================================
    # Calibrado com laudos originais: Fo ≈ Vo × Th
    # Esta relação vem da física do decaimento exponencial onde
    # a integral é proporcional à amplitude × constante de tempo
    Fo = Vo * Th

    # ================================================================
    # 6. ÍNDICES PARA VISUALIZAÇÃO
    # ================================================================
    To_end_index = recovery_start + (int(To_samples) if To_samples else len(recovery_samples) - 1)
    To_end_index = min(To_end_index, len(samples) - 1)

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
        peak_value=peak_value,
    )


def _find_crossing(
    samples: np.ndarray,
    level: float,
    direction: str = 'down'
) -> Optional[float]:
    """
    Encontra o índice (com interpolação) onde o sinal cruza um nível.

    Args:
        samples: Array de amostras
        level: Nível a ser cruzado
        direction: 'down' para sinal decrescente, 'up' para crescente

    Returns:
        Índice fracionário do cruzamento, ou None se não cruzar
    """
    for i in range(len(samples) - 1):
        if direction == 'down':
            # Procurar cruzamento descendente
            if samples[i] >= level and samples[i + 1] < level:
                # Interpolação linear para posição exata
                frac = (samples[i] - level) / (samples[i] - samples[i + 1])
                return i + frac
        else:
            # Procurar cruzamento ascendente
            if samples[i] <= level and samples[i + 1] > level:
                frac = (level - samples[i]) / (samples[i + 1] - samples[i])
                return i + frac

    return None


def _extrapolate_crossing(
    samples: np.ndarray,
    level: float
) -> Optional[float]:
    """
    Extrapola linearmente para encontrar quando o sinal cruzaria um nível.

    Usa os últimos pontos para estimar a tendência e extrapolar.

    Args:
        samples: Array de amostras
        level: Nível alvo

    Returns:
        Índice extrapolado, ou None se não for possível
    """
    if len(samples) < 10:
        return None

    # Usar últimos 20% dos dados para estimar tendência
    n_fit = max(10, len(samples) // 5)
    fit_samples = samples[-n_fit:]
    fit_indices = np.arange(len(samples) - n_fit, len(samples))

    # Regressão linear
    try:
        slope, intercept = np.polyfit(fit_indices, fit_samples, 1)
    except np.linalg.LinAlgError:
        return None

    if abs(slope) < 1e-6:
        return None  # Sinal praticamente constante

    # Encontrar onde a linha cruza o nível
    # level = slope * x + intercept
    # x = (level - intercept) / slope
    crossing_idx = (level - intercept) / slope

    # Limitar extrapolação a no máximo 2x o tamanho dos dados
    max_extrapolation = len(samples) * 2
    if crossing_idx < 0 or crossing_idx > max_extrapolation:
        return None

    return crossing_idx


def get_diagnostic_zone(To: float, Vo: float) -> str:
    """
    Determina a zona diagnóstica para um ponto (To, Vo).

    Baseado nos critérios do Vasoview:
    - VRT Normal: > 25 segundos
    - VRT Anormal: < 25 segundos

    Args:
        To: Tempo de reenchimento venoso (s)
        Vo: Potência da bomba venosa (%)

    Returns:
        String: "normal", "borderline" ou "abnormal"
    """
    # Zona vermelha (abnormal): To <= 20 OU Vo <= 2
    if To <= 20 or Vo <= 2:
        return "abnormal"

    # Zona amarela (borderline): 20 < To <= 25
    if 20 < To <= 25:
        return "borderline"

    # Zona amarela: triângulo de transição
    if To > 24:
        vo_limit = 4 - (To - 24) * 2 / 26
        if Vo <= vo_limit:
            return "borderline"

    return "normal"
