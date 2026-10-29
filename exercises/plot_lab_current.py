"""Самостоятелно създаване на времедиаграми и спектри за лабораторно упражнение.

Пример: python plot_lab_current.py ../DCData_mendeley --speed 30
Изисква Python >= 3.11, numpy и matplotlib. Не променя измерванията.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

CONDITIONS = [
    ("normal_no_reversal", "а) Номинални настройки", "#236b8e"),
    ("loose_foundation_no_reversal", "б) Разхлабен фундамент", "#a55c18"),
    ("suboptimal_control_no_reversal", "в) Неоптимален РС", "#8050a0"),
    ("suboptimal_control_rt_no_reversal", "г) Неоптимален РТ", "#277c59"),
]


def read_interval(path: Path, start_s: float, duration_s: float):
    """Read one scaled-voltage waveform from Rigol RG01/AG01 BIN.

    Supports the single-waveform, single-buffer floating-point export used in
    this dataset. Rejects other layouts instead of guessing their calibration.
    Reads only the requested interval, never a generated time vector/full file.
    """
    if not np.isfinite(start_s) or not np.isfinite(duration_s) or start_s < 0 or duration_s <= 0:
        raise ValueError("Началото е >= 0 и продължителността е > 0; нужни са крайни стойности")
    with path.open("rb") as fh:
        header = fh.read(12)
        if len(header) != 12 or header[:4] not in (b"RG01", b"AG01"):
            raise ValueError(f"Неподдържан BIN формат: {path}")
        declared_size, waveforms = struct.unpack_from("<II", header, 4)
        if waveforms != 1 or path.stat().st_size != declared_size:
            raise ValueError(f"Непълен файл или повече от една вълнова форма: {path}")
        size_bytes = fh.read(4)
        if len(size_bytes) != 4:
            raise ValueError(f"Липсва заглавна част: {path}")
        header_size = struct.unpack("<I", size_bytes)[0]
        if not 60 <= header_size <= 65536:
            raise ValueError(f"Невалиден размер на заглавна част: {path}")
        waveform = size_bytes + fh.read(header_size - 4)
        if len(waveform) != header_size:
            raise ValueError(f"Непълна заглавна част: {path}")
        buffers, points = struct.unpack_from("<II", waveform, 8)
        interval = struct.unpack_from("<d", waveform, 32)[0]
        if buffers != 1 or not np.isfinite(interval) or interval <= 0:
            raise ValueError(f"Неподдържани буфери или период на дискретизация: {path}")
        buffer = fh.read(12)
        if len(buffer) != 12:
            raise ValueError(f"Липсва буфер: {path}")
        buffer_size, buffer_type, width, payload_size = struct.unpack("<IHHI", buffer)
        if buffer_size != 12 or buffer_type != 1 or width not in (4, 8):
            raise ValueError(f"Очаква се буфер с реални числа във волтове: {path}")
        if payload_size != points * width or fh.tell() + payload_size != declared_size:
            raise ValueError(f"Несъответстващ размер на данните: {path}")
        fs = 1.0 / interval
        first = round(start_s * fs)
        count = round(duration_s * fs)
        if count < 3 or first + count > points:
            raise ValueError(f"Избраният интервал е извън записа: {path}")
        fh.seek(first * width, 1)
        raw = fh.read(count * width)
        if len(raw) != count * width:
            raise ValueError(f"Непълен избран интервал: {path}")
    samples = np.frombuffer(raw, dtype=f"<f{width}").astype(np.float64)
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"Невалидни числови стойности: {path}")
    return samples, fs, first


def amplitude_spectrum(samples, fs):
    """Single-sided peak amplitude; symmetric Hann, coherent-gain correction."""
    n = len(samples)
    window = np.hanning(n)
    amplitude = np.abs(np.fft.rfft(samples * window)) / window.sum()
    amplitude[1:-1 if n % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(n, d=1 / fs), amplitude


def overview_envelope(samples, fs, bins=2000):
    """Display-only min/max bins covering every sample (no FFT decimation)."""
    edges = np.linspace(0, len(samples), min(bins, len(samples)) + 1, dtype=int)
    starts = edges[:-1]
    low = np.minimum.reduceat(samples, starts)
    high = np.maximum.reduceat(samples, starts)
    centers = (starts + edges[1:] - 1) / (2 * fs)
    return centers, low, high


def generate(args):
    dataset = args.dataset.resolve()
    sources = [dataset / "data" / condition / "current" / f"speed{args.speed:03d}_current.bin"
               for condition, _, _ in CONDITIONS]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise ValueError("Липсват записи за избраното задание:\n" + "\n".join(missing))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig_t, axes_t = plt.subplots(4, 2, figsize=(10.4, 10.4), sharex="col", sharey=True)
    fig_f, axes_f = plt.subplots(2, 2, figsize=(10.4, 6.4), sharex=True, sharey=True)
    peak, amp_max = 0.0, 0.0
    metrics, records = [], []
    for (condition, title, color), path, (ax_overview, ax_t), ax_f in zip(CONDITIONS, sources, axes_t, axes_f.flat):
        with path.open("rb") as fh:
            before = hashlib.file_digest(fh, "sha256").hexdigest()
        raw, fs, first = read_interval(path, args.start, args.duration)
        mean = float(raw.mean())
        y = raw - mean
        frequency, amplitude = amplitude_spectrum(y, fs)
        count = min(round(args.window_ms / 1000 * fs) + 1, len(y))
        mask = frequency <= args.max_hz
        peak = max(peak, float(np.max(np.abs(y))))
        amp_max = max(amp_max, float(amplitude[mask].max()))
        centers, low, high = overview_envelope(y, fs)
        ax_overview.vlines(centers, low, high, color=color, linewidth=0.5)
        ax_t.plot(np.arange(count) / fs * 1000, y[:count], color=color, linewidth=0.5)
        ax_f.plot(frequency[mask], amplitude[mask], color=color, linewidth=0.85)
        for h in (300, 600, 900, 1200):
            if h <= args.max_hz:
                ax_f.axvline(h, color="#888888", linestyle=":", linewidth=0.7, alpha=0.6)
        for ax in (ax_overview, ax_t, ax_f):
            ax.set_title(title, loc="left", fontweight="bold", fontsize=11)
            ax.grid(alpha=0.22)
            ax.tick_params(labelleft=True, labelbottom=True)
        ax_t.set_xlabel("Време от началото на интервала (ms)")
        ax_overview.set_xlabel("Време от началото на интервала (s)")
        ax_overview.set_ylabel("Променлива съставка (V)")
        ax_overview.set_title(title + " — общ изглед", loc="left", fontsize=10)
        ax_t.set_title(title + " — детайл", loc="left", fontsize=10)
        ax_t.set_ylabel("Променлива съставка (V)")
        ax_f.set_xlabel("Честота (Hz)")
        ax_f.set_ylabel("Амплитуда (V)")
        rms = float(np.sqrt(np.mean(y * y)))
        metrics.append({"condition": condition, "removed_mean_V": mean, "rms_ac_V": rms,
                        "peak_to_peak_V": float(np.ptp(y)),
                        "crest_factor": float(np.max(np.abs(y)) / rms) if rms else None})
        with path.open("rb") as fh:
            checksum = hashlib.file_digest(fh, "sha256").hexdigest()
        if before != checksum:
            raise ValueError(f"Изходният запис е променен по време на обработката: {path}")
        records.append({"source": path.relative_to(dataset).as_posix(), "sha256": checksum,
                        "sample_rate_Hz": fs, "first_sample_index": first, "samples": len(y),
                        "start_s": first / fs, "duration_s": len(y) / fs,
                        "frequency_bin_spacing_Hz": fs / len(y),
                        "overview_bins": len(centers), "detail_samples": count})
        print(f"{condition}: fs={fs:.12g} Hz; N={len(y)}; df={fs / len(y):.12g} Hz")
    for ax_overview, ax_detail in axes_t:
        ax_overview.set_xlim(0, args.duration)
        ax_detail.set_xlim(0, args.window_ms)
        limit = peak * 1.08 if peak else 1.0
        ax_overview.set_ylim(-limit, limit)
    for ax in axes_f.flat:
        ax.set_xlim(0, args.max_hz)
        ax.set_ylim(0, amp_max * 1.1 if amp_max else 1.0)
    args.output.mkdir(parents=True, exist_ok=True)
    for fig, name in ((fig_t, "fig9_5_current_waveforms"), (fig_f, "fig9_6_current_spectra")):
        fig.tight_layout(pad=1.3, h_pad=2.0, w_pad=1.5)
        for extension in ("png", "pdf", "svg"):
            fig.savefig(args.output / f"{name}.{extension}", dpi=600,
                        bbox_inches="tight", facecolor="white")
        plt.close(fig)
    with (args.output / "example_metrics.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    provenance = {"setpoint_percent": args.speed, "measured_speed_available": False,
                  "nominal_base_speed_rpm": 2000, "commanded_speed_rpm": args.speed * 20,
                  "reversal": False, "dataset_root": str(dataset),
                  "mean_removal": "mean of selected interval, separately per recording",
                  "FFT": "symmetric Hann; window-sum correction; double interior positive bins only; no averaging or zero padding",
                  "waveform_window_ms": args.window_ms, "spectral_range_Hz": [0, args.max_hz],
                  "waveform_layout": "four condition rows; full interval (s) left, detail (ms) right",
                  "overview_rendering": "min/max envelope in at most 2000 bins; display only; all samples contribute",
                  "analysis_samples": "FFT and metrics use all original selected samples, not the rendering envelope",
                  "shared_waveform_ylim_V": [-limit, limit],
                  "records": records}
    (args.output / "figure_provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved figures and reports: {args.output.resolve()}")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Папката с data/ и metadata.csv")
    parser.add_argument("--speed", type=int, default=30, help="Задание в проценти (по подразбиране 30)")
    parser.add_argument("--start", type=float, default=2.0, help="Начало на интервала, s")
    parser.add_argument("--duration", type=float, default=2.0, help="Продължителност за FFT, s")
    parser.add_argument("--window-ms", type=float, default=60.0, help="Показан времеви прозорец, ms")
    parser.add_argument("--max-hz", type=float, default=1500.0, help="Горна показана честота, Hz")
    parser.add_argument("--output", type=Path, default=Path("figures_lab09_shared"), help="Изходна папка")
    args = parser.parse_args()
    if not 1 <= args.speed <= 100:
        parser.error("--speed трябва да е между 1 и 100; нужни са записи за четирите състояния")
    if not all(np.isfinite(v) for v in (args.start, args.duration, args.window_ms, args.max_hz)):
        parser.error("Числовите параметри трябва да са крайни")
    if args.start < 0 or min(args.duration, args.window_ms, args.max_hz) <= 0:
        parser.error("Началото е >=0; продължителността, прозорецът и честотата са >0")
    if args.window_ms > args.duration * 1000:
        parser.error("Времевият прозорец не може да надвишава анализирания интервал")
    try:
        generate(args)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()