# Algorithms Journal Paper: Titles, Contributions and Evaluation Plan

Planning date: 2026-10-13. This document records proposed research directions,
not established results or a guarantee of journal suitability. Select the final
title and contributions after completing the experiments.

## 1. Positioning and dataset constraints

The paper should investigate an algorithmic method or a rigorous evaluation
question, rather than repeat the dataset-description article or merely rank
several classifiers.

The available dataset comprises 98 operating points and 385 measurement files,
plus one oscilloscope setup file. Sensors were acquired sequentially under
matched conditions, not synchronously. Each sensor has one recording per
available operating point; there are no independent repeated acquisition
sessions. Seven XLS files are missing, and one current recording is truncated.

Relevant constraints:

- One brushed DC motor, one laboratory rig and no externally applied load.
- Labels describe normal operation, regulator tuning, loose foundation and
  reversal; they are not exclusively fault labels.
- Speed percentages are commanded setpoints, not independently measured RPM.
- Ordinary suboptimal speed-regulator tuning stops at 65%; other states reach
  100%. This unequal coverage can create classification shortcuts.
- Phone audio is from one Huawei P smart Z; results cannot establish
  generalization to different phones, rooms or acquisition sessions.
- Current samples are exported channel volts; conversion to amperes was not
  recorded. Vibrometer WAV amplitude is digital full-scale amplitude, not
  calibrated physical vibration amplitude.

Use the latest manually maintained [dataset description](../DCData_mendeley/README.md)
as the source of acquisition details.

## 2. Top three title choices

### Option 1 — Condition-level multimodal method

**Condition-Matched Multimodal Learning for Speed-Setpoint Estimation and
Operating-State Classification of a Brushed DC Motor**

Best suited to a methods-oriented paper, if a proposed fusion method provides
a demonstrable benefit over strong simpler baselines.

**Research question:** Can reliability-aware condition-level fusion improve
both prediction tasks without assuming sensor synchronization?

Possible contributions:

1. A fusion algorithm for independently acquired current, vibrometer and
   smartphone recordings, using recording-level representations.
2. A joint formulation for setpoint regression and operating-state classification,
   if both objectives genuinely share a learned model or representation.
3. A regularized reliability gate that adapts modality weights using quality
   indicators and handles absent or degraded modalities.
4. Evidence identifying when fusion helps, and when a single sensor is sufficient.

Candidate method: combine modality predictions through a small learned gate,
using quality indicators such as clipping fraction, usable duration and signal
stability. Quality indicators are hypotheses about reliability, not guaranteed
indicators: reversal and controller behavior can legitimately change stability.
Learn gate parameters only from training data. Use grouped out-of-fold training
predictions for stacking, never in-sample predictions or held-out test labels.

Required comparisons and ablations:

- Single-modality models; feature concatenation; equal-weight late fusion;
  regularized learned fusion; proposed quality-aware fusion.
- Fusion with versus without quality indicators.
- Separate-task models versus genuinely joint-task learning.
- Missing-modality and synthetic-degradation tests.
- Smartphone's incremental benefit beyond current and vibrometer.
- Recording-level aggregation versus different window-level pooling strategies.

Do not pair arbitrary segments from sequential recordings as simultaneous
observations. Fuse at the matched operating-point level after aggregation.

### Option 2 — Rigorous sensor-comparison evaluation

**Smartphone Audio versus Instrumented Measurements for Brushed DC Motor
Monitoring: A Leakage-Aware Evaluation**

Most feasible starting point. A publishable contribution would require a
substantive finding about evaluation bias, speed confounding or sensor ranking,
not simply a classifier leaderboard.

**Research question:** Does smartphone audio retain operating-state information
when recording leakage and speed-coverage confounding are controlled?

Possible contributions:

1. A controlled analysis of performance inflation under inappropriate splitting.
2. A fair cross-modality comparison using identical held-out operating points.
3. An analysis of operating-state information versus speed-related shortcuts.
4. Reproducible splits, out-of-fold predictions and uncertainty estimates.

Evaluate the following protocols separately:

| Protocol | Purpose |
|---|---|
| Random segment split | Diagnostic demonstration of leakage; not the primary estimate of generalization |
| Grouped split by operating point | Prediction on held-out operating-point recordings |
| Leave-one-speed-setpoint-out | Generalization to an unseen commanded speed |
| Common-speed subset across states | Reduce shortcuts from unequal speed coverage |

Compare known-setpoint-only classification, simple amplitude/statistical
features, spectral features and time–frequency representations. Compare models
with and without explicit speed conditioning. Restrict the main eight-condition
comparison to shared setpoints when assessing speed generalization; at speeds
where states are absent, report results as a restricted-label experiment rather
than implying full-state evaluation.

### Option 3 — Cross-speed representation method

**Cross-Speed Generalization for Brushed DC Motor Operating-State Classification
Using Speed-Conditioned Signal Representations**

Best suited to a focused algorithmic contribution if the representation improves
unseen-speed classification relative to conventional features.

**Research question:** Can speed-aware representations distinguish operating
states while reducing nuisance variation caused by commanded speed?

Possible contributions:

1. A representation separating speed-dependent features from state information.
2. A speed-conditioned classifier or regularized feature transformation.
3. Separate evaluation of interpolation and extrapolation across speed.
4. Analysis of which features transfer across speeds and sensor modalities.

Candidate methods:

- Feature residualization: fit normal-state feature dependence on speed using
  training data, then classify departures from that expected behavior.
- A classifier conditioned on commanded speed, compared with an unconditioned
  classifier and a speed-only baseline.
- Multi-scale features separating fixed-frequency converter signatures from
  speed-dependent signal components.
- A compact learned representation, justified against simpler regularized models.

Evaluate leave-one-speed-out and held-out contiguous speed bands, distinguishing
interpolation from extrapolation. All reference trends and transformations must
be fitted inside training folds. Commanded speed is not measured rotational
speed: do not describe setpoint-based frequency scaling as true order tracking.
State explicitly whether the setpoint is available at inference. If not, any
estimated-speed conditioning must be trained and evaluated without test leakage.

## 3. Recommended study sequence

Begin with Option 2 as the evaluation foundation. Then test quality-aware fusion
(Option 1) or speed-conditioned representations (Option 3). Choose the final
paper direction according to supported results, including informative negative
results. Do not select the most complex architecture merely to imply novelty.

### 3.1 Define targets before model selection

- Classification: eight combined conditions, or four operating states with a
  separate reversal label. Consider reporting both, because easy reversal
  detection may obscure regulator-tuning or looseness discrimination.
- Regression: commanded speed percentage. Report MAE in percentage points of
  rated-speed setpoint, not measured-RPM error.
- Call the method multi-task learning only if objectives share learned parameters;
  two independent models are dual-task evaluation.

### 3.2 Establish strong baselines

Start with statistical and spectral features, regularized linear models, SVMs
and tree-based ensembles. Add a compact neural model only with a clear rationale.
Use identical outer splits and comparable tuning budgets across methods.

### 3.3 Separate model selection from assessment

- Use nested grouped validation where feasible; predefine primary protocols.
- Keep every sensor recording and every window from an operating point in the
  same fold, including comparisons between modalities.
- Fit scaling, feature selection, reference trends and fusion weights using
  training folds only.
- Select window lengths and quality thresholds without inspecting test results.
- Use operating-point/recording-level predictions as primary outcomes. Aggregate
  segment probabilities or predictions using a specified training-selected rule.
- Evaluate waveform modalities on a common inventory; if including XLS, report
  the reduced complete-case inventory or a missing-data method fitted in training.
- Handle the truncated current file consistently and document inclusion/exclusion.

### 3.4 Report outcomes and uncertainty

- Classification: macro-F1, balanced accuracy, confusion matrix and per-class recall.
- Regression: setpoint MAE and errors stratified by speed and operating state.
- Fusion: paired improvement over the strongest single-modality baseline.
- Practicality: training/inference time, model size and computational requirements.
- Uncertainty: paired comparisons on the same held-out operating points, with
  grouping respected in resampling and uncertainty estimates.
- Do not use windows or repeated CV folds as independent observations in tests.
  Fold estimates share training data. Define the resampling unit and state that
  uncertainty is conditional on this single-rig dataset, not cross-session evidence.
- Avoid selecting a winner from many comparisons without reporting the search
  scope and addressing multiple testing where applicable.

### 3.5 Mechanism and sensitivity experiments

Evaluate window length, overlap and aggregation; inclusion/exclusion of quiet
starts; clipped versus less-clipped recordings; feature families; sensor
combinations; synthetic noise; missing modalities; and shortened recordings.
Preserve raw files. Record all exclusions and preprocessing choices.

Synthetic degradation tests assess the specified perturbations; they do not
demonstrate robustness to new devices, rooms or independently acquired sessions.

## 4. Segments are not repeated acquisitions

Dividing one recording into multiple windows creates segment-level observations,
not independent experimental repetitions. Windows share the acquisition session,
sensor placement, instrument settings and operating trajectory. Adjacent and
overlapping windows are correlated.

Valid uses of segmentation:

- Learn local temporal/spectral patterns.
- Quantify within-recording variability.
- Compare window lengths and pool predictions at recording level.
- Analyze steady-state portions and reversal transitions separately.

Keep all windows of a recording—and all modalities of its operating point—in
one split. Twenty 1-second windows from a 20-second recording do not constitute
twenty independent acquisitions or an independent sample size of twenty.

| Variability measure | Interpretation |
|---|---|
| SD across waveform windows | Temporal variation within an acquisition |
| SD across XLS readings | Variation among instrument readings at that operating point |
| Variation across new acquisition runs | Acquisition repeatability, depending on what is reset or changed |

Suggested manuscript wording:

> Each sensor was recorded once at each available operating point. Recordings
> were divided into analysis windows to obtain segment-level observations; these
> windows were not treated as independent acquisition repetitions. All windows
> and sensor recordings associated with an operating point were assigned to the
> same evaluation split.

The current data can support held-out-operating-point and held-out-setpoint
evaluation, but not direct evidence of acquisition repeatability or cross-session
robustness. Holding out a speed is also not evidence of generalization to a new motor.

## 5. Most valuable additional acquisition

If feasible, reacquire measurements in independent runs across different days
or sessions, recording session IDs and the conditions deliberately reset.
Repeat operating points; document sensor placement, phone orientation, recording
app/settings, mounting and instrument settings. Controlled placement changes can
support a separately defined robustness study. Additional motors would address
cross-machine transfer, which repeated sessions of one motor cannot establish.

Keep whole sessions outside training and model selection for a genuine
session-held-out assessment. Repeated CV partitions of the existing data do not
substitute for new physical acquisition.

## 6. Literature research and novelty check

Research these topics before claiming a new algorithm:

1. Recording/subject/session leakage and grouped or nested validation in signal ML.
2. Small-sample multimodal late fusion, reliability gating and missing modalities.
3. Speed/domain generalization, condition-dependent features and feature residualization.
4. Joint regression/classification and negative transfer between tasks.
5. Smartphone acoustic motor monitoring, including calibration and device variability.
6. Statistical comparison of cross-validated models and uncertainty with correlated data.

Build a literature matrix recording each study's task, machine, sensors,
synchronization, independent acquisition count, split unit, validation protocol,
baselines, method and code availability. Identify the precise gap rather than
claiming novelty simply because the dataset is new. Check current Algorithms
scope and author requirements before submission.

## 7. Proposed manuscript structure

1. Introduction: focused research question and explicitly bounded contributions.
2. Related work: algorithmic/evaluation gap established from the literature matrix.
3. Dataset and tasks: concise description citing the dataset article/repository.
4. Proposed method or evaluation framework: assumptions and implementation details.
5. Experimental design: preprocessing, grouped splits, tuning, baselines and metrics.
6. Results: primary outcomes, uncertainty, ablations and sensitivity analyses.
7. Discussion: mechanism, negative findings, confounding and applicability limits.
8. Conclusions: supported findings only; distinguish future acquisition needs.

Release exact split manifests, seeds, parameters, dependency versions, feature
definitions and out-of-fold operating-point predictions. Clearly separate
exploratory findings from any subsequent preregistered or untouched-test evaluation.