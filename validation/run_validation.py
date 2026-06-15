#!/usr/bin/env python3
"""
Reproducible validation harness for the D-PPG Manager software.

Computes every accuracy/agreement number reported in the manuscript directly
from the available data, with 95% confidence intervals, deterministically.

Data sources
------------
- Captured signals (raw PPG + hardware metadata) : data/ppg_data_20260212_132114.json
  (the only exams for which raw waveforms still exist; the original .DAT files
   for the historical exams no longer exist)
- Reference values (official Vasoscreen laudos)  : validation/reference_laudos.csv

Two modes are validated on the captured exams against the official references:
  * hardware-assisted : production algorithm using the 19-byte hw metadata
  * software-only      : production algorithm with algorithmic landmark detection

Reference-only descriptive statistics (grade distribution, bilateral asymmetry)
are computed on the full reference cohort (they do not require raw signals).

Usage:  python3 validation/run_validation.py
"""
import csv
import json
import os
import sys
from collections import defaultdict
from math import sqrt

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.analysis import calculate_parameters
from src.models import PPGBlock

SIGNALS_JSON = os.path.join(ROOT, "data", "ppg_data_20260212_132114.json")
REFERENCE_CSV = os.path.join(ROOT, "validation", "reference_laudos.csv")
PARAMS = ["To", "Th", "Ti", "Vo", "Fo"]
LIMB_LABEL_BYTE = {("MID", "with"): 0xE2, ("MID", "without"): 0xE1,
                   ("MIE", "with"): 0xE0, ("MIE", "without"): 0xDF}
RNG = np.random.default_rng(20260615)   # fixed seed -> reproducible bootstrap
N_BOOT = 10000


# --------------------------------------------------------------------------- #
# statistics helpers
# --------------------------------------------------------------------------- #
def boot_ci(x, stat=np.mean, n=N_BOOT):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return (float("nan"), float("nan"))
    idx = RNG.integers(0, len(x), size=(n, len(x)))
    bs = stat(x[idx], axis=1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h) * 100, (c + h) * 100


def grade(to):
    if to > 25:
        return "Normal"
    if to >= 20:
        return "I"
    if to >= 10:
        return "II"
    return "III"


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_reference():
    ref = {}
    with open(REFERENCE_CSV) as f:
        for r in csv.DictReader(f):
            ex = int(r["exam_number"])
            ref[ex] = {
                "patient": r["patient_id"], "limb": r["limb"], "tourniquet": r["tourniquet"],
                **{p: float(r[p]) for p in PARAMS},
            }
    return ref


def load_signals():
    with open(SIGNALS_JSON) as f:
        data = json.load(f)
    out = {}
    for b in data["blocks"]:
        out[b["exam_number"]] = b
    return out


def build_block(blk_json, ref_row, use_hw):
    lb = LIMB_LABEL_BYTE.get((ref_row["limb"], ref_row["tourniquet"]), 0xE2)
    block = PPGBlock(label_byte=lb,
                     samples=[int(x) for x in blk_json["samples"]],
                     exam_number=blk_json["exam_number"])
    if use_hw:
        hw = blk_json.get("hw_metadata") or {}
        mapping = {"baseline": "hw_baseline", "peak_index": "hw_peak_index",
                   "end_index": "hw_end_index", "amplitude": "hw_amplitude",
                   "To_samples": "hw_To_samples", "Th_samples": "hw_Th_samples",
                   "Ti_s": "hw_Ti", "Fo_x100": "hw_Fo_x100", "flags": "hw_flags"}
        ok = False
        for src_k, dst_k in mapping.items():
            if hw.get(src_k) is not None:
                setattr(block, dst_k, hw[src_k]); ok = True
        if not ok:
            return None
    return block


# --------------------------------------------------------------------------- #
# accuracy validation (one mode)
# --------------------------------------------------------------------------- #
def validate_mode(signals, ref, use_hw):
    errors = {p: [] for p in PARAMS}
    grades = []           # (computed_grade, reference_grade)
    tau_total = tau_ok = 0
    n_exams = 0
    for ex, blk_json in signals.items():
        if ex not in ref:
            continue
        block = build_block(blk_json, ref[ex], use_hw)
        if block is None:
            continue
        p = calculate_parameters(block)
        if p is None:
            continue
        n_exams += 1
        tau_total += 1
        if getattr(p, "tau", None):
            tau_ok += 1
        r = ref[ex]
        for pm in PARAMS:
            cv = getattr(p, pm)
            rv = r[pm]
            if rv != 0 and cv is not None:
                errors[pm].append(abs(cv - rv) / abs(rv) * 100)
        grades.append((grade(p.To), grade(r["To"])))

    rows = {}
    pooled = []
    for pm in PARAMS:
        e = errors[pm]
        pooled += e
        mlo, mhi = boot_ci(e, np.mean)
        dlo, dhi = boot_ci(e, np.median)
        rows[pm] = {"n": len(e), "mean": float(np.mean(e)), "median": float(np.median(e)),
                    "max": float(np.max(e)), "mean_ci": [mlo, mhi], "median_ci": [dlo, dhi]}
    plo, phi = boot_ci(pooled, np.mean)
    dlo, dhi = boot_ci(pooled, np.median)
    overall = {"n": len(pooled), "mean": float(np.mean(pooled)), "median": float(np.median(pooled)),
               "mean_ci": [plo, phi], "median_ci": [dlo, dhi]}

    agree = sum(1 for c, rr in grades if c == rr)
    conc = {"k": agree, "n": len(grades), "pct": agree / len(grades) * 100,
            "ci": wilson(agree, len(grades))}
    tau = {"k": tau_ok, "n": tau_total, "pct": tau_ok / tau_total * 100 if tau_total else 0,
           "ci": wilson(tau_ok, tau_total)}
    return {"n_exams": n_exams, "params": rows, "overall": overall,
            "concordance": conc, "tau": tau}


# --------------------------------------------------------------------------- #
# reference-only descriptive statistics
# --------------------------------------------------------------------------- #
def descriptive(ref):
    # grade distribution over all reference measurements
    counts = defaultdict(int)
    for r in ref.values():
        counts[grade(r["To"])] += 1
    n = sum(counts.values())
    dist = {g: {"n": counts[g], "pct": counts[g] / n * 100, "ci": wilson(counts[g], n)}
            for g in ["Normal", "I", "II", "III"]}

    # bilateral asymmetry on To, without-tourniquet pair, per patient
    by_pat = defaultdict(dict)
    for r in ref.values():
        if r["tourniquet"] == "without":
            by_pat[r["patient"]][r["limb"]] = r
    asym_to, asym_vo = [], []
    for pat, limbs in by_pat.items():
        if "MID" in limbs and "MIE" in limbs:
            a, b = limbs["MID"]["To"], limbs["MIE"]["To"]
            if max(a, b) > 0:
                asym_to.append(abs(a - b) / max(a, b) * 100)
            a, b = limbs["MID"]["Vo"], limbs["MIE"]["Vo"]
            if max(a, b) > 0:
                asym_vo.append(abs(a - b) / max(a, b) * 100)
    npat = len(asym_to)
    k20 = sum(1 for v in asym_to if v > 20)
    k40 = sum(1 for v in asym_to if v > 40)
    asym = {"n_patients": npat,
            "median_to": float(np.median(asym_to)),
            "gt20_pct": k20 / npat * 100, "gt20_ci": wilson(k20, npat),
            "gt40_pct": k40 / npat * 100, "gt40_ci": wilson(k40, npat)}
    return {"n_measurements": n, "n_patients": len(by_pat),
            "grade_distribution": dist, "asymmetry_to": asym}


# --------------------------------------------------------------------------- #
def fmt_ci(ci):
    return f"[{ci[0]:.1f}, {ci[1]:.1f}]"


def print_mode(title, res):
    print(f"\n{'='*72}\n{title}  (n = {res['n_exams']} exams)\n{'='*72}")
    print(f"{'Param':6}{'n':>4}{'mean':>9}{'median':>9}{'max':>7}   {'mean 95% CI':>16}   {'median 95% CI':>16}")
    for pm in PARAMS:
        r = res["params"][pm]
        print(f"{pm:6}{r['n']:>4}{r['mean']:>8.1f}%{r['median']:>8.1f}%{r['max']:>6.0f}%   "
              f"{fmt_ci(r['mean_ci']):>16}   {fmt_ci(r['median_ci']):>16}")
    o = res["overall"]
    print(f"{'ALL':6}{o['n']:>4}{o['mean']:>8.1f}%{o['median']:>8.1f}%{'':>6}   "
          f"{fmt_ci(o['mean_ci']):>16}   {fmt_ci(o['median_ci']):>16}")
    c = res["concordance"]
    print(f"\nGrade concordance (To): {c['k']}/{c['n']} = {c['pct']:.0f}%  "
          f"95% CI {fmt_ci(c['ci'])}")
    t = res["tau"]
    print(f"tau computed: {t['k']}/{t['n']} = {t['pct']:.0f}%  95% CI {fmt_ci(t['ci'])}")


def main():
    ref = load_reference()
    signals = load_signals()
    print(f"Reference cohort: {len(ref)} measurements, "
          f"{len(set(r['patient'] for r in ref.values()))} patients")
    print(f"Captured signals available: {len(signals)} exams")

    hw = validate_mode(signals, ref, use_hw=True)
    sw = validate_mode(signals, ref, use_hw=False)
    desc = descriptive(ref)

    print_mode("HARDWARE-ASSISTED MODE", hw)
    print_mode("SOFTWARE-ONLY MODE", sw)

    print(f"\n{'='*72}\nREFERENCE COHORT DESCRIPTIVE  "
          f"(n={desc['n_measurements']} meas., {desc['n_patients']} patients)\n{'='*72}")
    print("Grade distribution (by reference To):")
    for g in ["Normal", "I", "II", "III"]:
        d = desc["grade_distribution"][g]
        print(f"  {g:7} n={d['n']:>3} ({d['pct']:.0f}%)  95% CI {fmt_ci(d['ci'])}")
    a = desc["asymmetry_to"]
    print(f"\nBilateral asymmetry in To (without-tourniquet, n={a['n_patients']} patients):")
    print(f"  median asymmetry = {a['median_to']:.0f}%")
    print(f"  >20%: {a['gt20_pct']:.0f}%  95% CI {fmt_ci(a['gt20_ci'])}")
    print(f"  >40%: {a['gt40_pct']:.0f}%  95% CI {fmt_ci(a['gt40_ci'])}")

    out = {"hardware_assisted": hw, "software_only": sw, "descriptive": desc}
    with open(os.path.join(ROOT, "validation", "results.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved machine-readable results -> validation/results.json")


if __name__ == "__main__":
    main()
