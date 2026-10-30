"""Standalone Lab08 WAV experiment. No Word or project-specific modules needed.

Usage: python lab08_ml.py /path/to/DCData_mendeley --output results_lab08
Python >=3.11. See README_lab08_ml_bg.md for methods and limitations.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import periodogram
from scipy.stats import kurtosis
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, ConfusionMatrixDisplay, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

CONDITIONS = ["normal_no_reversal", "loose_foundation_no_reversal",
              "suboptimal_control_no_reversal", "suboptimal_control_rt_no_reversal"]
LABELS = ["Номинално", "Разхлабен\nфундамент", "Неоптимален\nРС", "Неоптимален\nРТ"]
BANDS = [(0, 100), (100, 250), (250, 500), (500, 1000),
         (1000, 2000), (2000, 5000), (5000, 10000)]
FEATURES = ["RMS", "PTP", "CF", "Kurtosis"] + [f"band_{lo}_{hi}" for lo, hi in BANDS]
SUBSETS = [("Времева област", list(range(4))), ("Честотна област", list(range(4, 11))),
           ("Времева и честотна област", list(range(11)))]
COMBINED = SUBSETS[-1][0]
MODELS = ("kNN", "SVM", "Random Forest")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def select_records(dataset):
    meta = pd.read_csv(dataset / "metadata.csv")
    required = {"sensor", "condition", "speed_percent", "new_path"}
    if not required.issubset(meta.columns):
        raise ValueError(f"Missing metadata columns: {sorted(required - set(meta.columns))}")
    meta = meta[(meta.sensor == "sound_vibrometer") & meta.condition.isin(CONDITIONS)].copy()
    if set(meta.condition) != set(CONDITIONS):
        raise ValueError("All four no-reversal conditions are required")
    speeds = pd.to_numeric(meta.speed_percent, errors="raise")
    if not np.isfinite(speeds).all() or not (speeds == speeds.astype(int)).all() or not speeds.between(1, 100).all():
        raise ValueError("Speed setpoints must be integers from 1 to 100")
    meta["speed_percent"] = speeds.astype(int)
    common = sorted(set.intersection(*(set(meta[meta.condition == c].speed_percent) for c in CONDITIONS)))
    if not common:
        raise ValueError("No common speed setpoints across all four conditions")
    meta = meta[meta.speed_percent.isin(common)].sort_values(["condition", "speed_percent"])
    if meta.duplicated(["condition", "speed_percent"]).any() or meta.new_path.duplicated().any():
        raise ValueError("Duplicate recording or condition/setpoint in metadata")
    if len(common) < 5:
        raise ValueError("At least five common setpoints per class are needed for five folds")
    for relative in meta.new_path:
        if not isinstance(relative, str):
            raise ValueError("Invalid recording path")
        path = (dataset / relative).resolve()
        if not path.is_relative_to(dataset) or path.suffix.lower() != ".wav" or not path.is_file():
            raise ValueError(f"Missing, external or non-WAV recording: {relative}")
    return meta, common


def window_features(y, fs):
    y = np.asarray(y, dtype=np.float64).copy()
    if not np.isfinite(y).all():
        raise ValueError("Non-finite WAV samples")
    y -= y.mean()
    rms = float(np.sqrt(np.mean(y * y)))
    if rms <= 0:
        raise ValueError("Zero-energy window; no features can be inferred")
    freq, power = periodogram(y, fs, window="hann", detrend=False, scaling="density")
    total = power.sum()
    values = [rms, float(np.ptp(y)), float(np.max(np.abs(y)) / rms),
              float(kurtosis(y, fisher=False, bias=True))]
    values += [float(power[(freq >= lo) & (freq < hi)].sum() / total) for lo, hi in BANDS]
    if not np.isfinite(values).all():
        raise ValueError("Invalid extracted features")
    return values


def extract(dataset, meta):
    rows, sources = [], []
    for row in meta.itertuples():
        path = (dataset / row.new_path).resolve()
        before = sha(path)
        samples, fs = sf.read(path, dtype="float64", always_2d=True)
        if fs != 44100 or samples.shape[1] < 1:
            raise ValueError(f"Expected 44100-Hz WAV with at least one channel: {row.new_path}")
        signal = samples[fs:, 0]
        n = 22050
        count = len(signal) // n
        if count < 1:
            raise ValueError(f"No complete 0.5-s window after first second: {row.new_path}")
        for i in range(count):
            values = window_features(signal[i*n:(i+1)*n], fs)
            rows.append({"record": row.new_path, "speed": int(row.speed_percent),
                         "class": CONDITIONS.index(row.condition), "window": i,
                         **dict(zip(FEATURES, values))})
        if sha(path) != before:
            raise ValueError(f"Source changed during reading: {row.new_path}")
        sources.append({"path": row.new_path, "sha256": before, "sample_rate_hz": fs,
                        "channels": samples.shape[1], "samples": len(samples),
                        "windows": count, "discarded_tail_samples": len(signal) % n})
        print(f"Read {len(sources)}/{len(meta)} recordings; {count} windows", flush=True)
    return pd.DataFrame(rows), sources


def majority(values):
    """Deterministic majority; tied counts choose the lowest class index."""
    return int(np.bincount(values, minlength=4).argmax())


def evaluate(frame):
    X, y = frame[FEATURES].to_numpy(), frame["class"].to_numpy()
    folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=42).split(X, y, frame.record))
    models = {"kNN": make_pipeline(StandardScaler(), KNeighborsClassifier(5)),
              "SVM": make_pipeline(StandardScaler(), SVC(C=1, gamma="scale", kernel="rbf")),
              "Random Forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=2,
                                                       class_weight="balanced", random_state=42, n_jobs=1)}
    fold_ids = np.full(len(frame), -1, dtype=int)
    for fold, (train, test) in enumerate(folds):
        if set(frame.record.iloc[train]) & set(frame.record.iloc[test]):
            raise ValueError("Train/test recording leakage")
        if set(y[train]) != set(range(4)) or len(train) < 5:
            raise ValueError("Training fold lacks a class or enough kNN samples")
        fold_ids[test] = fold
    if (fold_ids < 0).any():
        raise ValueError("Incomplete out-of-fold coverage")
    frame["fold"] = fold_ids
    metrics, records, matrices = [], [], {}
    for subset, indices in SUBSETS:
        for name, prototype in models.items():
            pred = np.full(len(y), -1, dtype=int)
            for train, test in folds:
                fitted = clone(prototype).fit(X[train][:, indices], y[train])
                pred[test] = fitted.predict(X[test][:, indices])
            grouped = pd.DataFrame({"record": frame.record, "true": y, "pred": pred}).groupby("record")
            truth = grouped["true"].first().to_numpy()
            voted = grouped["pred"].agg(majority).to_numpy()
            metrics.append({"features": subset, "model": name,
                            "accuracy_record": accuracy_score(truth, voted),
                            "macro_f1_record": f1_score(truth, voted, labels=range(4), average="macro", zero_division=0),
                            "accuracy_window": accuracy_score(y, pred),
                            "macro_f1_window": f1_score(y, pred, labels=range(4), average="macro", zero_division=0)})
            for record, actual, prediction in zip(grouped.size().index, truth, voted):
                records.append({"features": subset, "model": name, "record": record,
                                "true": int(actual), "predicted": int(prediction)})
            if subset == COMBINED:
                frame[f"prediction_{name}"] = pred
                matrices[name] = confusion_matrix(truth, voted, labels=range(4))
            print(f"Evaluated {subset}: {name}", flush=True)
    return pd.DataFrame(metrics), pd.DataFrame(records), matrices, models


def save_figures(frame, matrices, output):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    means = frame.groupby(["record", "class"])[["RMS", "Kurtosis"]].mean().reset_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    for c, label in enumerate(LABELS):
        points = means[means["class"] == c]
        ax.scatter(points.RMS, points.Kurtosis, label=label.replace("\n", " "), s=40)
    ax.set(xlabel="Среден RMS на прозорците (цифров пълен обхват)", ylabel="Среден куртозис (Pearson)")
    ax.grid(alpha=.25)
    ax.legend()
    export(fig, output, "fig8_3_features")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, name in zip(axes, MODELS):
        ConfusionMatrixDisplay(matrices[name], display_labels=LABELS).plot(ax=ax, colorbar=False, cmap="Blues")
        ax.set_title(name)
        ax.set_xlabel("Предсказан клас")
        ax.set_ylabel("Действителен клас")
        ax.tick_params(axis="both", labelsize=7)
    export(fig, output, "fig8_4_confusion")


def export(fig, output, stem):
    fig.tight_layout()
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output / f"{stem}.{extension}", dpi=600, bbox_inches="tight")
    plt.close(fig)


def save_tables(metrics, output):
    combined = metrics[metrics.features == COMBINED].set_index("model").loc[list(MODELS)]
    table2 = pd.DataFrame({"Метод за класификация": MODELS,
                           "Accuracy, %": 100 * combined.accuracy_record.to_numpy(),
                           "Macro-F1": combined.macro_f1_record.to_numpy()})
    table3 = metrics.pivot(index="features", columns="model", values="macro_f1_record").loc[
        [name for name, _ in SUBSETS], list(MODELS)]
    table3.index.name = "Използвани признаци"
    table2.to_csv(output / "table8_2_classification.csv", index=False, encoding="utf-8-sig")
    table3.to_csv(output / "table8_3_feature_comparison.csv", encoding="utf-8-sig")
    lines = ["# Резултати за упражнение 08", "", "Показателите са на ниво цял запис (извънобучаващи предсказвания).",
             "Таблица 8.2: комбинирани признаци. Таблица 8.3: Macro-F1.", "",
             "## Таблица 8.2", "", "| Метод | Accuracy, % | Macro-F1 |", "|---|---:|---:|"]
    for row in table2.itertuples(index=False, name=None):
        lines.append(f"| {row[0]} | {row[1]:.1f} | {row[2]:.3f} |")
    lines += ["", "## Таблица 8.3", "", "| Признаци | kNN | SVM | Random Forest |", "|---|---:|---:|---:|"]
    for name, row in table3.iterrows():
        lines.append(f"| {name} | " + " | ".join(f"{v:.3f}" for v in row) + " |")
    (output / "tables_lab08.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Dataset root containing metadata.csv and data/")
    parser.add_argument("--output", type=Path, default=Path("results_lab08"))
    parser.add_argument("--overwrite", action="store_true", help="Replace generated results in a nonempty output folder")
    args = parser.parse_args(argv)
    dataset, output = args.dataset.resolve(), args.output.resolve()
    try:
        if output.is_relative_to(dataset) or dataset.is_relative_to(output):
            raise ValueError("Output must be separate from the dataset, not inside it or its parent")
        if output.exists() and (not output.is_dir() or (any(output.iterdir()) and not args.overwrite)):
            raise ValueError("Output exists and is not empty; choose another folder or use --overwrite")
        meta, speeds = select_records(dataset)
        frame, sources = extract(dataset, meta)
        metrics, records, matrices, models = evaluate(frame)
        if any(sha(dataset / source["path"]) != source["sha256"] for source in sources):
            raise ValueError("A source recording changed during the experiment")
        output.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output / "features_predictions.csv", index=False, encoding="utf-8-sig")
        records.to_csv(output / "record_predictions.csv", index=False, encoding="utf-8-sig")
        metrics.to_csv(output / "classification_metrics.csv", index=False, encoding="utf-8-sig")
        save_tables(metrics, output)
        save_figures(frame, matrices, output)
        provenance = {"recordings": len(meta), "windows": len(frame), "speeds": speeds,
                      "classes": dict(enumerate(CONDITIONS)), "features": FEATURES, "bands_hz": BANDS,
                      "channel": 1, "skip_s": 1, "window_s": .5, "overlap": 0,
                      "spectral_method": "periodic Hann periodogram; half-open bands / total power through Nyquist",
                      "kurtosis": "Pearson, bias=True", "amplitude": "digital full scale, not physical calibrated units",
                      "validation": "5-fold StratifiedGroupKFold; source-record groups; shuffle=True, seed=42; no tuning",
                      "primary_metrics": "pooled recording-level OOF majority vote; tied counts choose lowest class index",
                      "models": {name: str(model) for name, model in models.items()}, "rf_n_jobs": 1,
                      "versions": {name: version(name) for name in ("numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "soundfile")},
                      "python": platform.python_version(), "script_sha256": sha(Path(__file__)), "sources": sources}
        (output / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Finished: {len(meta)} recordings, {len(frame)} windows. Results: {output}")
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()