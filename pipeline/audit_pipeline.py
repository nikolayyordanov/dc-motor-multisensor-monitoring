#!/usr/bin/env python3
"""Audit modality comparison for leakage, signal quality, and split sensitivity."""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold


MODALITIES = ["sound_phone", "sound_vibrometer", "current"]
AUDIT_TREES = 10
NON_FEATURES = {
    "group_id", "condition", "operation", "reversal", "speed_percent",
    "modality", "path", "segment_id", "segment_index", "segment_start_s",
    "segment_end_s",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, default=Path("pipeline_outputs"))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def duplicate_summary(manifest: pd.DataFrame) -> list[dict]:
    rows = []
    for modality in MODALITIES:
        path_col = f"path_{modality}"
        hashes: dict[str, list[str]] = defaultdict(list)
        for raw_path in manifest[path_col]:
            path = Path(raw_path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes[digest].append(str(path))
        rows.append({
            "modality": modality,
            "files": len(manifest),
            "unique_sha256": len(hashes),
            "duplicate_groups": sum(len(paths) > 1 for paths in hashes.values()),
        })
    return rows


def vibrometer_quality(manifest: pd.DataFrame) -> dict[str, float]:
    correlations = []
    clipping = []
    mix_retention = []
    for raw_path in manifest["path_sound_vibrometer"]:
        signal, fs = sf.read(raw_path, always_2d=True, dtype="float32")
        signal = signal[int(fs):int(5 * fs)]
        channel_rms = np.sqrt(np.mean(signal * signal, axis=0))
        mix = signal.mean(axis=1)
        correlations.append(float(np.corrcoef(signal.T)[0, 1]))
        clipping.append(float(np.mean(np.abs(signal) >= 0.999)))
        mix_retention.append(
            float(np.sqrt(np.mean(mix * mix)) / np.max(channel_rms))
        )
    return {
        "median_channel_correlation": float(np.median(correlations)),
        "minimum_channel_correlation": float(np.min(correlations)),
        "median_mix_rms_retention": float(np.median(mix_retention)),
        "maximum_clipped_fraction": float(np.max(clipping)),
        "median_clipped_fraction": float(np.median(clipping)),
    }


def evaluate_target(
    data: pd.DataFrame,
    features: pd.DataFrame,
    target: pd.Series,
    seed: int,
) -> tuple[float, float, float]:
    group_labels = pd.DataFrame({
        "group_id": data["group_id"],
        "target": target,
    }).drop_duplicates("group_id")
    min_class_count = int(group_labels["target"].value_counts().min())
    n_splits = min(5, min_class_count)
    cv = StratifiedGroupKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=seed,
    )

    def fit_predict(train: np.ndarray, test: np.ndarray) -> tuple[list, list]:
        model = RandomForestClassifier(
            n_estimators=AUDIT_TREES,
            random_state=seed,
            class_weight="balanced",
            n_jobs=1,
        )
        train_counts = data.loc[train, "group_id"].value_counts()
        weights = (
            1.0 / data.loc[train, "group_id"].map(train_counts)
        ).to_numpy(copy=True)
        weights *= weights.size / weights.sum()
        model.fit(features.loc[train], target.loc[train], sample_weight=weights)

        probabilities = model.predict_proba(features.loc[test])
        probability_cols = [f"p_{label}" for label in model.classes_]
        frame = pd.DataFrame({
            "group_id": data.loc[test, "group_id"].to_numpy(),
            "target": target.loc[test].to_numpy(),
        })
        frame[probability_cols] = probabilities
        true_values = []
        predicted_values = []
        for _, group in frame.groupby("group_id", sort=False):
            true_values.append(group["target"].iloc[0])
            mean_probability = group[probability_cols].mean().to_numpy()
            predicted_values.append(model.classes_[int(np.argmax(mean_probability))])
        return true_values, predicted_values

    scores = []
    groups = data["group_id"].to_numpy()
    for train_idx, test_idx in cv.split(features, target, groups=groups):
        train = np.zeros(len(data), dtype=bool)
        test = np.zeros(len(data), dtype=bool)
        train[train_idx] = True
        test[test_idx] = True
        true_values, predicted_values = fit_predict(train, test)
        scores.append(f1_score(true_values, predicted_values, average="macro"))

    load_true = []
    load_predictions = []
    for load in sorted(data["speed_percent"].unique()):
        test = data["speed_percent"].eq(load).to_numpy()
        train = ~test
        true_values, predicted_values = fit_predict(train, test)
        load_true.extend(true_values)
        load_predictions.extend(predicted_values)

    return (
        float(np.mean(scores)),
        float(np.std(scores)),
        float(f1_score(load_true, load_predictions, average="macro")),
    )


def evaluate_cached_features(outputs: Path, seed: int) -> tuple[list[dict], list[dict]]:
    metric_rows = []
    importance_rows = []
    for modality in MODALITIES:
        data = pd.read_csv(outputs / f"features_{modality}.csv")
        feature_cols = [col for col in data.columns if col not in NON_FEATURES]
        features = data[feature_cols].fillna(0.0)
        tasks = {
            "condition_8class": (data, features, data["condition"]),
            "operation_4class": (data, features, data["operation"]),
            "reversal_binary": (data, features, data["reversal"]),
        }
        mechanical_mask = data["operation"].isin(["normal", "loose_foundation"])
        mechanical_data = data.loc[mechanical_mask].reset_index(drop=True)
        mechanical_features = features.loc[mechanical_mask].reset_index(drop=True)
        mechanical_target = mechanical_data["operation"].map({
            "normal": "normal",
            "loose_foundation": "loose_foundation",
        })
        tasks["loose_vs_normal_binary"] = (
            mechanical_data,
            mechanical_features,
            mechanical_target,
        )

        for task, (task_data, task_features, target) in tasks.items():
            cv_mean, cv_std, load_f1 = evaluate_target(
                task_data, task_features, target, seed
            )
            metric_rows.append({
                "modality": modality,
                "task": task,
                "stratified_5fold_macro_f1_mean": cv_mean,
                "stratified_5fold_macro_f1_std": cv_std,
                "leave_one_load_out_macro_f1": load_f1,
            })

        estimator = RandomForestClassifier(
            n_estimators=AUDIT_TREES,
            random_state=seed,
            class_weight="balanced",
            n_jobs=1,
        )
        target = data["condition"]
        estimator.fit(features, target)
        importance = pd.Series(
            estimator.feature_importances_, index=feature_cols
        ).sort_values(ascending=False)
        for feature, value in importance.head(8).items():
            importance_rows.append({
                "modality": modality,
                "feature": feature,
                "importance": float(value),
            })

    return metric_rows, importance_rows


def main() -> None:
    args = parse_args()
    manifest = pd.read_csv(args.outputs / "paired_manifest.csv")

    duplicates_path = args.outputs / "audit_duplicates.csv"
    quality_path = args.outputs / "audit_vibrometer_quality.csv"
    duplicates = (
        pd.read_csv(duplicates_path)
        if duplicates_path.exists()
        else pd.DataFrame(duplicate_summary(manifest))
    )
    quality = (
        pd.read_csv(quality_path)
        if quality_path.exists()
        else pd.DataFrame([vibrometer_quality(manifest)])
    )
    metrics, importance = evaluate_cached_features(args.outputs, args.seed)
    metrics_df = pd.DataFrame(metrics)
    importance_df = pd.DataFrame(importance)

    duplicates.to_csv(duplicates_path, index=False)
    quality.to_csv(quality_path, index=False)
    metrics_df.to_csv(args.outputs / "audit_validation_sensitivity.csv", index=False)
    importance_df.to_csv(args.outputs / "audit_feature_importance.csv", index=False)

    print("\nDuplicate-file audit")
    print(duplicates.to_string(index=False))
    print("\nVibrometer WAV audit")
    print(quality.to_string(index=False))
    print("\nValidation sensitivity")
    print(metrics_df.to_string(index=False))
    print("\nTop feature importance")
    print(importance_df.groupby("modality").head(5).to_string(index=False))


if __name__ == "__main__":
    main()