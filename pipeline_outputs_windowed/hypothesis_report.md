# Hypothesis Benchmark Report

## Data and Protocol

- Paired groups used: 97
- Grouped folds: 5
- Segment offset (s): 0.0
- Current-duration eligibility (s): >= 20 (tolerance 0.001)
- Analysis span: longest common span of the three paired modalities
- Analysis duration range (s): 19.904-20.000
- User-specified duration cap (s): 20.0
- Window duration (s): 2.0
- Window overlap: 50%
- Predictions aggregated at recording level
- Random seed: 42

## Cross-Validation Metrics (mean over folds)

| Modality | Macro F1 | Balanced Acc | MAE | RMSE | R2 |
|---|---:|---:|---:|---:|---:|
| current | 0.4324 | 0.4708 | 2.7031 | 4.2114 | 0.9804 |
| sound_phone | 0.7380 | 0.7625 | 5.6819 | 7.5414 | 0.9362 |
| sound_vibrometer | 0.2153 | 0.2667 | 3.2772 | 5.7514 | 0.9616 |

## Phone Non-Inferiority Checks

Margins:
- Macro F1 delta margin: -0.05
- MAE delta margin: +5.0 load-percent points

| Comparison | Delta F1 mean | Delta F1 95% CI | Delta MAE mean | Delta MAE 95% CI | Overall non-inferior |
|---|---:|---|---:|---|---|
| phone - sound_vibrometer | 0.5227 | [0.4555, 0.6065] | 2.4047 | [0.7032, 4.2180] | True |
| phone - current | 0.3056 | [0.2001, 0.3952] | 2.9788 | [1.4284, 4.6308] | True |

## Notes

- This is a baseline tabular-feature benchmark using one fixed model family across modalities.
- Use this as a reproducible reference point before moving to larger deep models.