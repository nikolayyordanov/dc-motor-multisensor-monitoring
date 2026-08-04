# Hypothesis Testing Strategy

## Goal

Test whether smartphone audio (`sound_phone`) can replace instrument-grade signals (`sound_vibrometer`, `current`) for condition monitoring of the DC motor.

Primary claim to test:

- Phone-only models are non-inferior to instrument models for:
  - Condition classification
  - Load estimation

## Unified Protocol

Use one pre-registered analysis path for every sensor, condition, load, and
reversal state. Do not select a different window duration, overlap, feature
set, model family, or validation split after looking at a particular class.

- Exclude a condition-load group when its actual current payload is shorter
  than 20 seconds (with 1 ms tolerance for binary timing precision).
- Use up to 20 seconds from the start of each retained recording. The span is
  bounded by the shortest actual modality payload in that paired group.
- Use 2-second windows with 50% overlap for all conditions and states.
- Treat windows as repeated views of a recording, not independent samples.
- Keep every window from a recording in one fold and give each recording equal
  total training weight.
- Aggregate window predictions before calculating any metric.
- Use the 8-class `condition` label as the primary unified classification
  endpoint. It jointly represents operation family and reversal state.
- Report operation family, reversal state, mechanical condition, and load as
  secondary endpoints using the same windows and recording-level folds.
- Apply the same model family and hyperparameter-selection procedure to each
  sensor. Sensor-specific decoding and calibration are allowed, but the
  downstream statistical protocol must remain identical.

The 2-second window is the common compromise: it contains about 6.6 rotations
at the documented low-speed point of approximately 200 RPM, remains shorter
than the 4-second reversal period, and provides enough samples for all three
modalities. Fifty-percent overlap supplies 18 or 19 aligned temporal views,
depending on whether the shortest paired recording reaches the full 20 seconds.
Recording-equalized weights prevent these counts from changing each recording's
total training influence.

## Cohort and Fairness Rules

- Use only condition-load points with all 3 modalities present.
- Unit of independence is one condition-load recording group.
- Build a shared `group_id` for all modalities:
  - `group_id = condition + "__" + load_percent`
- Never split windows from the same recording group across train/test.
- Use identical grouped folds for all modalities.

## Targets

- Primary classification target:
  - Composite `condition` label (8 classes)
- Secondary classification targets:
  - Mechanical condition: normal vs loose foundation
  - Direction reversal: no vs yes
  - Operation family: normal, loose foundation, suboptimal control, suboptimal control RT
- Regression target: `load_percent` (numeric)

## Preprocessing

- Phone audio (`m4a`): decode, mono mix, fixed time slice.
- Vibrometer waveform (`wav`): mono mix, fixed time slice.
- Current (`bin`): parse Rigol binary, fixed time slice, downsample to analysis rate.
- Begin at the start of each recording and calculate each paired group's
  analysis span as the shortest actual duration among phone, vibrometer, and
  current, capped at 20 seconds. Probe
  compressed-audio container timing and Rigol payload timing rather than
  trusting missing or inaccurate metadata. This uses all common data while
  preserving identical temporal coverage across sensors.
- Divide each recording into 2-second windows with 50% overlap. At the target rates, each window contains 32,000 phone/vibrometer samples or 40,000 current samples.
- For all modalities:
  - Remove DC
  - Extract fixed summary feature vector from time and frequency domains
- No amplitude normalization is currently applied. RMS and peak-related features remain available to the model.
- Resampling and current downsampling must use an anti-alias filter.

## Validation Design

- Main evaluation: stratified grouped cross-validation with identical folds for every modality, reported from aggregated out-of-fold predictions.
- Validation-sensitivity evaluation: leave-one-load-level-out using the same recording-level aggregation.
- Assign every window from an original recording to the same fold.
- Weight training windows inversely by the number of windows in their recording, so every recording has equal total weight.
- Average class probabilities and take the median load estimate across windows before calculating recording-level metrics.
- GroupKFold over unique recording IDs alone is insufficient evidence because every condition-load pair has only one recording.
- A replacement claim requires an external validation campaign with repeated acquisitions across days, phone positions, and mounting cycles.

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

## Interpretation Constraint

The current dataset has one separately recorded file per sensor and condition-load point. Condition labels can therefore be confounded with recording session, ambient sound, phone automatic gain control, or acquisition order. High smartphone performance on these files does not by itself establish that a phone generalizes better than a contact vibrometer or current probe.

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
  --out-dir pipeline_outputs \
  --window-seconds 2 \
  --window-overlap 0.5
```
