#!/usr/bin/env python3
"""
Reproduces the central mechanistic claim of the manuscript: the venous refilling
time (To) cannot be recovered from the stored D-PPG waveform.

For the captured exams that carry the device's own metadata (which includes the
firmware's To_samples), we attempt to predict that To_samples from the raw signal
by (a) five mechanistic models and (b) a leave-one-out cross-validated linear
regression on signal features. None reproduces the firmware value, which (together
with the disassembly of dppg 2.dll) shows the endpoint is supplied by the device
or an operator marker, not computed from the waveform.

Usage:  python3 validation/to_recoverability.py
"""
import json
import os
import numpy as np
from scipy.optimize import curve_fit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS = os.path.join(ROOT, "data", "ppg_data_20260212_132114.json")
SR = 4.0
RNG = np.random.default_rng(20260615)


def load():
    blocks = [b for b in json.load(open(SIGNALS))["blocks"] if b.get("hw_metadata")]
    out = []
    for b in blocks:
        s = np.array(b["samples"], dtype=float)
        hw = b["hw_metadata"]
        if hw.get("To_samples") and hw.get("peak_index") is not None and hw.get("amplitude", 0) > 0:
            out.append((s, hw))
    return out


def rel_err(pred, true):
    return abs(pred - true) / true * 100 if true else np.nan


def _expm(t, A, tau, C):
    return A * np.exp(-t / tau) + C


def main():
    data = load()
    print(f"Captured exams with device metadata: {len(data)}\n")
    print("Each model predicts the firmware To_samples from the raw signal "
          "(baseline = mean of first 5 samples, peak = device peak_index).")
    print(f"{'Model':34}{'median rel-err':>16}{'mean rel-err':>14}")

    def report(name, errs):
        e = np.array([x for x in errs if np.isfinite(x)])
        print(f"{name:34}{np.median(e):>14.0f}% {np.mean(e):>12.0f}%")

    thr, tan, lin, expm, taum = [], [], [], [], []
    feats, target = [], []
    for s, hw in data:
        base = float(np.mean(s[:5]))
        pk = hw["peak_index"]
        peakval = s[pk] if pk < len(s) else s.max()
        amp = peakval - base
        to_hw = hw["To_samples"] / SR
        rec = s[pk:]
        if amp <= 0 or len(rec) < 12:
            continue
        # 1. threshold crossing at baseline
        cross = next((i for i in range(pk + 1, len(s)) if s[i] <= base), None)
        thr.append(rel_err((cross - pk) / SR, to_hw) if cross else 100.0)
        # 2. steepest-slope tangent extrapolated to baseline
        best = None
        for i in range(0, len(rec) - 8):
            sl = np.polyfit(np.arange(8), rec[i:i + 8], 1)[0]
            if sl < 0 and (best is None or sl < best[0]):
                best = (sl, i + 4, rec[i:i + 8].mean())
        if best:
            sl, mid, mv = best
            tan.append(rel_err((mid + (base - mv) / sl) / SR, to_hw))
        # 3. linear extrapolation To = W*amp/drop over 8 s
        W = int(8 * SR)
        if pk + W < len(s):
            drop = peakval - s[pk + W]
            if drop > 0:
                lin.append(rel_err(W * amp / drop / SR, to_hw))
        # 4 & 5. exponential fit -> tau; decay-to-epsilon and tau-multiple
        try:
            tt = np.arange(len(rec)) / SR
            p, _ = curve_fit(_expm, tt, rec, p0=[amp, 5, base], maxfev=5000,
                             bounds=([0, 0.3, base - 50], [np.inf, 300, base + 200]))
            tau = p[1]
            if p[0] > 3:
                expm.append(rel_err(tau * np.log(p[0] / 3), to_hw))   # decay to 3 ADC
            taum.append(rel_err(2.0 * tau, to_hw))                    # To ~ 2*tau
            # feature vector for regression
            fv = [amp, base, len(rec), tau,
                  *[peakval - (s[pk + int(k * SR)] if pk + int(k * SR) < len(s) else s[-1])
                    for k in (2, 3, 4, 6, 8)]]
            feats.append(fv)
            target.append(hw["To_samples"])
        except Exception:
            pass

    report("1. threshold crossing (baseline)", thr)
    report("2. steepest-slope tangent", tan)
    report("3. linear extrapolation (W*amp/drop)", lin)
    report("4. exponential decay to baseline", expm)
    report("5. time-constant multiple (2*tau)", taum)

    # leave-one-out CV linear regression
    X, y = np.array(feats), np.array(target, dtype=float)
    n = len(y)
    pred = np.zeros(n)
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        A = np.c_[np.ones(len(tr)), (X[tr] - mu) / sd]
        coef, *_ = np.linalg.lstsq(A, y[tr], rcond=None)
        pred[i] = coef[0] + coef[1:] @ ((X[i] - mu) / sd)
    r2 = 1 - np.sum((pred - y) ** 2) / np.sum((y - y.mean()) ** 2)
    print(f"\nLeave-one-out CV linear regression ({X.shape[1]} features, n={n}): "
          f"out-of-sample R2 = {r2:.2f}")
    print("\nConclusion: no closed-form mechanistic model reproduces the firmware To "
          "(all median errors >= ~30%). A flexible regression correlates To with signal "
          "features (R2 above), but that is a data-driven approximation, not the firmware's "
          "logic: the dppg 2.dll disassembly shows the endpoint is read as a stored input "
          "(device metadata or operator marker), never computed from the samples.")


if __name__ == "__main__":
    main()
