#!/usr/bin/env python3
"""
Análise detalhada de um exame específico para debug.
"""

import csv
import numpy as np
from collections import defaultdict
import sys

SAMPLING_RATE = 4.0

def analyze_exam(samples, exam_number):
    """Analisa um exame em detalhes."""
    samples = np.array(samples, dtype=float)

    print(f"\n{'='*60}")
    print(f"ANÁLISE DETALHADA DO EXAME {exam_number}")
    print(f"{'='*60}")
    print(f"Total de amostras: {len(samples)}")
    print(f"Duração: {len(samples)/SAMPLING_RATE:.1f}s")

    # Baselines
    initial_baseline = np.median(samples[:10])
    stable_baseline = np.median(samples[-20:])
    reference_baseline = max(stable_baseline, initial_baseline)

    print(f"\n--- BASELINES ---")
    print(f"Baseline inicial (mediana 0-9): {initial_baseline:.1f}")
    print(f"Baseline estável (mediana últimos 20): {stable_baseline:.1f}")
    print(f"Baseline referência (max): {reference_baseline:.1f}")

    # Estatísticas básicas
    print(f"\n--- ESTATÍSTICAS ---")
    print(f"Mínimo: {samples.min():.1f} (índice {np.argmin(samples)})")
    print(f"Máximo: {samples.max():.1f} (índice {np.argmax(samples)})")
    print(f"Média: {samples.mean():.1f}")

    # Detecção do pico (suavizado)
    window = 5
    smoothed = np.convolve(samples, np.ones(window)/window, mode='valid')
    offset = (window - 1) // 2

    search_start = max(10, int(len(smoothed) * 0.1))
    search_end = int(len(smoothed) * 0.9)

    peak_idx_smooth = np.argmax(smoothed[search_start:search_end]) + search_start
    peak_idx = peak_idx_smooth + offset
    peak_value = samples[peak_idx]

    print(f"\n--- DETECÇÃO DE PICO ---")
    print(f"Janela de busca: índices {search_start} a {search_end}")
    print(f"Pico suavizado no índice: {peak_idx_smooth}")
    print(f"Pico real no índice: {peak_idx} (tempo: {peak_idx/SAMPLING_RATE:.1f}s)")
    print(f"Valor no pico: {peak_value:.1f}")

    # Amplitudes
    amplitude_vo = peak_value - initial_baseline
    amplitude_ref = peak_value - reference_baseline

    print(f"\n--- AMPLITUDES ---")
    print(f"Amplitude (vs baseline inicial): {amplitude_vo:.1f}")
    print(f"Amplitude (vs baseline referência): {amplitude_ref:.1f}")

    # Vo
    Vo = (amplitude_vo / initial_baseline) * 100.0
    print(f"\n--- PARÂMETROS ---")
    print(f"Vo = ({amplitude_vo:.1f} / {initial_baseline:.1f}) × 100 = {Vo:.1f}%")

    # Thresholds (calibrados com 532 medições do banco Vasoview)
    th_threshold = initial_baseline + amplitude_vo * 0.50
    ti_threshold = reference_baseline + amplitude_ref * 0.25   # 75% recuperação (Ti/Th = 2.0)
    to_threshold = reference_baseline + amplitude_ref * 0.03

    print(f"\n--- THRESHOLDS ---")
    print(f"Th (50% recuperação): {th_threshold:.1f}")
    print(f"Ti (75% recuperação): {ti_threshold:.1f}")
    print(f"To (97% recuperação): {to_threshold:.1f}")

    # Tempos de cruzamento
    recovery_start = peak_idx
    recovery_samples = samples[recovery_start:]

    def find_crossing_time(threshold, name):
        for i, val in enumerate(recovery_samples):
            if val <= threshold:
                t = i / SAMPLING_RATE
                print(f"{name}: cruzou em índice {recovery_start + i} (t={t:.1f}s), valor={val:.1f}")
                return t
        print(f"{name}: NÃO cruzou! Mínimo na recuperação: {recovery_samples.min():.1f}")
        # Extrapolação
        if len(recovery_samples) >= 2:
            slope = (recovery_samples[-1] - recovery_samples[0]) / len(recovery_samples)
            if slope < 0:
                remaining = (recovery_samples[-1] - threshold) / abs(slope)
                t = (len(recovery_samples) + remaining) / SAMPLING_RATE
                print(f"  → Extrapolado para t={t:.1f}s")
                return t
        t = len(recovery_samples) / SAMPLING_RATE
        print(f"  → Usando duração da recuperação: t={t:.1f}s")
        return t

    print(f"\n--- TEMPOS DE CRUZAMENTO ---")
    Th = find_crossing_time(th_threshold, "Th")
    Ti = find_crossing_time(ti_threshold, "Ti")
    To = find_crossing_time(to_threshold, "To")

    Fo = Vo * Th

    print(f"\n--- RESULTADO FINAL ---")
    print(f"To = {To:.1f}s")
    print(f"Th = {Th:.1f}s")
    print(f"Ti = {Ti:.1f}s")
    print(f"Vo = {Vo:.1f}%")
    print(f"Fo = Vo × Th = {Vo:.1f} × {Th:.1f} = {Fo:.0f}%s")

    # Mostrar valores próximos ao pico
    print(f"\n--- VALORES PRÓXIMOS AO PICO (±10 amostras) ---")
    start = max(0, peak_idx - 10)
    end = min(len(samples), peak_idx + 11)
    for i in range(start, end):
        marker = " ← PICO" if i == peak_idx else ""
        print(f"  [{i:3d}] {samples[i]:.0f}{marker}")

    return {
        "To": round(To, 1),
        "Th": round(Th, 1),
        "Ti": round(Ti, 1),
        "Vo": round(Vo, 1),
        "Fo": round(Fo, 0),
    }


def main():
    if len(sys.argv) < 3:
        print("Uso: python3 analyze_exam.py <csv_file> <exam_number>")
        sys.exit(1)

    csv_file = sys.argv[1]
    target_exam = int(sys.argv[2])

    # Ler CSV e agrupar por exame
    exams = defaultdict(list)

    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            exam = int(row['exam_number'])
            value = int(row['value'])
            exams[exam].append(value)

    if target_exam not in exams:
        print(f"Exame {target_exam} não encontrado no arquivo.")
        print(f"Exames disponíveis: {sorted(exams.keys())}")
        sys.exit(1)

    samples = exams[target_exam]
    analyze_exam(samples, target_exam)


if __name__ == "__main__":
    main()
