#!/usr/bin/env python3
"""Generate publication-ready tables and figures from pipeline outputs.

Inputs (from benchmark_hypothesis.py):
- paired_manifest.csv
- fold_metrics.csv
- comparisons.json

Outputs:
- tables/*.csv and tables/*.tex
- figures/*.png and figures/*.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-dir", type=Path, default=Path("pipeline_outputs"))
    parser.add_argument("--out-dir", type=Path, default=Path("pipeline_outputs/paper"))
    parser.add_argument("--dpi", type=int, default=600)
    return parser.parse_args()


def ci95(series: pd.Series) -> tuple[float, float, float]:
    vals = series.dropna().to_numpy(dtype=float)
    if len(vals) == 0:
        return np.nan, np.nan, np.nan
    mean = float(np.mean(vals))
    if len(vals) == 1:
        return mean, mean, mean
    se = np.std(vals, ddof=1) / np.sqrt(len(vals))
    # t critical for n=5 folds is 2.776; this keeps CI conservative for small n.
    t_crit = 2.776 if len(vals) <= 5 else 1.96
    lo = mean - t_crit * se
    hi = mean + t_crit * se
    return mean, lo, hi


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 600,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def modality_label(modality: str) -> str:
    mapping = {
        "sound_phone": "Smartphone audio",
        "sound_vibrometer": "Vibrometer waveform",
        "current": "Armature current",
    }
    return mapping.get(modality, modality)


def write_table(df: pd.DataFrame, stem: str, out_tables: Path) -> None:
    out_tables.mkdir(parents=True, exist_ok=True)
    csv_path = out_tables / f"{stem}.csv"
    tex_path = out_tables / f"{stem}.tex"
    df.to_csv(csv_path, index=False)
    df.to_latex(tex_path, index=False, float_format=lambda x: f"{x:.4f}")


def build_dataset_table(manifest: pd.DataFrame) -> pd.DataFrame:
    by_condition = (
        manifest.groupby(["condition", "operation", "reversal"]).agg(
            n_groups=("group_id", "count"),
            load_min=("load_percent", "min"),
            load_max=("load_percent", "max"),
        )
    ).reset_index()
    by_condition["load_range_percent"] = by_condition.apply(
        lambda r: f"{int(r['load_min'])}-{int(r['load_max'])}", axis=1
    )
    by_condition = by_condition.drop(columns=["load_min", "load_max"])
    by_condition = by_condition.sort_values("condition").reset_index(drop=True)
    by_condition = by_condition.rename(
        columns={
            "condition": "Condition",
            "operation": "Operation family",
            "reversal": "Direction reversal",
            "n_groups": "Paired groups (n)",
            "load_range_percent": "Load range (% rated)",
        }
    )
    return by_condition


def build_performance_summary(fold_metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for modality, grp in fold_metrics.groupby("modality"):
        f1_m, f1_lo, f1_hi = ci95(grp["macro_f1"])
        ba_m, ba_lo, ba_hi = ci95(grp["balanced_acc"])
        mae_m, mae_lo, mae_hi = ci95(grp["mae"])
        rmse_m, rmse_lo, rmse_hi = ci95(grp["rmse"])
        r2_m, r2_lo, r2_hi = ci95(grp["r2"])
        rows.append(
            {
                "Modality": modality_label(modality),
                "Macro F1 (mean)": f1_m,
                "Macro F1 (95% CI low)": f1_lo,
                "Macro F1 (95% CI high)": f1_hi,
                "Balanced accuracy (mean)": ba_m,
                "Balanced accuracy (95% CI low)": ba_lo,
                "Balanced accuracy (95% CI high)": ba_hi,
                "MAE (load percentage points, mean)": mae_m,
                "MAE (95% CI low)": mae_lo,
                "MAE (95% CI high)": mae_hi,
                "RMSE (load percentage points, mean)": rmse_m,
                "RMSE (95% CI low)": rmse_lo,
                "RMSE (95% CI high)": rmse_hi,
                "R2 (mean)": r2_m,
                "R2 (95% CI low)": r2_lo,
                "R2 (95% CI high)": r2_hi,
                "Folds (n)": int(len(grp)),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("Modality").reset_index(drop=True)


def build_noninferiority_table(comparisons: list[dict]) -> pd.DataFrame:
    rows = []
    for c in comparisons:
        rows.append(
            {
                "Comparison": f"Smartphone - {modality_label(c['reference'])}",
                "Delta Macro F1 (mean)": c["delta_f1_mean"],
                "Delta Macro F1 (95% CI low)": c["delta_f1_ci_low"],
                "Delta Macro F1 (95% CI high)": c["delta_f1_ci_high"],
                "Delta MAE (load percentage points, mean)": c["delta_mae_mean"],
                "Delta MAE (95% CI low)": c["delta_mae_ci_low"],
                "Delta MAE (95% CI high)": c["delta_mae_ci_high"],
                "Wilcoxon p (Macro F1 delta)": c["delta_f1_wilcoxon_p"],
                "Wilcoxon p (MAE delta)": c["delta_mae_wilcoxon_p"],
                "Non-inferior overall": bool(c["noninferior_overall"]),
            }
        )
    return pd.DataFrame(rows)


def save_fig(fig: plt.Figure, base: Path, dpi: int) -> None:
    fig.savefig(base.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_classification_metrics(fold_metrics: pd.DataFrame, out_figures: Path, dpi: int) -> None:
    data = fold_metrics.copy()
    data["Modality"] = data["modality"].map(modality_label)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    order = ["Smartphone audio", "Armature current", "Vibrometer waveform"]

    sns.barplot(
        data=data,
        x="Modality",
        y="macro_f1",
        hue="Modality",
        order=order,
        errorbar=("ci", 95),
        ax=axes[0],
        palette="Set2",
        legend=False,
    )
    axes[0].set_title("Condition Classification: Macro F1")
    axes[0].set_ylabel("Macro F1 (unitless)")
    axes[0].set_xlabel("")
    axes[0].tick_params(axis="x", rotation=15)
    axes[0].set_ylim(0, 1.0)

    sns.barplot(
        data=data,
        x="Modality",
        y="balanced_acc",
        hue="Modality",
        order=order,
        errorbar=("ci", 95),
        ax=axes[1],
        palette="Set2",
        legend=False,
    )
    axes[1].set_title("Condition Classification: Balanced Accuracy")
    axes[1].set_ylabel("Balanced accuracy (unitless)")
    axes[1].set_xlabel("")
    axes[1].tick_params(axis="x", rotation=15)
    axes[1].set_ylim(0, 1.0)

    save_fig(fig, out_figures / "fig_classification_metrics", dpi)


def plot_regression_metrics(fold_metrics: pd.DataFrame, out_figures: Path, dpi: int) -> None:
    data = fold_metrics.copy()
    data["Modality"] = data["modality"].map(modality_label)
    order = ["Smartphone audio", "Armature current", "Vibrometer waveform"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)

    sns.barplot(
        data=data,
        x="Modality",
        y="mae",
        hue="Modality",
        order=order,
        errorbar=("ci", 95),
        ax=axes[0],
        palette="Set1",
        legend=False,
    )
    axes[0].set_title("Load Estimation: MAE")
    axes[0].set_ylabel("MAE (load percentage points)")
    axes[0].set_xlabel("")
    axes[0].tick_params(axis="x", rotation=15)

    sns.barplot(
        data=data,
        x="Modality",
        y="rmse",
        hue="Modality",
        order=order,
        errorbar=("ci", 95),
        ax=axes[1],
        palette="Set1",
        legend=False,
    )
    axes[1].set_title("Load Estimation: RMSE")
    axes[1].set_ylabel("RMSE (load percentage points)")
    axes[1].set_xlabel("")
    axes[1].tick_params(axis="x", rotation=15)

    sns.barplot(
        data=data,
        x="Modality",
        y="r2",
        hue="Modality",
        order=order,
        errorbar=("ci", 95),
        ax=axes[2],
        palette="Set1",
        legend=False,
    )
    axes[2].set_title("Load Estimation: R2")
    axes[2].set_ylabel("R2 (unitless)")
    axes[2].set_xlabel("")
    axes[2].tick_params(axis="x", rotation=15)
    axes[2].set_ylim(0, 1.0)

    save_fig(fig, out_figures / "fig_regression_metrics", dpi)


def plot_noninferiority(comparisons: list[dict], out_figures: Path, dpi: int) -> None:
    comp_df = pd.DataFrame(comparisons)
    comp_df["Comparison"] = comp_df["reference"].map(
        lambda x: f"Smartphone - {modality_label(x)}"
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)

    y = np.arange(len(comp_df))
    f1_mean = comp_df["delta_f1_mean"].to_numpy()
    f1_lo = comp_df["delta_f1_ci_low"].to_numpy()
    f1_hi = comp_df["delta_f1_ci_high"].to_numpy()
    xerr_f1 = np.vstack([f1_mean - f1_lo, f1_hi - f1_mean])

    axes[0].errorbar(
        f1_mean,
        y,
        xerr=xerr_f1,
        fmt="o",
        color="#1f77b4",
        capsize=4,
    )
    axes[0].axvline(0.0, color="black", linestyle="--", linewidth=1, label="No difference")
    axes[0].axvline(-0.05, color="red", linestyle=":", linewidth=1.2, label="Non-inferiority margin")
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(comp_df["Comparison"])
    axes[0].set_title("Non-inferiority: Delta Macro F1")
    axes[0].set_xlabel("Delta Macro F1 (phone - reference, unitless)")
    axes[0].legend(loc="lower right", frameon=True)

    mae_mean = comp_df["delta_mae_mean"].to_numpy()
    mae_lo = comp_df["delta_mae_ci_low"].to_numpy()
    mae_hi = comp_df["delta_mae_ci_high"].to_numpy()
    xerr_mae = np.vstack([mae_mean - mae_lo, mae_hi - mae_mean])

    axes[1].errorbar(
        mae_mean,
        y,
        xerr=xerr_mae,
        fmt="o",
        color="#2ca02c",
        capsize=4,
    )
    axes[1].axvline(0.0, color="black", linestyle="--", linewidth=1, label="No difference")
    axes[1].axvline(5.0, color="red", linestyle=":", linewidth=1.2, label="Non-inferiority margin")
    axes[1].set_yticks(y)
    axes[1].set_yticklabels(comp_df["Comparison"])
    axes[1].set_title("Non-inferiority: Delta MAE")
    axes[1].set_xlabel("Delta MAE (load percentage points, phone - reference)")
    axes[1].legend(loc="lower right", frameon=True)

    save_fig(fig, out_figures / "fig_noninferiority", dpi)


def plot_fold_metric_distributions(fold_metrics: pd.DataFrame, out_figures: Path, dpi: int) -> None:
    data = fold_metrics.copy()
    data["Modality"] = data["modality"].map(modality_label)
    order = ["Smartphone audio", "Armature current", "Vibrometer waveform"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)

    sns.boxplot(
        data=data,
        x="Modality",
        y="macro_f1",
        order=order,
        ax=axes[0],
        palette="Pastel1",
    )
    sns.stripplot(
        data=data,
        x="Modality",
        y="macro_f1",
        order=order,
        ax=axes[0],
        color="black",
        size=3,
        alpha=0.6,
    )
    axes[0].set_title("Fold Distribution: Macro F1")
    axes[0].set_ylabel("Macro F1 (unitless)")
    axes[0].set_xlabel("")
    axes[0].tick_params(axis="x", rotation=15)

    sns.boxplot(
        data=data,
        x="Modality",
        y="mae",
        order=order,
        ax=axes[1],
        palette="Pastel2",
    )
    sns.stripplot(
        data=data,
        x="Modality",
        y="mae",
        order=order,
        ax=axes[1],
        color="black",
        size=3,
        alpha=0.6,
    )
    axes[1].set_title("Fold Distribution: MAE")
    axes[1].set_ylabel("MAE (load percentage points)")
    axes[1].set_xlabel("")
    axes[1].tick_params(axis="x", rotation=15)

    save_fig(fig, out_figures / "fig_fold_distributions", dpi)


def main() -> None:
    args = parse_args()
    in_dir = args.in_dir
    out_dir = args.out_dir
    out_tables = out_dir / "tables"
    out_figures = out_dir / "figures"
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)

    setup_style()

    manifest = pd.read_csv(in_dir / "paired_manifest.csv")
    fold_metrics = pd.read_csv(in_dir / "fold_metrics.csv")
    with (in_dir / "comparisons.json").open("r", encoding="utf-8") as fh:
        comparisons = json.load(fh)

    dataset_table = build_dataset_table(manifest)
    perf_table = build_performance_summary(fold_metrics)
    noninf_table = build_noninferiority_table(comparisons)

    write_table(dataset_table, "table_dataset_overview", out_tables)
    write_table(perf_table, "table_performance_summary", out_tables)
    write_table(noninf_table, "table_noninferiority", out_tables)

    plot_classification_metrics(fold_metrics, out_figures, dpi=args.dpi)
    plot_regression_metrics(fold_metrics, out_figures, dpi=args.dpi)
    plot_noninferiority(comparisons, out_figures, dpi=args.dpi)
    plot_fold_metric_distributions(fold_metrics, out_figures, dpi=args.dpi)

    print("Generated paper tables and figures.")
    print(f"Tables: {out_tables}")
    print(f"Figures: {out_figures}")


if __name__ == "__main__":
    main()
