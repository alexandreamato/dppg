The issue stemmed from `dppg_reader.py` using outdated, uncalibrated parameters for the `Th` and `Ti` thresholds in its `calculate_parameters` function. These discrepancies were identified by comparing `dppg_reader.py` with `calibrate.py` and `analyze_exam.py`, which contained the correct, calibrated values.

To resolve this, I have made the following changes in `dppg_reader.py`:

1.  **Updated `Th` Threshold**: Changed `level_Th = initial_baseline + amplitude_vo * 0.50` to `level_Th = initial_baseline + amplitude_vo * 0.48`.
    *   **Reasoning**: The calibrated value for the `Th` threshold (52% recovery) was found to be `0.48`, not `0.50`. This adjustment ensures that the calculation for `Th` (related to systolic activity) is more accurate.

2.  **Updated `Ti` Threshold**: Changed `level_Ti = reference_baseline + amplitude_ref * 0.125` to `level_Ti = reference_baseline + amplitude_ref * 0.12`.
    *   **Reasoning**: The calibrated value for the `Ti` threshold (88% recovery) was found to be `0.12`, not `0.125`. This adjustment ensures that the calculation for `Ti` (related to diastolic activity) is more accurate.

These modifications directly apply the developer's own calibrated findings, which should significantly reduce the discrepancy between the `dppg-reader`'s output and the official software's results.