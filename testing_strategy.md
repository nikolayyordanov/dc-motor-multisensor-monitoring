# Hypothesis Testing Strategy

## Goal

Test whether smartphone audio (`sound_phone`) can replace instrument-grade signals (`sound_vibrometer`, `current`) for condition monitoring of the DC motor.

Primary claim to test:

- Phone-only models are non-inferior to instrument models for:
  - Condition classification
  - Load estimation

## Cohort and Fairness Rules

- Use only condition-load points with all 3 modalities present.
- Unit of independence is one condition-load recording group.
- Build a shared `group_id` for all modalities:
  - `group_id = condition + "__" + load_percent`
- Never split windows from the same recording group across train/test.
- Use identical grouped folds for all modalities.

## Targets

- Classification target: `condition` (8 classes)
- Regression target: `load_percent` (numeric)

## Preprocessing

- Phone audio (`m4a`): decode, mono mix, fixed time slice.
- Vibrometer waveform (`wav`): mono mix, fixed time slice.
- Current (`bin`): parse Rigol binary, fixed time slice, downsample to analysis rate.
- For all modalities:
  - Remove DC
  - Extract fixed summary feature vector from time and frequency domains

## Validation Design

- Main evaluation: GroupKFold with group-based leakage prevention.
- Optional stress tests (recommended next step):
  - Leave-one-load-out
  - Leave-one-condition-family-out

## Models

Use one model family per task across all modalities for fair comparison:

- Classification: RandomForestClassifier
- Regression: RandomForestRegressor

## Metrics

- Classification:
  - Macro F1 (primary)
  - Balanced accuracy
- Regression:
  - MAE in load-percent points (primary)
  - RMSE
  - R2

## Statistical Decision Layer

Paired fold-wise comparison between:

- Phone vs vibrometer
- Phone vs current

Compute:

- Fold deltas for Macro F1 and MAE
- Bootstrap 95% CI of deltas
- Wilcoxon signed-rank p-value

Non-inferiority margins (pre-registered):

- Macro F1 margin: 0.05
  - phone is non-inferior if CI low of delta F1 > -0.05
- MAE margin: 5.0 load-percent points
  - phone is non-inferior if CI high of delta MAE < +5.0

## Reproducibility

- Fixed random seed
- Saved manifest, features, fold metrics, and final report
- Single command to rerun pipeline

## Deliverables

Pipeline should generate:

- `pipeline_outputs/paired_manifest.csv`
- `pipeline_outputs/features_<modality>.csv`
- `pipeline_outputs/fold_metrics.csv`
- `pipeline_outputs/hypothesis_report.md`

## Run

```bash
.venv/Scripts/python.exe pipeline/benchmark_hypothesis.py \
  --dataset-root DCData_mendeley \
  --out-dir pipeline_outputs
```
