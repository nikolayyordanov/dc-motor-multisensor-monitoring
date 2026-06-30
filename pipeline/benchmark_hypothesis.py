#!/usr/bin/env python3
"""Benchmark phone-vs-instrument hypothesis with leakage-safe grouped CV.

Outputs:
- paired_manifest.csv
- features_<modality>.csv
- fold_metrics.csv
- hypothesis_report.md
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import av
import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import resample_poly, welch
from scipy.stats import kurtosis, skew, wilcoxon
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GroupKFold

MODALITIES = ["sound_phone", "sound_vibrometer", "current"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("DCData_mendeley"))
    parser.add_argument("--out-dir", type=Path, default=Path("pipeline_outputs"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--offset-seconds", type=float, default=1.0)
    parser.add_argument("--max-seconds", type=float, default=8.0)
    parser.add_argument("--target-fs-current", type=float, default=20000.0)
    parser.add_argument("--target-fs-audio", type=float, default=16000.0)
    parser.add_argument("--bootstrap-iter", type=int, default=5000)
    parser.add_argument("--f1-margin", type=float, default=0.05)
    parser.add_argument("--mae-margin", type=float, default=5.0)
    return parser.parse_args()


def build_paired_manifest(dataset_root: Path) -> pd.DataFrame:
    meta = pd.read_csv(dataset_root / "metadata.csv")
    meta = meta[meta["sensor"].isin(MODALITIES)].copy()

    pivot = (
        meta.pivot_table(
            index=["condition", "operation", "reversal", "load_percent"],
            columns="sensor",
            values="new_path",
            aggfunc="first",
        )
        .reset_index()
        .dropna(subset=MODALITIES)
    )

    pivot["group_id"] = (
        pivot["condition"].astype(str) + "__" + pivot["load_percent"].astype(int).astype(str)
    )

    for sensor in MODALITIES:
        pivot[f"path_{sensor}"] = pivot[sensor].apply(lambda p: str((dataset_root / p).resolve()))

    keep_cols = [
        "group_id",
        "condition",
        "operation",
        "reversal",
        "load_percent",
        "path_sound_phone",
        "path_sound_vibrometer",
        "path_current",
    ]
    return pivot[keep_cols].sort_values(["condition", "load_percent"]).reset_index(drop=True)


def _safe_float(x: float) -> float:
    if np.isfinite(x):
        return float(x)
    return 0.0


def extract_signal_features(sig: np.ndarray, fs: float) -> dict[str, float]:
    if sig.ndim > 1:
        sig = sig.mean(axis=1)
    sig = np.asarray(sig, dtype=np.float64)
    if sig.size < 32:
        return {"feat_valid": 0.0}

    sig = sig - np.mean(sig)
    rms = np.sqrt(np.mean(sig * sig))
    peak = np.max(np.abs(sig))
    zcr = np.mean((sig[:-1] * sig[1:]) < 0)
    crest = peak / (rms + 1e-12)

    nperseg = min(4096, sig.size)
    freqs, pxx = welch(sig, fs=fs, nperseg=nperseg, scaling="density")
    pxx = np.maximum(pxx, 1e-18)
    pxx_sum = np.sum(pxx)

    dom_freq = freqs[int(np.argmax(pxx))]
    centroid = np.sum(freqs * pxx) / pxx_sum
    bandwidth = np.sqrt(np.sum(((freqs - centroid) ** 2) * pxx) / pxx_sum)
    cdf = np.cumsum(pxx) / pxx_sum
    rolloff_idx = int(np.searchsorted(cdf, 0.85))
    rolloff85 = freqs[min(rolloff_idx, len(freqs) - 1)]

    bands = [(0, 50), (50, 150), (150, 400), (400, 1000), (1000, 3000), (3000, 8000)]
    band_powers: dict[str, float] = {}
    for lo, hi in bands:
        mask = (freqs >= lo) & (freqs < hi)
        bpow = np.sum(pxx[mask]) / pxx_sum
        band_powers[f"band_{lo}_{hi}"] = float(bpow)

    out = {
        "feat_valid": 1.0,
        "mean": _safe_float(np.mean(sig)),
        "std": _safe_float(np.std(sig)),
        "rms": _safe_float(rms),
        "peak": _safe_float(peak),
        "crest": _safe_float(crest),
        "zcr": _safe_float(zcr),
        "skew": _safe_float(skew(sig)),
        "kurtosis": _safe_float(kurtosis(sig, fisher=False)),
        "dom_freq": _safe_float(dom_freq),
        "spec_centroid": _safe_float(centroid),
        "spec_bandwidth": _safe_float(bandwidth),
        "spec_rolloff85": _safe_float(rolloff85),
    }
    out.update(band_powers)
    return out


def load_audio_segment(path: Path, offset_s: float, max_s: float, target_fs: float) -> tuple[np.ndarray, float]:
    suffix = path.suffix.lower()

    if suffix == ".wav":
        with sf.SoundFile(str(path)) as f:
            fs = float(f.samplerate)
            start = int(max(0.0, offset_s) * fs)
            n_frames = int(max_s * fs)
            f.seek(start)
            sig = f.read(frames=n_frames, dtype="float32", always_2d=False)
        if sig.ndim > 1:
            sig = sig.mean(axis=1)
    else:
        # Decode compressed formats (e.g. M4A) via PyAV/FFmpeg libraries,
        # avoiding dependence on a system ffmpeg executable.
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            resampler = av.audio.resampler.AudioResampler(
                format="fltp",
                layout="mono",
                rate=int(target_fs),
            )
            chunks = []
            for frame in container.decode(stream):
                converted = resampler.resample(frame)
                if converted is None:
                    continue
                if not isinstance(converted, list):
                    converted = [converted]
                for out_frame in converted:
                    arr = out_frame.to_ndarray()
                    chunks.append(arr.reshape(-1).astype(np.float32, copy=False))

            flushed = resampler.resample(None)
            if flushed is not None:
                if not isinstance(flushed, list):
                    flushed = [flushed]
                for out_frame in flushed:
                    arr = out_frame.to_ndarray()
                    chunks.append(arr.reshape(-1).astype(np.float32, copy=False))

        sig = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        fs = float(target_fs)

        start = int(max(0.0, offset_s) * fs)
        stop = start + int(max_s * fs)
        sig = sig[start:stop]

    if sig.size == 0:
        return np.zeros(0, dtype=np.float32), float(target_fs)
    if fs != target_fs:
        up = int(target_fs)
        down = int(fs)
        sig = resample_poly(sig, up, down).astype(np.float32)
        fs = float(target_fs)
    return sig, float(fs)


def _load_rigol_rg01_segment(
    path: Path,
    offset_s: float,
    max_s: float,
    target_fs: float,
) -> tuple[np.ndarray, float]:
    with path.open("rb") as fh:
        data = fh.read(300)

    if data[0:2] not in (b"RG", b"AG"):
        raise ValueError("Not RG/AG binary")

    off = 12
    wh_size = struct.unpack_from("<i", data, off)[0]
    with path.open("rb") as fh:
        fh.seek(off)
        wh = fh.read(wh_size)
    x_inc = struct.unpack_from("<d", wh, 32)[0]
    fs = 1.0 / x_inc if x_inc > 0 else 1_000_000.0

    off += wh_size
    with path.open("rb") as fh:
        fh.seek(off)
        bh = fh.read(12)
    bh_size = struct.unpack_from("<i", bh, 0)[0]
    _buf_type, bpp = struct.unpack_from("<hh", bh, 4)
    buf_size = struct.unpack_from("<i", bh, 8)[0]

    payload_offset = off + bh_size
    n_samples = int(buf_size // bpp)

    start = int(max(0.0, offset_s) * fs)
    stop = int(min(n_samples, start + max_s * fs))
    if stop <= start:
        return np.zeros(0, dtype=np.float32), target_fs

    dtype = {1: np.uint8, 2: np.int16, 4: np.float32, 8: np.float64}.get(bpp)
    if dtype is None:
        raise ValueError(f"Unsupported bytes-per-point in RG file: {bpp}")

    itemsize = np.dtype(dtype).itemsize
    read_offset = payload_offset + start * itemsize
    read_count = stop - start
    with path.open("rb") as fh:
        fh.seek(read_offset)
        raw = fh.read(read_count * itemsize)
    sig = np.frombuffer(raw, dtype=dtype).astype(np.float64, copy=False)

    if dtype == np.uint8:
        sig = sig - np.mean(sig)

    if fs > target_fs:
        step = max(1, int(round(fs / target_fs)))
        sig = sig[::step]
        fs = fs / step

    return sig.astype(np.float32), float(fs)


def load_current_segment(path: Path, offset_s: float, max_s: float, target_fs: float) -> tuple[np.ndarray, float]:
    with path.open("rb") as fh:
        magic = fh.read(2)
    if magic in (b"RG", b"AG"):
        return _load_rigol_rg01_segment(path, offset_s, max_s, target_fs)

    # Fallback: treat as WFM-like 8-bit payload after a fixed header.
    header_bytes = 4200
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=header_bytes)
    if raw.size == 0:
        return np.zeros(0, dtype=np.float32), target_fs

    fs = target_fs
    start = int(max(0.0, offset_s) * fs)
    stop = int(min(raw.size, start + max_s * fs))
    sig = np.asarray(raw[start:stop], dtype=np.float32)
    sig = sig - np.mean(sig)
    return sig, fs


def extract_features_for_modality(
    manifest: pd.DataFrame,
    modality: str,
    offset_s: float,
    max_s: float,
    target_fs_audio: float,
    target_fs_current: float,
) -> pd.DataFrame:
    rows = []
    path_col = f"path_{modality}"
    for idx, rec in manifest.iterrows():
        p = Path(rec[path_col])
        if modality in ("sound_phone", "sound_vibrometer"):
            sig, fs = load_audio_segment(
                p, offset_s=offset_s, max_s=max_s, target_fs=target_fs_audio
            )
        else:
            sig, fs = load_current_segment(
                p, offset_s=offset_s, max_s=max_s, target_fs=target_fs_current
            )

        feats = extract_signal_features(sig, fs)
        out = {
            "group_id": rec["group_id"],
            "condition": rec["condition"],
            "operation": rec["operation"],
            "reversal": rec["reversal"],
            "load_percent": rec["load_percent"],
            "modality": modality,
            "path": str(p),
        }
        out.update(feats)
        rows.append(out)

        if (idx + 1) % 20 == 0:
            print(f"[{modality}] processed {idx + 1}/{len(manifest)}")

    return pd.DataFrame(rows)


def get_group_folds(manifest: pd.DataFrame, n_splits: int) -> list[tuple[np.ndarray, np.ndarray]]:
    gkf = GroupKFold(n_splits=n_splits)
    y = manifest["condition"].to_numpy()
    groups = manifest["group_id"].to_numpy()
    idx = np.arange(len(manifest))
    return list(gkf.split(idx, y=y, groups=groups))


def evaluate_modality(
    feat_df: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray]],
    seed: int,
) -> pd.DataFrame:
    use_cols = [
        c
        for c in feat_df.columns
        if c
        not in {
            "group_id",
            "condition",
            "operation",
            "reversal",
            "load_percent",
            "modality",
            "path",
        }
    ]

    X = feat_df[use_cols].fillna(0.0).to_numpy()
    y_cls = feat_df["condition"].to_numpy()
    y_reg = feat_df["load_percent"].to_numpy()

    rows = []
    for fold_id, (tr, te) in enumerate(folds, start=1):
        clf = RandomForestClassifier(
            n_estimators=500,
            random_state=seed + fold_id,
            class_weight="balanced",
        )
        reg = RandomForestRegressor(
            n_estimators=500,
            random_state=seed + fold_id,
        )

        clf.fit(X[tr], y_cls[tr])
        reg.fit(X[tr], y_reg[tr])

        pred_cls = clf.predict(X[te])
        pred_reg = reg.predict(X[te])

        rows.append(
            {
                "modality": feat_df["modality"].iloc[0],
                "fold": fold_id,
                "macro_f1": f1_score(y_cls[te], pred_cls, average="macro"),
                "balanced_acc": balanced_accuracy_score(y_cls[te], pred_cls),
                "mae": mean_absolute_error(y_reg[te], pred_reg),
                "rmse": np.sqrt(mean_squared_error(y_reg[te], pred_reg)),
                "r2": r2_score(y_reg[te], pred_reg),
            }
        )

    return pd.DataFrame(rows)


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator, n_iter: int = 5000) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return 0.0, 0.0, 0.0
    means = np.empty(n_iter, dtype=np.float64)
    n = values.size
    for i in range(n_iter):
        sample = values[rng.integers(0, n, size=n)]
        means[i] = np.mean(sample)
    lo = float(np.percentile(means, 2.5))
    hi = float(np.percentile(means, 97.5))
    return float(np.mean(values)), lo, hi


def compare_phone_vs_reference(
    fold_metrics: pd.DataFrame,
    reference: str,
    rng: np.random.Generator,
    n_bootstrap: int,
    f1_margin: float,
    mae_margin: float,
) -> dict:
    phone = fold_metrics[fold_metrics["modality"] == "sound_phone"].sort_values("fold")
    ref = fold_metrics[fold_metrics["modality"] == reference].sort_values("fold")

    delta_f1 = phone["macro_f1"].to_numpy() - ref["macro_f1"].to_numpy()
    delta_mae = phone["mae"].to_numpy() - ref["mae"].to_numpy()

    mean_f1, lo_f1, hi_f1 = bootstrap_ci(delta_f1, rng, n_iter=n_bootstrap)
    mean_mae, lo_mae, hi_mae = bootstrap_ci(delta_mae, rng, n_iter=n_bootstrap)

    try:
        w_f1 = wilcoxon(delta_f1, zero_method="wilcox", correction=False)
        p_f1 = float(w_f1.pvalue)
    except ValueError:
        p_f1 = 1.0

    try:
        w_mae = wilcoxon(delta_mae, zero_method="wilcox", correction=False)
        p_mae = float(w_mae.pvalue)
    except ValueError:
        p_mae = 1.0

    verdict_f1 = lo_f1 > -f1_margin
    verdict_mae = hi_mae < mae_margin

    return {
        "reference": reference,
        "delta_f1_mean": mean_f1,
        "delta_f1_ci_low": lo_f1,
        "delta_f1_ci_high": hi_f1,
        "delta_f1_wilcoxon_p": p_f1,
        "delta_mae_mean": mean_mae,
        "delta_mae_ci_low": lo_mae,
        "delta_mae_ci_high": hi_mae,
        "delta_mae_wilcoxon_p": p_mae,
        "noninferior_f1": verdict_f1,
        "noninferior_mae": verdict_mae,
        "noninferior_overall": bool(verdict_f1 and verdict_mae),
    }


def build_report(
    out_dir: Path,
    manifest: pd.DataFrame,
    fold_metrics: pd.DataFrame,
    comparisons: list[dict],
    args: argparse.Namespace,
) -> str:
    summary = (
        fold_metrics.groupby("modality")
        .agg(
            macro_f1_mean=("macro_f1", "mean"),
            macro_f1_std=("macro_f1", "std"),
            balanced_acc_mean=("balanced_acc", "mean"),
            mae_mean=("mae", "mean"),
            mae_std=("mae", "std"),
            rmse_mean=("rmse", "mean"),
            r2_mean=("r2", "mean"),
        )
        .reset_index()
    )

    lines = []
    lines.append("# Hypothesis Benchmark Report")
    lines.append("")
    lines.append("## Data and Protocol")
    lines.append("")
    lines.append(f"- Paired groups used: {len(manifest)}")
    lines.append(f"- Grouped folds: {args.n_splits}")
    lines.append(f"- Segment offset (s): {args.offset_seconds}")
    lines.append(f"- Segment duration (s): {args.max_seconds}")
    lines.append(f"- Random seed: {args.seed}")
    lines.append("")
    lines.append("## Cross-Validation Metrics (mean over folds)")
    lines.append("")
    lines.append("| Modality | Macro F1 | Balanced Acc | MAE | RMSE | R2 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['modality']} | {r['macro_f1_mean']:.4f} | {r['balanced_acc_mean']:.4f} | "
            f"{r['mae_mean']:.4f} | {r['rmse_mean']:.4f} | {r['r2_mean']:.4f} |"
        )

    lines.append("")
    lines.append("## Phone Non-Inferiority Checks")
    lines.append("")
    lines.append("Margins:")
    lines.append(f"- Macro F1 delta margin: -{args.f1_margin}")
    lines.append(f"- MAE delta margin: +{args.mae_margin} load-percent points")
    lines.append("")
    lines.append("| Comparison | Delta F1 mean | Delta F1 95% CI | Delta MAE mean | Delta MAE 95% CI | Overall non-inferior |")
    lines.append("|---|---:|---|---:|---|---|")
    for c in comparisons:
        lines.append(
            f"| phone - {c['reference']} | {c['delta_f1_mean']:.4f} | "
            f"[{c['delta_f1_ci_low']:.4f}, {c['delta_f1_ci_high']:.4f}] | "
            f"{c['delta_mae_mean']:.4f} | "
            f"[{c['delta_mae_ci_low']:.4f}, {c['delta_mae_ci_high']:.4f}] | "
            f"{str(c['noninferior_overall'])} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This is a baseline tabular-feature benchmark using one fixed model family across modalities.")
    lines.append("- Use this as a reproducible reference point before moving to larger deep models.")

    report = "\n".join(lines)
    (out_dir / "hypothesis_report.md").write_text(report, encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)

    print("Building paired manifest...")
    manifest = build_paired_manifest(args.dataset_root)
    manifest.to_csv(out_dir / "paired_manifest.csv", index=False)
    print(f"Paired groups: {len(manifest)}")

    fold_indices = get_group_folds(manifest, n_splits=args.n_splits)

    feature_tables = {}
    all_fold_metrics = []
    for modality in MODALITIES:
        print(f"Extracting features for: {modality}")
        feat_df = extract_features_for_modality(
            manifest,
            modality,
            offset_s=args.offset_seconds,
            max_s=args.max_seconds,
            target_fs_audio=args.target_fs_audio,
            target_fs_current=args.target_fs_current,
        )
        feature_tables[modality] = feat_df
        feat_df.to_csv(out_dir / f"features_{modality}.csv", index=False)

        print(f"Evaluating modality: {modality}")
        fold_df = evaluate_modality(feat_df, fold_indices, seed=args.seed)
        all_fold_metrics.append(fold_df)

    fold_metrics = pd.concat(all_fold_metrics, ignore_index=True)
    fold_metrics.to_csv(out_dir / "fold_metrics.csv", index=False)

    comparisons = [
        compare_phone_vs_reference(
            fold_metrics,
            reference="sound_vibrometer",
            rng=rng,
            n_bootstrap=args.bootstrap_iter,
            f1_margin=args.f1_margin,
            mae_margin=args.mae_margin,
        ),
        compare_phone_vs_reference(
            fold_metrics,
            reference="current",
            rng=rng,
            n_bootstrap=args.bootstrap_iter,
            f1_margin=args.f1_margin,
            mae_margin=args.mae_margin,
        ),
    ]

    with (out_dir / "comparisons.json").open("w", encoding="utf-8") as fh:
        json.dump(comparisons, fh, indent=2)

    report = build_report(out_dir, manifest, fold_metrics, comparisons, args)
    print("\nBenchmark complete.")
    print(f"Report: {out_dir / 'hypothesis_report.md'}")
    print("\n--- Report Preview ---\n")
    print(report)


if __name__ == "__main__":
    main()
