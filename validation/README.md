# Validation harness

Reproducible, deterministic validation of the D-PPG Manager parameter algorithms
against the official Elcat Vasoscreen reports. Supports the accuracy and agreement
figures reported in the manuscript (Jornal Vascular Brasileiro, JVB-2026-0036).

## Run

```bash
python3 validation/run_validation.py
```

Outputs the accuracy tables (hardware-assisted and software-only modes), the
reference-cohort descriptive statistics, and writes machine-readable results to
`results.json`. All confidence intervals are reproducible: bootstrap (10,000
resamples, fixed seed) for errors, Wilson score for proportions.

## Data availability

- `reference_laudos.csv` — **de-identified** reference parameter values extracted
  from the official Vasoscreen reports (223 measurements, 56 patients), identified
  only by sequential exam number and anonymous patient id (P001–P056), in line with
  the ethics approval (CEP Hospital Moriah, CAAE 96775026.3.0000.8054). Drives the
  descriptive statistics (grade distribution, bilateral asymmetry).
- `results.json` — committed snapshot of the computed results.
- The **raw PPG waveforms** required for the accuracy tables (hardware-assisted and
  software-only modes) are restricted patient data and are **not** shared
  (`data/ppg_data_*.json`, git-ignored). The accuracy tables are therefore
  reproducible only on the institutional dataset; the analysis code, however, is
  fully open for inspection.

## Notes

- Raw waveforms survive for 37–42 directly-captured exams; the original `.DAT`
  files for the remaining historical exams no longer exist.
- Hardware-assisted mode consumes the device's exported 19-byte metadata
  (baseline, peak, endpoint). Software-only mode detects these landmarks
  algorithmically; the venous-refilling-time endpoint is set by the device firmware
  or by an operator marker and is not recoverable from the waveform (see manuscript
  Discussion), which bounds software-only accuracy for To/Ti.
