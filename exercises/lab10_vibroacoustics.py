"""Standalone Lab10: XLS statistics, WAV spectra and WAV/M4A spectrograms."""
import argparse
import hashlib
import json
from pathlib import Path

import av
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import spectrogram
import soundfile as sf
import xlrd

CONDITIONS = ("normal_no_reversal", "loose_foundation_no_reversal")
SPEEDS = (10, 20, 50, 80, 100)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audio(path):
    if path.suffix.lower() == ".wav":
        y, fs = sf.read(path, dtype="float64", always_2d=True)
        return y[:, 0], fs
    pieces = []
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        fs = stream.codec_context.sample_rate
        resampler = av.AudioResampler(format="fltp", layout=stream.codec_context.layout, rate=fs)
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                pieces.append(converted.to_ndarray()[0].astype(float))
        for converted in resampler.resample(None):
            pieces.append(converted.to_ndarray()[0].astype(float))
    if not pieces:
        raise ValueError(f"No audio: {path}")
    return np.concatenate(pieces), fs


def amplitude(y, fs):
    window = np.hanning(len(y))
    values = np.abs(np.fft.rfft(y * window)) / window.sum()
    values[1:-1 if len(y) % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(len(y), 1 / fs), values


def export(fig, out, name):
    fig.tight_layout()
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out / f"{name}.{ext}", dpi=600, bbox_inches="tight")
    plt.close(fig)


def generate(dataset, out, start=2., duration=4.):
    dataset, out = dataset.resolve(), out.resolve()
    if out.is_relative_to(dataset) or dataset.is_relative_to(out):
        raise ValueError("Output must be separate from the dataset")
    meta = pd.read_csv(dataset / "metadata.csv")
    sources, rows, signals = [], [], {}
    def source(condition, sensor, speed):
        selected = meta[(meta.condition == condition) & (meta.sensor == sensor) & (meta.speed_percent == speed)]
        if len(selected) != 1:
            raise ValueError(f"Expected one source: {condition}, {sensor}, {speed}%")
        path = (dataset / selected.iloc[0].new_path).resolve()
        if not path.is_relative_to(dataset) or not path.is_file():
            raise ValueError(f"Invalid source: {path}")
        sources.append({"path": path.relative_to(dataset).as_posix(), "sha256": sha(path)})
        return path
    for condition in CONDITIONS:
        for speed in SPEEDS:
            path = source(condition, "vibration", speed)
            book = xlrd.open_workbook(str(path))
            values = {name: [] for name in ("Velocity", "Acceleration", "Displacement")}
            for sheet in book.sheets():
                for r in range(sheet.nrows):
                    if sheet.ncols >= 5:
                        name = str(sheet.cell_value(r, 3)).strip()
                        if name in values:
                            cell = sheet.cell(r, 4)
                            value = float(cell.value)
                            if cell.ctype == xlrd.XL_CELL_ERROR or not np.isfinite(value):
                                raise ValueError(f"Invalid reading: {path}")
                            values[name].append(value)
            book.release_resources()
            for name, samples in values.items():
                if not samples:
                    raise ValueError(f"Missing quantity {name}: {path}")
                rows.append({"condition": condition, "speed_percent": speed, "quantity": name,
                             "unit": {"Velocity": "mm/s", "Acceleration": "m/s²", "Displacement": "mm"}[name],
                             "n": len(samples), "mean": np.mean(samples),
                             "sample_sd": np.std(samples, ddof=1) if len(samples) > 1 else np.nan})
        for sensor in ("sound_vibrometer", "sound_phone"):
            y, fs = audio(source(condition, sensor, 50))
            a, n = round(start * fs), round(duration * fs)
            if n < 4096 or a < 0 or a + n > len(y) or fs / 2 < 10000:
                raise ValueError("Invalid interval or sampling rate")
            y = y[a:a+n].copy()
            if not np.isfinite(y).all() or np.max(np.abs(y)) == 0:
                raise ValueError("Invalid audio interval")
            y -= y.mean()
            signals[(condition, sensor)] = (y, fs)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "vibration_statistics.csv", index=False, encoding="utf-8-sig")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True, sharey=True)
    maximum = 0.
    for ax, condition, title in zip(axes, CONDITIONS, ("а) Нормално закрепване", "б) Разхлабено закрепване")):
        y, fs = signals[(condition, "sound_vibrometer")]
        f, amp = amplitude(y, fs)
        mask = f <= 10000
        maximum = max(maximum, amp[mask].max())
        ax.plot(f[mask], amp[mask], linewidth=.65)
        ax.set(title=title, ylabel="Амплитуда (цифров пълен обхват)", xlim=(0, 10000))
        ax.grid(alpha=.25)
    axes[-1].set_xlabel("Честота (Hz)")
    axes[0].set_ylim(0, maximum * 1.08)
    export(fig, out, "fig10_4_amplitude_spectra")
    specs = {}
    for key, (y, fs) in signals.items():
        f, t, power = spectrogram(y, fs, window="hann", nperseg=2048, noverlap=1024,
                                  detrend=False, scaling="density", mode="psd")
        mask = f <= 10000
        specs[key] = (f[mask], t + start, 10 * np.log10(np.maximum(power[mask], 1e-20)))
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for col, sensor in enumerate(("sound_vibrometer", "sound_phone")):
        vmax = max(specs[(condition, sensor)][2].max() for condition in CONDITIONS)
        for row, condition in enumerate(CONDITIONS):
            ax = axes[row, col]
            f, t, db = specs[(condition, sensor)]
            mesh = ax.pcolormesh(t, f, db, vmin=vmax-80, vmax=vmax, shading="auto", rasterized=True)
            letter = ("а", "б")[row] if col == 0 else ("в", "г")[row]
            ax.set_title(f"{letter}) {'Виброметър WAV' if col == 0 else 'Телефон M4A'} — {'нормално' if row == 0 else 'разхлабено'}")
            ax.set_xlabel("Време от началото на записа (s)")
            ax.set_ylabel("Честота (Hz)")
            fig.colorbar(mesh, ax=ax, label="PSD dB re 1 FS²/Hz (не SPL)")
    export(fig, out, "fig10_5_spectrograms")
    assert all(sha(dataset / item["path"]) == item["sha256"] for item in sources)
    report = {"speeds_percent": SPEEDS, "audio_speed_percent": 50, "start_s": start, "duration_s": duration,
              "channel": "first channel, no stereo averaging", "mean_removal": "per selected interval",
              "amplitude_units": "digital full scale; WAV not calibrated mechanical units",
              "FFT": "symmetric Hann, window-sum correction, double interior positive bins only",
              "STFT": "periodic Hann, 2048 samples, 1024 overlap, PSD density; 10log10(PSD / 1FS²/Hz)",
              "color_scales": "same for both conditions within each modality; 80dB range; not calibrated SPL",
              "independence": "sequential nonsynchronous sensor recordings; XLS readings not independent repeats",
              "sources": sources}
    (out / "provenance.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("figures_lab10"))
    parser.add_argument("--start", type=float, default=2.)
    parser.add_argument("--duration", type=float, default=4.)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not np.isfinite([args.start, args.duration]).all() or args.start < 0 or args.duration <= 0:
        parser.error("Invalid start/duration")
    if args.output.exists() and any(args.output.iterdir()) and not args.overwrite:
        parser.error("Nonempty output: choose another folder or --overwrite")
    generate(args.dataset, args.output, args.start, args.duration)
    print("Lab10 figures and XLS statistics saved; source files unchanged.")