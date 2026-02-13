"""
Análise e cálculo de parâmetros do sinal D-PPG.

Este módulo implementa os algoritmos de processamento de sinal
para extrair os parâmetros quantitativos da curva PPG.

MÉTODO: Baseado no pseudocódigo de dppg 2.dll (fcn.100182c0).
Algoritmos confirmados via engenharia reversa com radare2:

- To: Tempo entre pico e endpoint de recuperação (threshold ~97%)
      No original: To = (end_marker - peak) / sr (markers do hardware)
      Na nossa implementação: endpoint via threshold crossing a 3%
- Th: Tempo até 50% de recuperação (threshold crossing)
      Confirmado: shift-right por 1 (divisão por 2) em 0x100183AF
- Ti: Extrapolação linear adaptativa do slope inicial de recuperação
      NÃO usa threshold crossing. Usa janela de 3s ou 6s.
- Vo: Amplitude relativa ao baseline: (peak - baseline) / baseline × 100
- Fo: Integral (área sob curva) de peak a endpoint, normalizada
      NÃO é Vo × Th. É integral real com correção trapezoidal.

NOTA: A constante 0.125 encontrada em 0x10039d68 da DLL era usada para
layout de impressão, NÃO para cálculo de Ti. O Ti usa extrapolação
linear adaptativa, não cruzamento de threshold.
"""

from typing import Optional, List, Tuple
import numpy as np

from .config import ESTIMATED_SAMPLING_RATE, AnalysisParams
from .models import PPGParameters, PPGBlock


def calculate_parameters(block: PPGBlock) -> Optional[PPGParameters]:
    """
    Calcula os parâmetros quantitativos da curva D-PPG.

    Usa valores do hardware (baseline, peak, endpoint) quando disponíveis
    nos metadados do protocolo. Caso contrário, calcula por software.

    Args:
        block: Bloco PPG com as amostras (e opcionalmente hw_* metadata)

    Returns:
        PPGParameters com os valores calculados, ou None se inválido
    """
    samples = np.array(block.samples, dtype=float)

    if len(samples) < 40:
        return None

    sr = ESTIMATED_SAMPLING_RATE
    has_hw = (
        getattr(block, 'hw_baseline', None) is not None and
        getattr(block, 'hw_peak_index', None) is not None and
        getattr(block, 'hw_amplitude', None) is not None
    )

    # ================================================================
    # 1. BASELINE
    # ================================================================
    if has_hw:
        initial_baseline = float(block.hw_baseline)
    else:
        initial_baseline = float(np.median(samples[:10]))

    stable_baseline = float(np.median(samples[-20:]))

    # ================================================================
    # 2. PICO
    # ================================================================
    if has_hw and block.hw_peak_index < len(samples):
        peak_idx = block.hw_peak_index
        peak_value = float(samples[peak_idx])
    else:
        # Fallback: detecção por software
        window = AnalysisParams.SMOOTHING_WINDOW

        global_max = float(np.max(samples))
        estimated_amplitude = global_max - initial_baseline
        estimated_vo = (estimated_amplitude / initial_baseline) * 100.0 if initial_baseline > 0 else 0

        exercise_start = 5
        exercise_end = min(int(25 * sr), len(samples) - 10)

        if exercise_end <= exercise_start:
            return None

        if estimated_vo < AnalysisParams.LOW_AMPLITUDE_VO_THRESHOLD:
            peak_idx = int(exercise_start + np.argmax(samples[exercise_start:exercise_end]))
        else:
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

            peak_idx_smooth = np.argmax(smoothed[search_start:search_end]) + search_start
            peak_idx = peak_idx_smooth + offset

        peak_idx = min(peak_idx, len(samples) - 1)
        peak_value = float(samples[peak_idx])

    # ================================================================
    # 3. Vo (Venous Pump Power)
    # ================================================================
    if has_hw and block.hw_amplitude > 0:
        amplitude_vo = float(block.hw_amplitude)
    else:
        amplitude_vo = peak_value - initial_baseline

    if amplitude_vo <= 0 or initial_baseline <= 0:
        return None

    Vo = (amplitude_vo / initial_baseline) * 100.0

    if Vo < 0.5:
        return None

    # ================================================================
    # 4. TEMPOS
    # ================================================================
    recovery_start = peak_idx
    recovery_samples = samples[recovery_start:]

    if len(recovery_samples) < 10:
        return None

    sample_time = 1.0 / sr

    # ----------------------------------------------------------------
    # 4a. Th
    # ----------------------------------------------------------------
    if has_hw and block.hw_Th_samples is not None and block.hw_Th_samples > 0:
        Th = block.hw_Th_samples * sample_time
    else:
        level_Th = initial_baseline + amplitude_vo * AnalysisParams.THRESHOLD_TH
        Th_samples_val = _find_crossing(recovery_samples, level_Th, direction='down')
        if Th_samples_val is None:
            Th_samples_val = float(len(recovery_samples) - 1)
        Th = Th_samples_val * sample_time

    # ----------------------------------------------------------------
    # 4b. Ti
    # ----------------------------------------------------------------
    if has_hw and block.hw_Ti is not None and block.hw_Ti > 0:
        Ti = float(block.hw_Ti)
    else:
        Ti = _calculate_ti(samples, peak_idx, peak_value, initial_baseline, sr)

    # ----------------------------------------------------------------
    # 4c. To
    # ----------------------------------------------------------------
    hw_flags = getattr(block, 'hw_flags', None)
    if has_hw and block.hw_To_samples is not None and block.hw_To_samples > 0:
        To_samples_val = block.hw_To_samples
        To = To_samples_val * sample_time
    else:
        reference_baseline = max(stable_baseline, initial_baseline)
        amplitude_ref = peak_value - reference_baseline

        if amplitude_ref <= 0:
            amplitude_ref = amplitude_vo
            reference_baseline = initial_baseline

        level_To = reference_baseline + amplitude_ref * AnalysisParams.THRESHOLD_TO
        To_samples_val = _find_crossing(recovery_samples, level_To, direction='down')
        if To_samples_val is None:
            To_samples_val = _extrapolate_crossing(recovery_samples, level_To)
        To = To_samples_val * sample_time if To_samples_val else None

    # Validar resultados
    if Th is None or Ti is None or To is None:
        return None
    if To <= 0 or Th <= 0 or Ti <= 0:
        return None

    # ================================================================
    # 5. Fo (Integral da curva de recuperação)
    # ================================================================
    if has_hw and block.hw_Fo_x100 is not None and block.hw_Fo_x100 > 0:
        Fo = block.hw_Fo_x100 / 100.0
    else:
        if has_hw and block.hw_To_samples is not None:
            fo_end_idx = recovery_start + block.hw_To_samples
        elif To_samples_val is not None:
            fo_end_idx = recovery_start + int(To_samples_val)
        else:
            fo_end_idx = len(samples) - 1
        fo_end_idx = min(fo_end_idx, len(samples) - 1)
        Fo = _calculate_fo(samples, recovery_start, fo_end_idx, initial_baseline, sr)

    # ================================================================
    # 6. ÍNDICES PARA VISUALIZAÇÃO
    # ================================================================
    if has_hw and block.hw_end_index is not None:
        To_end_index = min(block.hw_end_index, len(samples) - 1)
    elif To_samples_val is not None:
        To_end_index = min(recovery_start + int(To_samples_val), len(samples) - 1)
    else:
        To_end_index = len(samples) - 1

    exercise_threshold = initial_baseline + amplitude_vo * 0.10
    exercise_start_index = 0
    for i in range(peak_idx):
        if samples[i] >= exercise_threshold:
            exercise_start_index = i
            break

    # ================================================================
    # 7. TAU (Exponential time constant)
    # ================================================================
    tau = _calculate_tau(samples, peak_idx, To_end_index, initial_baseline, peak_value, sr)

    return PPGParameters(
        To=round(To, 1),
        Th=round(Th, 1),
        Ti=round(Ti, 0),
        Vo=round(Vo, 1),
        Fo=round(Fo, 0),
        tau=tau,
        peak_index=peak_idx,
        To_end_index=To_end_index,
        exercise_start_index=exercise_start_index,
        baseline_value=initial_baseline,
        peak_value=peak_value,
    )


def _calculate_ti(
    samples: np.ndarray,
    peak_idx: int,
    peak_value: float,
    baseline: float,
    sr: float
) -> Optional[float]:
    """
    Calcula Ti usando extrapolação linear adaptativa.

    Algoritmo confirmado via pseudocódigo de dppg 2.dll (0x10018460-0x10018520):
    1. Verifica queda do sinal nos primeiros 3 segundos após o pico
    2. Se queda >= 10 unidades ADC: usa janela de 3s (decaimento rápido)
    3. Se queda < 10: usa janela de 6s (decaimento lento)
    4. Extrapola: Ti = janela × amplitude / queda_na_janela

    Args:
        samples: Array completo de amostras
        peak_idx: Índice do pico
        peak_value: Valor do pico (ADC)
        baseline: Valor do baseline (ADC)
        sr: Taxa de amostragem (Hz)

    Returns:
        Ti em segundos, ou None se não for possível calcular
    """
    amplitude = peak_value - baseline
    if amplitude <= 0:
        return None

    # Verificar queda nos primeiros 3 segundos
    offset_3sec = peak_idx + int(AnalysisParams.TI_FAST_WINDOW * sr)

    if offset_3sec >= len(samples):
        # Não há dados suficientes para calcular Ti
        return None

    delta_3sec = peak_value - samples[offset_3sec]

    # Escolher janela adaptativa
    if delta_3sec >= AnalysisParams.TI_DELTA_THRESHOLD:
        window_periods = AnalysisParams.TI_FAST_WINDOW  # 3 segundos
    else:
        window_periods = AnalysisParams.TI_SLOW_WINDOW  # 6 segundos

    # Índice do alvo na janela escolhida
    target_idx = peak_idx + int(window_periods * sr)
    if target_idx >= len(samples):
        # Usar último sample disponível se não houver dados suficientes
        target_idx = len(samples) - 1
        # Ajustar janela efetiva
        window_periods = (target_idx - peak_idx) / sr

    target_value = samples[target_idx]
    denominator = peak_value - target_value

    if denominator <= 0:
        # Sinal não está recuperando: overflow
        return AnalysisParams.TI_MAX_SECONDS

    # Extrapolação linear: Ti = janela × amplitude / queda
    Ti = window_periods * amplitude / denominator

    # Cap em 120 segundos (como o Vasoview faz)
    if Ti > AnalysisParams.TI_MAX_SECONDS:
        Ti = AnalysisParams.TI_MAX_SECONDS

    return float(Ti)


def _calculate_fo(
    samples: np.ndarray,
    peak_idx: int,
    end_idx: int,
    baseline: float,
    sr: float
) -> float:
    """
    Calcula Fo usando integração real (área sob a curva de recuperação).

    Algoritmo confirmado via pseudocódigo de dppg 2.dll (0x10018520-0x100186EB):
    1. Soma (sample[i] - baseline) de peak a end
    2. Aplica correção trapezoidal para excesso residual
    3. Normaliza: × 100 / baseline / sr → resultado em %×s

    Args:
        samples: Array completo de amostras
        peak_idx: Índice do pico (início da integração)
        end_idx: Índice do endpoint (fim da integração)
        baseline: Valor do baseline (ADC)
        sr: Taxa de amostragem (Hz)

    Returns:
        Fo em %×s (percent × seconds)
    """
    if end_idx <= peak_idx or baseline <= 0:
        return 0.0

    # Garantir limites válidos
    end_idx = min(end_idx, len(samples) - 1)

    # Soma de (sample - baseline) de peak a end
    segment = samples[peak_idx:end_idx]
    area = float(np.sum(segment - baseline))

    # Correção trapezoidal: subtrai metade do retângulo residual
    # Isso compensa o fato de que o sinal pode não ter retornado
    # completamente ao baseline no endpoint
    last_excess = float(samples[end_idx] - baseline)
    n_samples = end_idx - peak_idx
    correction = last_excess * n_samples / 2.0

    adjusted = area - correction

    # Normalizar para %×s
    # area está em ADC×amostras, baseline em ADC, sr em Hz
    # Fo = area / baseline × 100 / sr = %×s
    Fo = adjusted * 100.0 / (baseline * sr)

    return max(Fo, 0.0)


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
            if samples[i] >= level and samples[i + 1] < level:
                frac = (samples[i] - level) / (samples[i] - samples[i + 1])
                return i + frac
        else:
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

    Usado apenas para To quando o sinal não atinge o threshold de recuperação
    dentro da gravação.

    Args:
        samples: Array de amostras
        level: Nível alvo

    Returns:
        Índice extrapolado (em amostras), ou None se não for possível
    """
    if len(samples) < 10:
        return None

    n_fit = min(AnalysisParams.EXTRAPOLATION_FIT_SAMPLES, len(samples) // 2)
    n_fit = max(n_fit, 5)

    last_samples = samples[-n_fit:]
    last_value = float(samples[-1])

    slope = (last_samples[-1] - last_samples[0]) / (n_fit - 1)

    if slope >= 0:
        max_samples = AnalysisParams.MAX_EXTRAPOLATION_TIME * ESTIMATED_SAMPLING_RATE
        return max_samples

    remaining = last_value - level

    if remaining <= 0:
        return float(len(samples) - 1)

    additional_samples = remaining / abs(slope)
    crossing_idx = len(samples) - 1 + additional_samples

    max_samples = AnalysisParams.MAX_EXTRAPOLATION_TIME * ESTIMATED_SAMPLING_RATE
    if crossing_idx > max_samples:
        crossing_idx = max_samples

    return crossing_idx


def _calculate_tau(
    samples: np.ndarray,
    peak_idx: int,
    end_idx: int,
    baseline: float,
    peak_value: float,
    sr: float,
) -> Optional[float]:
    """
    Fit exponential decay y(t) = A * exp(-t/τ) + C to the recovery phase.

    τ represents the speed of venous refilling — larger τ means slower
    refilling (better venous function).

    Args:
        samples: Array of all samples
        peak_idx: Index of the peak
        end_idx: Index of the recovery endpoint
        baseline: Baseline ADC value
        peak_value: Peak ADC value
        sr: Sampling rate (Hz)

    Returns:
        τ in seconds, or None if fit fails
    """
    if end_idx <= peak_idx:
        return None

    segment = samples[peak_idx:end_idx + 1]
    if len(segment) < 10:
        return None

    t = np.arange(len(segment)) / sr
    y = np.array(segment, dtype=float)

    A0 = peak_value - baseline
    if A0 <= 0:
        return None
    tau0 = (end_idx - peak_idx) / sr / 3.0

    try:
        from scipy.optimize import curve_fit

        def exp_decay(t, A, tau, C):
            return A * np.exp(-t / tau) + C

        popt, _ = curve_fit(exp_decay, t, y, p0=[A0, tau0, baseline], maxfev=5000)
        tau = abs(popt[1])
        if tau < 0.5 or tau > 200:
            return None
        return round(tau, 1)
    except Exception:
        return None


def bilateral_asymmetry(
    params_mie: PPGParameters,
    params_mid: PPGParameters,
) -> dict:
    """Calculate bilateral asymmetry index for each parameter.

    Asymmetry = |param_MIE - param_MID| / max(param_MIE, param_MID) × 100

    Args:
        params_mie: Parameters for left leg (MIE)
        params_mid: Parameters for right leg (MID)

    Returns:
        Dict mapping parameter name to asymmetry percentage.
        Example: {"To": 35.7, "Vo": 33.3, "tau": 12.5}
    """
    result = {}
    for attr in ("To", "Vo", "tau"):
        val_mie = getattr(params_mie, attr, None)
        val_mid = getattr(params_mid, attr, None)
        if val_mie is not None and val_mid is not None and val_mie > 0 and val_mid > 0:
            denom = max(val_mie, val_mid)
            result[attr] = round(abs(val_mie - val_mid) / denom * 100, 1)
    return result


def tourniquet_effect(
    params_sem: PPGParameters,
    params_com: PPGParameters,
) -> dict:
    """Calculate tourniquet effect as % change.

    Positive = improvement (To increased), negative = worsening (To decreased).

    Args:
        params_sem: Parameters without tourniquet
        params_com: Parameters with tourniquet

    Returns:
        Dict with keys "To_pct" and "Vo_pct" (% change).
    """
    result = {}
    if params_sem.To > 0:
        result["To_pct"] = round((params_com.To - params_sem.To) / params_sem.To * 100, 1)
    if params_sem.Vo > 0:
        result["Vo_pct"] = round((params_com.Vo - params_sem.Vo) / params_sem.Vo * 100, 1)
    return result


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
    if To <= 20 or Vo <= 2:
        return "abnormal"

    if 20 < To <= 25:
        return "borderline"

    if To > 24:
        vo_limit = 4 - (To - 24) * 2 / 26
        if Vo <= vo_limit:
            return "borderline"

    return "normal"
