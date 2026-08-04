# Hypothesis Benchmark Report

## Data and Protocol

- Paired groups used: 98
- Grouped folds: 5
- Segment offset (s): 1.0
- Segment duration (s): 4.0
- Random seed: 42

## Cross-Validation Metrics (mean over folds)

| Modality | Macro F1 | Balanced Acc | MAE | RMSE | R2 |
|---|---:|---:|---:|---:|---:|
| current | 0.5469 | 0.5708 | 7.7905 | 11.6821 | 0.8540 |
| sound_phone | 0.7542 | 0.7875 | 8.8812 | 11.8588 | 0.8625 |
| sound_vibrometer | 0.3657 | 0.3708 | 3.8873 | 6.2173 | 0.9607 |

## Phone Non-Inferiority Checks

Margins:
- Macro F1 delta margin: -0.05
- MAE delta margin: +5.0 load-percent points

| Comparison | Delta F1 mean | Delta F1 95% CI | Delta MAE mean | Delta MAE 95% CI | Overall non-inferior |
|---|---:|---|---:|---|---|
| phone - sound_vibrometer | 0.3886 | [0.2532, 0.5477] | 4.9939 | [3.8510, 6.0708] | False |
| phone - current | 0.2073 | [0.1218, 0.2912] | 1.0907 | [-0.5008, 2.9479] | True |

## Notes

- This is a baseline tabular-feature benchmark using one fixed model family across modalities.
- Use this as a reproducible reference point before moving to larger deep models.