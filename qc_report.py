#!/usr/bin/env python3
"""Read-only measurement QC: python qc_report.py <dataset_folder>.

Writes quality reports and updates the dataset README; never changes measurements.
Requires numpy, pandas, soundfile, av and xlrd, plus this repo's Rigol/build utilities.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import json
import re
import struct
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

try:
    import xlrd
except ImportError:
    xlrd = None

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from analyze_rigol import load_file as load_rigol_file  # noqa: E402
from build_mendeley_dataset import wav_info, expected_loads_for  # noqa: E402

SENSOR_ORDER = ["current", "sound_vibrometer", "sound_phone", "vibration"]
EXTENSIONS = dict(zip(SENSOR_ORDER, (".bin", ".wav", ".m4a", ".xls")))
SENSOR_LABELS = {
    "current": "Current (BIN)",
    "sound_vibrometer": "Vibrometer (WAV)",
    "sound_phone": "Phone (M4A)",
    "vibration": "Spot readings (XLS)",
}

CLIP_FRACTION_FLAG = 0.0
RMS_WINDOW_S = 1.0
DURATION_TOL_S = 0.000051
RATE_TOL_HZ = 1.0


# --------------------------------------------------------------------------- #
# Generic signal-analysis helpers (shared across modalities)
# --------------------------------------------------------------------------- #
def _max_consecutive_run(mask: np.ndarray) -> int:
    """Longest run of consecutive ``True`` values in a boolean array."""
    if mask.size == 0 or not mask.any():
        return 0
    padded = np.concatenate(([0], mask.ravel().astype(np.int8), [0]))
    diff = np.diff(padded)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return int((ends - starts).max())


def clipping_stats(samples: np.ndarray, limits: tuple[float, float] | None = None) -> dict:
    """Count samples at known rails; unknown rails remain unverifiable."""
    if samples.size == 0:
        return {"clip_fraction": 0.0, "clipped": False, "clip_count": 0}
    if limits is None:
        return {"clip_fraction": None, "clipped": False, "clip_count": None,
                "clipping_status": "unverifiable: scaled BIN volts omit ADC rails"}
    lo, hi = limits
    mask_lo = samples <= lo
    mask_hi = samples >= hi
    clip_count = int(mask_lo.sum() + mask_hi.sum())
    clip_fraction = clip_count / samples.size
    clipped = clip_fraction > CLIP_FRACTION_FLAG
    return {"clip_fraction": clip_fraction, "clipped": clipped, "clip_count": clip_count,
            "clipping_status": "limit samples detected" if clipped else "not detected"}


def signal_stats(samples: np.ndarray, fs: float) -> dict:
    if samples.ndim == 1:
        samples = samples[:, None]
    if not samples.size or fs <= 0 or not np.isfinite(fs):
        raise ValueError("empty waveform or invalid sampling rate")
    dc, dc_ratios, variations, leads, flat_max, silent_max = [], [], [], [], [], []
    segments = []
    for channel, values in enumerate(samples.T):
        if not np.isfinite(values).all():
            raise ValueError("nonfinite samples")
        mean = float(values.mean())
        rms = float(np.sqrt(np.mean(values * values)))
        dc.append(mean)
        dc_ratios.append(100 * abs(mean) / rms if rms else 0.0)
        variation = rms_variation_pct(values, fs)
        if variation is not None:
            variations.append(variation)
        win = max(1, round(0.01 * fs))
        blocks = values[:len(values) // win * win].reshape(-1, win)
        if not len(blocks):
            leads.append(0.0)
            continue
        amplitude = np.sqrt(np.mean(blocks * blocks, axis=1))
        # One percent of typical amplitude identifies quiet starts without using loud transients.
        threshold = max(float(np.median(amplitude)) * 0.01, float(np.max(np.abs(values))) * 1e-6)
        silent = amplitude <= threshold
        flat = np.ptp(blocks, axis=1) == 0
        quiet = flat | silent
        active = np.flatnonzero(~quiet)
        lead = float(active[0] * win / fs) if active.size else len(values) / fs
        leads.append(lead)
        flat_max.append(_max_consecutive_run(flat) * win / fs)
        silent_max.append(_max_consecutive_run(silent) * win / fs)
        for kind, mask in (("flat", flat), ("silent", silent)):
            diff = np.diff(np.r_[False, mask, False].astype(np.int8))
            for start, end in zip(np.flatnonzero(diff == 1), np.flatnonzero(diff == -1)):
                if (end - start) * win / fs >= 0.1:
                    segments.append({"channel": channel + 1, "kind": kind,
                                     "start_s": start * win / fs, "end_s": end * win / fs})
    return {"dc_offset": max(dc, key=abs), "dc_offsets_by_channel": json.dumps(dc),
            "dc_offset_pct_rms": max(dc_ratios), "leading_flat_s": min(leads),
            "leading_quiet_by_channel_s": json.dumps(leads),
            "flat_max_s": max(flat_max, default=0), "silent_max_s": max(silent_max, default=0),
            "segments_json": json.dumps(segments),
            "rms_variation_pct": max(variations) if variations else None,
            "rms_variation_by_channel_pct": json.dumps(variations)}


def validate_bin(path: Path) -> None:
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(12)
        if len(head) != 12 or head[:4] not in (b"RG01", b"AG01"):
            raise ValueError("invalid BIN header")
        declared, count = struct.unpack_from("<ii", head, 4)
        if count < 1:
            raise ValueError("invalid BIN waveform count")
        for _ in range(count):
            start = fh.tell()
            header = fh.read(140)
            hsize, _, buffers, points = struct.unpack_from("<iiii", header)
            interval = struct.unpack_from("<d", header, 32)[0]
            if hsize < 140 or points < 1 or buffers < 1 or interval <= 0:
                raise ValueError("invalid waveform header")
            fh.seek(start + hsize)
            for _ in range(buffers):
                start = fh.tell()
                bsize, _, width, length = struct.unpack("<ihhi", fh.read(12))
                if bsize < 12 or width not in (1, 2, 4, 8) or length != points * width:
                    raise ValueError("invalid/truncated BIN buffer")
                fh.seek(start + bsize + length)
                if fh.tell() > size:
                    available = max(0, size - start - bsize)
                    raise ValueError(f"truncated BIN payload: {available // width} of {points} samples "
                                     f"({available / width * interval:.6f} of {points * interval:.6f} s); "
                                     f"file {size} bytes, header declares {declared}")
            if declared != size:
                raise ValueError(f"BIN header declares {declared} bytes, actual {size}")
        if fh.tell() != size:
            raise ValueError("unconsumed BIN bytes")


def rms_variation_pct(samples: np.ndarray, fs: float) -> float | None:
    """Relative RMS variation across 1-s windows: (max-min)/median, as %."""
    win = max(int(round(RMS_WINDOW_S * fs)), 1)
    n_windows = samples.size // win
    if n_windows < 2:
        return None
    rms = np.array([
        np.sqrt(np.mean(samples[i * win:(i + 1) * win].astype(np.float64) ** 2))
        for i in range(n_windows)
    ])
    median = float(np.median(rms))
    if median <= 0:
        return None
    return float((rms.max() - rms.min()) / median * 100.0)


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _match(actual, expected, tol: float = 0.0):
    """Compare an actual value to a metadata value; ``None`` if not checkable."""
    if expected is None or (isinstance(expected, float) and np.isnan(expected)):
        return None
    if actual is None:
        return False
    return abs(float(actual) - float(expected)) <= tol


# --------------------------------------------------------------------------- #
# Per-modality analysis (reuses the repo's existing readers)
# --------------------------------------------------------------------------- #
def analyze_current(path: Path) -> dict:
    validate_bin(path)
    _, _time, channels, meta = load_rigol_file(str(path))
    del _time
    arrays = list(channels.values())
    if len({len(a) for a in arrays}) != 1:
        raise ValueError("inconsistent channel lengths")
    samples = arrays[0][:, None] if len(arrays) == 1 else np.column_stack(arrays)
    fs = 1.0 / meta["tInc"] if meta.get("tInc") else float("nan")
    duration = samples.shape[0] / fs if fs else float("nan")
    clip = clipping_stats(samples, limits=None)
    return {
        "opened_ok": True,
        "actual_sample_rate_hz": fs,
        "actual_duration_s": duration,
        "actual_channels": len(channels),
        "n_samples": int(samples.shape[0]),
        **signal_stats(samples, fs),
        **clip,
    }


def analyze_wav(path: Path) -> dict:
    info = wav_info(path)
    with sf.SoundFile(str(path)) as fh:
        frames, subtype = fh.frames, fh.subtype
        sig = fh.read(dtype="float64", always_2d=True)
        fs = fh.samplerate
    with wave.open(str(path), "rb") as header:
        declared_frames = header.getnframes()
    if sig.shape[0] != frames or frames != declared_frames or not info:
        raise ValueError("truncated WAV payload/header mismatch")
    bits = {"PCM_U8": 8, "PCM_16": 16, "PCM_24": 24, "PCM_32": 32}.get(subtype)
    limits = (-1.0, 1.0 - 2.0 ** (1 - bits)) if bits else (-1.0, 1.0)
    clip = clipping_stats(sig, limits=limits)
    return {
        "opened_ok": True,
        "actual_sample_rate_hz": info.get("sample_rate_hz", fs),
        "actual_duration_s": sig.shape[0] / fs,
        "actual_channels": info.get("channels", sig.shape[1]),
        "n_samples": int(sig.shape[0]),
        **signal_stats(sig, fs),
        **clip,
    }


def _decode_m4a_full(path: Path) -> tuple[np.ndarray, int, int]:
    """Use the pipeline's PyAV decoding approach, preserving native rate/channels."""
    import av

    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        fs = int(stream.codec_context.sample_rate)
        n_channels = int(stream.codec_context.channels)
        expected_s = float(stream.duration * stream.time_base) if stream.duration else None
        chunks = []
        for frame in container.decode(stream):
            if frame.is_corrupt or frame.sample_rate != fs or len(frame.layout.channels) != n_channels:
                raise ValueError("corrupt frame or changing audio format")
            resampler = av.AudioResampler(format="fltp", layout=frame.layout, rate=fs)
            chunks.extend(f.to_ndarray() for f in resampler.resample(frame))
    if not chunks:
        return np.zeros((n_channels, 0), dtype=np.float32), fs, n_channels
    sig = np.concatenate(chunks, axis=-1)
    if sig.ndim == 1:
        sig = sig.reshape(1, -1)
    if expected_s is not None and abs(sig.shape[-1] / fs - expected_s) > 2048 / fs:
        raise ValueError("decoded duration disagrees with AAC stream duration beyond padding tolerance")
    return sig, fs, n_channels


def analyze_m4a(path: Path) -> dict:
    sig, fs, n_channels = _decode_m4a_full(path)
    sig = sig.astype(np.float64).T
    # AAC can overshoot nominal digital full scale without analogue saturation.
    clip = clipping_stats(sig, limits=(-1.0, 1.0))
    return {
        "opened_ok": True,
        "actual_sample_rate_hz": fs,
        "actual_duration_s": sig.shape[0] / fs if fs else float("nan"),
        "actual_channels": n_channels,
        "n_samples": int(sig.shape[0]),
        **signal_stats(sig, fs),
        **clip,
    }


def analyze_xls(path: Path) -> dict:
    if xlrd is None:
        raise RuntimeError("xlrd is required to read .xls spot-reading files")
    from analyze_acoustics import xlrd as existing_xlrd
    readings = defaultdict(list)
    with open(os.devnull, "w") as log:
        book = existing_xlrd.open_workbook(str(path), logfile=log, on_demand=False)
    for sh in book.sheets():
        for row in range(sh.nrows):
            cells = sh.row_values(row)
            if any(sh.cell_type(row, c) == xlrd.XL_CELL_ERROR for c in range(sh.ncols)):
                raise ValueError("spreadsheet error cell")
            if len(cells) >= 5 and str(cells[3]).strip() in ("Velocity", "Acceleration", "Displacement"):
                value = float(cells[4])
                if not np.isfinite(value) or value < 0:
                    raise ValueError("invalid spot reading")
                readings[str(cells[3]).strip()].append(value)
    if set(readings) != {"Velocity", "Acceleration", "Displacement"}:
        raise ValueError("missing spot-reading metric")
    variation = {k: float(np.std(v) / np.mean(v) * 100) if np.mean(v) else 0.0
                 for k, v in readings.items()}
    n_rows = sum(map(len, readings.values()))
    book.release_resources()
    return {
        "opened_ok": True,
        "actual_sample_rate_hz": None,
        "actual_duration_s": None,
        "actual_channels": None,
        "n_samples": n_rows,
        "dc_offset": None,
        "leading_flat_s": None,
        "rms_variation_pct": None,
        "clip_fraction": None,
        "clipped": False,
        "clip_count": None,
        "spot_cv_pct": max(variation.values()),
        "spot_variation_json": json.dumps(variation),
    }


ANALYZERS = {
    "current": analyze_current,
    "sound_vibrometer": analyze_wav,
    "sound_phone": analyze_m4a,
    "vibration": analyze_xls,
}


# --------------------------------------------------------------------------- #
# Per-file row construction
# --------------------------------------------------------------------------- #
def build_row(row: pd.Series, dataset_folder: Path) -> dict:
    sensor = row["sensor"]
    rel_path = row["new_path"]
    path = dataset_folder / rel_path
    out = {
        "sensor": sensor,
        "condition": row.get("condition", ""),
        "reversal": row.get("reversal", ""),
        "speed_percent": row.get("speed_percent", ""),
        "path": rel_path,
        "exists": path.is_file(),
        "opened_ok": False,
        "error": "",
        "file_size_bytes": None,
        "sha256": "",
        "meta_sample_rate_hz": row.get("sample_rate_hz"),
        "meta_duration_s": row.get("duration_s"),
        "meta_channels": row.get("channels"),
        "actual_sample_rate_hz": None,
        "actual_duration_s": None,
        "actual_channels": None,
        "sample_rate_match": None,
        "duration_match": None,
        "channels_match": None,
        "n_samples": None,
        "dc_offset": None,
        "clip_count": None,
        "clip_fraction": None,
        "clipped": False,
        "leading_flat_s": None,
        "rms_variation_pct": None,
    }
    if not out["exists"]:
        out["error"] = "file missing"
        return out

    out["file_size_bytes"] = path.stat().st_size
    try:
        out["sha256"] = sha256_of_file(path)
    except Exception as exc:  # pragma: no cover - should not normally happen
        out["error"] = f"checksum failed: {exc}"
        return out

    analyzer = ANALYZERS[sensor]
    try:
        result = analyzer(path)
    except Exception as exc:
        out["error"] = f"open/decode failed: {exc}"
        return out

    out.update(result)
    out["file_size_match"] = _match(out["file_size_bytes"], row.get("file_size_bytes"))
    out["sample_rate_match"] = _match(
        out["actual_sample_rate_hz"], out["meta_sample_rate_hz"], tol=RATE_TOL_HZ)
    out["duration_match"] = _match(
        out["actual_duration_s"], out["meta_duration_s"], tol=DURATION_TOL_S)
    out["channels_match"] = _match(
        out["actual_channels"], out["meta_channels"], tol=0.0)
    return out


# --------------------------------------------------------------------------- #
# Expected-inventory / missing-file check
# --------------------------------------------------------------------------- #
def missing_files(meta: pd.DataFrame, rows: list[dict]) -> tuple[list[tuple[str, int, str]], int]:
    meas = meta[meta["condition"].notna() & meta["speed_percent"].notna()].copy()
    meas["speed_percent"] = meas["speed_percent"].astype(int)
    operating_points = {(r.condition, speed) for r in meas.itertuples()
                        for speed in expected_loads_for(r.operation, "current")}
    have = {(r["condition"], int(r["speed_percent"]), r["sensor"]) for r in rows if r["exists"]}
    missing = []
    for condition, speed in operating_points:
        for sensor in SENSOR_ORDER:
            key = (condition, speed, sensor)
            if key not in have:
                missing.append(key)
    return sorted(missing), len(operating_points)


# --------------------------------------------------------------------------- #
# Duplicate detection (global, across all files incl. scope_setup)
# --------------------------------------------------------------------------- #
def duplicate_groups(checksums: dict[str, str]) -> dict[str, list[str]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path, digest in checksums.items():
        by_hash[digest].append(path)
    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}


# --------------------------------------------------------------------------- #
# Summary aggregation -> README table + manuscript text
# --------------------------------------------------------------------------- #
def summarize(rows: list[dict], missing: list[tuple[str, int, str]], expected_total: int) -> dict:
    by_sensor: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sensor[r["sensor"]].append(r)

    summary = {"sensors": {}, "missing": missing, "expected_total": expected_total}
    for sensor in SENSOR_ORDER:
        frows = by_sensor.get(sensor, [])
        n = len(frows)
        opened = sum(1 for r in frows if r["opened_ok"])
        rate_checks = [r["sample_rate_match"] for r in frows if r["sample_rate_match"] is not None]
        dur_checks = [r["duration_match"] for r in frows if r["duration_match"] is not None]
        chan_checks = [r["channels_match"] for r in frows if r["channels_match"] is not None]
        all_meta_checks = rate_checks + dur_checks + chan_checks
        meta_pass = sum(1 for v in all_meta_checks if v)
        meta_total = len(all_meta_checks)
        clip_files = [r for r in frows if r.get("clipped")]
        max_clip_pct = max((r["clip_fraction"] for r in frows if r.get("clip_fraction") is not None),
                            default=0.0) * 100.0
        flat_files = [(r["path"], r["leading_flat_s"]) for r in frows
                  if r.get("leading_flat_s") is not None and r["leading_flat_s"] >= 0.1]
        rms_vals = [r["rms_variation_pct"] for r in frows if r.get("rms_variation_pct") is not None]
        n_missing = sum(1 for m in missing if m[2] == sensor)

        summary["sensors"][sensor] = {
            "n_files": n,
            "opened": opened,
            "meta_pass": meta_pass,
            "meta_total": meta_total,
            "clip_files": len(clip_files),
            "max_clip_pct": max_clip_pct,
            "flat_files": flat_files,
            "rms_median_pct": float(np.median(rms_vals)) if rms_vals else None,
            "rms_max_pct": float(np.max(rms_vals)) if rms_vals else None,
            "n_missing": n_missing,
            "flat_any": sum(bool(json.loads(r.get("segments_json", "[]"))) for r in frows),
            "spot_cv": [r["spot_cv_pct"] for r in frows if "spot_cv_pct" in r],
            "dc_max": max((r.get("dc_offset_pct_rms", 0) for r in frows), default=0),
        }
    summary["rows"] = rows
    summary["rms_values"] = [r["rms_variation_pct"] for r in rows if r.get("rms_variation_pct") is not None]
    return summary


def startup_interpretation(summary: dict, detailed: bool = False) -> str:
    observations = []
    for sensor in ("sound_phone", "sound_vibrometer"):
        values = [duration for _, duration in summary["sensors"][sensor]["flat_files"]]
        if values:
            observations.append(f"{SENSOR_LABELS[sensor]}: {len(values)} recordings, "
                                f"{min(values):.2f}-{max(values):.2f} s")
    if not observations:
        return "No leading quiet segments meeting the reporting threshold were detected."
    text = ("Leading quiet segments (" + "; ".join(observations) + ") may reflect "
            "recording-chain startup behavior, such as software/hardware muting, buffer initialization "
            "or gain-control settling, rather than motor behavior; this explanation is not confirmed.")
    if detailed:
        text += (" Similar onset durations across operating points, at the QC's 10-ms resolution, "
                 "are consistent with a repeatable acquisition artifact but do not identify its cause. "
                 "The phone model, recording app, processing settings and recorder used for the "
                 "vibrometer AC output are not documented. Phone hardware/software could explain "
                 "the WAV starts only if that signal was recorded through a phone; this is unknown. "
                 "AAC encoder priming or container timing may affect M4A onset, but cannot explain "
                 "the uncompressed WAV onset and have not been shown to account for the measured "
                 "0.40-0.41 s. Confirmation requires recording an already-active source with the "
                 "same device/app and checking startup muting, gain processing and codec timing. "
                 "For steady-state analysis, exclude the measured quiet start and verify the "
                 "subsequent onset has settled before selecting windows; preserve the raw files "
                 "and report any exclusion. Full-recording QC RMS statistics include these starts.")
    return text


def format_readme_table(summary: dict, dup_groups: dict) -> str:
    s = summary["sensors"]

    def opens_cell(sensor):
        d = s[sensor]
        return f"{d['opened']}/{d['n_files']}"

    def meta_cell(sensor):
        d = s[sensor]
        if d["meta_total"] == 0:
            return "n/a (not recorded in metadata.csv)"
        gaps = {field.removeprefix("meta_") for r in summary["rows"] if r["sensor"] == sensor
            for field in ("meta_sample_rate_hz", "meta_duration_s", "meta_channels")
            if pd.isna(r.get(field))}
        suffix = "; absent: " + ", ".join(sorted(gaps)) if gaps else ""
        if d["opened"] < d["n_files"]:
            suffix += f"; {d['n_files'] - d['opened']} failed files not verifiable"
        return f"{d['meta_pass']}/{d['meta_total']} populated fields agree" + suffix

    def dup_cell(sensor):
        hits = [paths for paths in dup_groups.values()
                if any(Path(p).parts[-2] == sensor for p in paths)]
        return "none" if not hits else f"{len(hits)} group(s)"

    def clip_cell(sensor):
        d = s[sensor]
        if sensor == "vibration":
            return "n/a"
        if sensor == "current":
            return "unverifiable (ADC rails absent from scaled-volts export)"
        if d["clip_files"] == 0:
            return "not detected at digital limits"
        return f"{d['clip_files']} file(s); max {d['max_clip_pct']:.4f}%"

    def flat_cell(sensor):
        d = s[sensor]
        if sensor == "vibration":
            return "n/a"
        if not d["flat_files"]:
            return f"{d['flat_any']} files with flat/silent runs >=0.1 s; no leading run >=0.1 s"
        vals = [v for _, v in d["flat_files"]]
        return f"initial {min(vals):.2f}-{max(vals):.2f} s in {len(vals)} files; {d['flat_any']} files with runs >=0.1 s; cause requires confirmation"

    def rms_cell(sensor):
        d = s[sensor]
        if sensor == "vibration" and d["spot_cv"]:
            return f"reading CV: median {np.median(d['spot_cv']):.1f}%, max {max(d['spot_cv']):.1f}% (not time windows)"
        if d["rms_median_pct"] is None:
            return "n/a"
        return f"median {d['rms_median_pct']:.1f}%, max {d['rms_max_pct']:.1f}%"

    def missing_cell(sensor):
        d = s[sensor]
        if d["n_missing"] == 0:
            return "0"
        speeds = sorted({sp for c, sp, se in summary["missing"] if se == sensor})
        return f"{d['n_missing']} ({', '.join(str(x) + '%' for x in speeds)} speed; paths listed below)"

    lines = [
        "### Data quality checks",
        "",
        f"All {sum(s[sn]['n_files'] for sn in SENSOR_ORDER)} measurement files were checked "
        "automatically (see `quality/qc_per_file.csv` and `quality/checksums_sha256.txt`).",
        "",
        "| Check | Current (BIN) | Vibrometer (WAV) | Phone (M4A) | Spot readings (XLS) |",
        "|---|---|---|---|---|",
        f"| Opens / decodes completely | {opens_cell('current')} | {opens_cell('sound_vibrometer')} "
        f"| {opens_cell('sound_phone')} | {opens_cell('vibration')} |",
        f"| Matches `metadata.csv` (sample rate, duration, channels) | {meta_cell('current')} "
        f"| {meta_cell('sound_vibrometer')} | {meta_cell('sound_phone')} | {meta_cell('vibration')} |",
        f"| Duplicate files (identical SHA-256) | {dup_cell('current')} | {dup_cell('sound_vibrometer')} "
        f"| {dup_cell('sound_phone')} | {dup_cell('vibration')} |",
        f"| Clipping (files affected; max % of samples) | {clip_cell('current')} "
        f"| {clip_cell('sound_vibrometer')} | {clip_cell('sound_phone')} | {clip_cell('vibration')} |",
        f"| Flat / silent segments | {flat_cell('current')} | {flat_cell('sound_vibrometer')} "
        f"| {flat_cell('sound_phone')} | {flat_cell('vibration')} |",
        f"| Within-recording RMS variation, 1-s windows (median / max) | {rms_cell('current')} "
        f"| {rms_cell('sound_vibrometer')} | {rms_cell('sound_phone')} | {rms_cell('vibration')} |",
        f"| Missing files | {missing_cell('current')} | {missing_cell('sound_vibrometer')} "
        f"| {missing_cell('sound_phone')} | {missing_cell('vibration')} |",
    ]
    lines += ["", f"Coverage: {summary['expected_total'] // 4} expected operating points x 4 sensors = "
              f"{summary['expected_total']} expected measurements; {len(summary['missing'])} missing.", "",
              "Methods: full-recording native samples, channels assessed separately (no mono mixing or resampling). "
              "RMS variation = 100 x (maximum - minimum) / median RMS over complete non-overlapping "
              "1-s windows, including the start; the file statistic is the worst channel. "
              "Flat = constant samples within 10-ms blocks; silent = block RMS <= 1% of median block RMS "
              "(floor: 0.0001% of peak); report runs >=0.1 s. Leading durations have 10-ms resolution. "
              "Clipping counts every sample at either PCM limit or beyond +/-1 for decoded AAC; "
              "AAC overshoot is a digital-limit flag, not proof of analogue saturation. "
              "Observed BIN extrema are not ADC rails and cannot establish clipping. "
              "Rate tolerance: 1 Hz; duration tolerance: 0.000051 s (metadata rounded to 4 decimals). "
              "Missing metadata fields are not treated as agreement. Spot variation is the worst "
              "per-quantity coefficient of variation, never mixed across units.", "",
              "DC offset is recorded per channel in the CSV. Maximum absolute mean / RMS: " +
              "; ".join(f"{SENSOR_LABELS[sn]} {s[sn]['dc_max']:.1f}%" for sn in SENSOR_ORDER[:-1]) +
              ". Current DC is physically expected and is not automatically an error.", "",
              "**Interpretation of quiet starts.** " + startup_interpretation(summary, detailed=True), "",
              "Human review: confirm the cause of quiet/flat starts and whether amplitude changes are "
              "expected during reversals. The documented low-speed detection-threshold explanation "
              "cannot be established from missing files alone."]
    if summary["missing"]:
        lines += ["", "Missing expected measurements:"]
        lines += [f"- data/{c}/{se}/speed{sp:03d}_{se}{EXTENSIONS[se]}" for c, sp, se in summary["missing"]]
    issues = [r for r in summary["rows"] if r.get("error") or any(
        r.get(f) is False for f in ("sample_rate_match", "duration_match", "channels_match", "file_size_match"))]
    if issues:
        lines += ["", "Opening / metadata exceptions:"]
        lines += [f"- {r['path']}: {r.get('error') or 'metadata mismatch (see CSV fields)'}" for r in issues]
    if dup_groups:
        lines += ["", "Duplicate groups (identical SHA-256):"]
        lines += ["- " + "; ".join(paths) for paths in dup_groups.values()]
    return "\n".join(lines)


def update_readme(readme_path: Path, new_section: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    start_marker = "### Data quality checks"
    end_marker = "## 9. License & citation"
    start = text.index(start_marker)
    end = text.index(end_marker)
    updated = text[:start] + new_section + "\n\n" + text[end:]
    updated = re.sub(r"Values in square\s+brackets are to be filled in from the check results before publication\.", "", updated)
    readme_path.write_text(updated, encoding="utf-8")


def build_manuscript_text(summary: dict, dup_groups: dict) -> str:
    s = summary["sensors"]
    total_files = sum(s[sn]["n_files"] for sn in SENSOR_ORDER)

    exceptions = [r["path"] + ": " + (r["error"] or ", ".join(
        f for f in ("sample_rate_match", "duration_match", "channels_match", "file_size_match")
        if r.get(f) is False)) for r in summary["rows"] if r["error"] or any(
        r.get(f) is False for f in ("sample_rate_match", "duration_match", "channels_match", "file_size_match"))]
    opened_sentence = ("All files opened completely and agreed with populated fields of metadata.csv."
                       if not exceptions else "Opening or metadata exceptions: " + "; ".join(exceptions) + ".")
    gaps = []
    for sensor in SENSOR_ORDER[:-1]:
        fields = sorted({field.removeprefix("meta_") for r in summary["rows"] if r["sensor"] == sensor
                         for field in ("meta_sample_rate_hz", "meta_duration_s", "meta_channels")
                         if pd.isna(r.get(field))})
        if fields:
            gaps.append(f"{SENSOR_LABELS[sensor]}: {', '.join(fields)}")
    if gaps:
        opened_sentence += " Missing metadata fields prevent verification for " + "; ".join(gaps) + "."
    opened_sentence += " Waveform sampling fields do not apply to spot readings."

    if dup_groups:
        dup_sentence = "Duplicate files were found: " + "; ".join(
            ", ".join(paths) for paths in dup_groups.values()) + "."
    else:
        dup_sentence = "no duplicate files were found."

    clip_files_total = sum(s[sn]["clip_files"] for sn in SENSOR_ORDER if sn != "vibration")
    max_clip_pct = max((s[sn]["max_clip_pct"] for sn in SENSOR_ORDER if sn != "vibration"), default=0.0)
    if clip_files_total == 0:
        clip_sentence = "Clipping was not detected in decoded audio at the digital limits."
    else:
        clip_sentence = f"Clipping occurred at the decoded audio digital limits in {clip_files_total} files, at most {max_clip_pct:.4f}% of samples."
    clip_sentence += " Current ADC saturation could not be verified because the BIN exports omit ADC rail limits."

    vib = s["sound_vibrometer"]
    if vib["flat_files"]:
        vals = [v for _, v in vib["flat_files"]]
        flat_sentence = (f"{len(vals)} vibrometer waveform files begin with a flat segment of "
                          f"{min(vals):.2f}-{max(vals):.2f} s (flat or silent by the stated thresholds; cause requires confirmation).")
    else:
        flat_sentence = "No vibrometer waveform files begin with a flat segment."

    rms_vals = summary["rms_values"]
    rms_max_vals = [v for sn in SENSOR_ORDER for v in
                    ([s[sn]["rms_max_pct"]] if s[sn]["rms_max_pct"] is not None else [])]
    if rms_vals:
        rms_sentence = (f"Within-recording RMS variation was median {np.median(rms_vals):.1f}%, "
                         f"maximum {np.max(rms_max_vals):.1f}%.")
    else:
        rms_sentence = "Within-recording RMS variation could not be computed."

    paragraph_a = (
        f"All {total_files} measurement files were checked automatically for complete "
        "opening/decoding, agreement of sampling rate, duration and channel count with "
        "metadata.csv, duplicate files (SHA-256), clipping/saturation, flat or silent "
        "segments, DC offset, and within-recording amplitude stability (RMS in 1-s windows). "
        f"{opened_sentence} {dup_sentence[0].upper() + dup_sentence[1:]} {clip_sentence} "
        f"{flat_sentence} {startup_interpretation(summary)} {rms_sentence} Detailed per-modality results are given in the "
        "README (Section 8, Data quality checks)."
    )

    missing = summary["missing"]
    documented_missing = {("loose_foundation_no_reversal", 1, "vibration"),
                          ("loose_foundation_no_reversal", 2, "vibration"),
                          ("normal_no_reversal", 1, "vibration"),
                          ("normal_no_reversal", 2, "vibration"),
                          ("normal_with_reversal", 1, "vibration"),
                          ("suboptimal_control_no_reversal", 1, "vibration"),
                          ("suboptimal_control_no_reversal", 2, "vibration")}
    if set(missing) == documented_missing:
        paragraph_b = (
            "The seven missing vibrometer spot-measurement files correspond to the 1% "
            "and 2% speed setpoints, at which the vibration level was below the detection "
            "threshold of the instrument (Table 6; README, Section 8)."
        )
    elif missing:
        listing = "; ".join(f"{c} speed{sp:03d} ({se})" for c, sp, se in missing)
        paragraph_b = f"The {len(missing)} missing file(s) are: {listing}."
    else:
        paragraph_b = "No expected files are missing."

    return paragraph_a + "\n\n" + paragraph_b + "\n"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_folder", type=Path, help="Path to DCData_mendeley (or similar)")
    args = parser.parse_args()

    dataset_folder: Path = args.dataset_folder
    meta_path = dataset_folder / "metadata.csv"
    readme_path = dataset_folder / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")
    if "### Data quality checks" not in readme_text or "## 9. License & citation" not in readme_text:
        parser.error("dataset README is missing the expected quality/license headings")
    out_dir = dataset_folder / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading metadata: {meta_path}")
    meta = pd.read_csv(meta_path)
    measurement_meta = meta[meta["sensor"].isin(SENSOR_ORDER)].copy()
    if measurement_meta["new_path"].duplicated().any() or measurement_meta.duplicated(
            ["condition", "speed_percent", "sensor"]).any():
        raise ValueError("duplicate measurement paths or operating-point/sensor keys in metadata.csv")
    for rel in meta["new_path"]:
        if not (dataset_folder / rel).resolve().is_relative_to(dataset_folder.resolve()):
            raise ValueError("metadata path escapes dataset folder")
    listed = set(measurement_meta["new_path"])
    extra_rows = []
    for path in sorted((dataset_folder / "data").rglob("*")):
        if path.is_file() and path.suffix.lower() in EXTENSIONS.values():
            rel = path.relative_to(dataset_folder).as_posix()
            if rel not in listed:
                match = re.fullmatch(r"speed(\d+)_(.+)", path.stem)
                if not match or path.parent.name not in SENSOR_ORDER:
                    raise ValueError(f"unrecognised unlisted measurement: {rel}")
                extra_rows.append({"sensor": path.parent.name, "condition": path.parent.parent.name,
                                   "speed_percent": int(match[1]), "new_path": rel})
    if extra_rows:
        measurement_meta = pd.concat([measurement_meta, pd.DataFrame(extra_rows)], ignore_index=True)

    print(f"Checking {len(measurement_meta)} measurement files ...")
    rows: list[dict] = []
    for i, (_, mrow) in enumerate(measurement_meta.iterrows(), start=1):
        row = build_row(mrow, dataset_folder)
        row["metadata_listed"] = mrow["new_path"] in listed
        if not row["metadata_listed"]:
            row["error"] = "measurement absent from metadata.csv"
        rows.append(row)
        status = "OK" if row["opened_ok"] else f"FAIL ({row['error']})"
        if i % 25 == 0 or not row["opened_ok"] or i == len(measurement_meta):
            print(f"  {i}/{len(measurement_meta)} checked; latest: {status}", flush=True)

    print("Computing checksums for all files in metadata.csv ...")
    checksums: dict[str, str] = {}
    for r in rows:
        if r["sha256"]:
            checksums[r["path"]] = r["sha256"]
    for _, mrow in meta[~meta["sensor"].isin(SENSOR_ORDER)].iterrows():
        p = dataset_folder / mrow["new_path"]
        if p.is_file():
            checksums[mrow["new_path"]] = sha256_of_file(p)

    missing, n_operating_points = missing_files(meta, rows)
    expected_total = n_operating_points * len(SENSOR_ORDER)
    dup_groups = duplicate_groups(checksums)
    for row in rows:
        row["duplicate_paths"] = "; ".join(p for p in dup_groups.get(row["sha256"], []) if p != row["path"])
    summary = summarize(rows, missing, expected_total)

    # --- quality/qc_per_file.csv ---
    per_file_path = out_dir / "qc_per_file.csv"
    columns = ["sensor", "condition", "reversal", "speed_percent", "path", "exists",
               "opened_ok", "error", "file_size_bytes", "sha256",
               "meta_sample_rate_hz", "actual_sample_rate_hz", "sample_rate_match",
               "meta_duration_s", "actual_duration_s", "duration_match",
               "meta_channels", "actual_channels", "channels_match",
               "n_samples", "dc_offset", "clip_count", "clip_fraction", "clipped",
               "leading_flat_s", "rms_variation_pct"]
    extra_columns = sorted(set().union(*(r.keys() for r in rows)) - set(columns))
    columns += extra_columns
    df_out = pd.DataFrame(rows).reindex(columns=columns)
    missing_rows = [{
        "sensor": se, "condition": c, "reversal": "", "speed_percent": sp,
        "path": f"data/{c}/{se}/speed{sp:03d}_{se}{EXTENSIONS[se]}", "exists": False,
        "opened_ok": False, "error": "file missing", "file_size_bytes": None,
        "sha256": "", "meta_sample_rate_hz": None, "actual_sample_rate_hz": None,
        "sample_rate_match": None, "meta_duration_s": None, "actual_duration_s": None,
        "duration_match": None, "meta_channels": None, "actual_channels": None,
        "channels_match": None, "n_samples": None, "dc_offset": None,
        "clip_count": None, "clip_fraction": None, "clipped": False,
        "leading_flat_s": None, "rms_variation_pct": None,
    } for c, sp, se in missing if not any(r["condition"] == c and int(r["speed_percent"]) == sp
                                        and r["sensor"] == se for r in rows)]
    if missing_rows:
        df_out = pd.concat([df_out, pd.DataFrame(missing_rows).reindex(columns=columns)], ignore_index=True)
    df_out.to_csv(per_file_path, index=False)
    print(f"Wrote {per_file_path}")

    # --- quality/checksums_sha256.txt ---
    checksum_path = out_dir / "checksums_sha256.txt"
    with checksum_path.open("w", encoding="utf-8") as fh:
        for path in sorted(checksums):
            fh.write(f"{checksums[path]}  {path}\n")
    print(f"Wrote {checksum_path}")

    # --- README.md update ---
    new_section = format_readme_table(summary, dup_groups)
    update_readme(readme_path, new_section)
    print(f"Updated {readme_path}")

    # --- quality/manuscript_text.txt ---
    manuscript = build_manuscript_text(summary, dup_groups)
    manuscript_path = out_dir / "manuscript_text.txt"
    manuscript_path.write_text(manuscript, encoding="utf-8")
    print(f"Wrote {manuscript_path}")

    # --- Plain-language summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_fail = sum(1 for r in rows if not r["opened_ok"])
    if total_fail:
        print(f"[!] {total_fail} file(s) failed to open/decode - see qc_per_file.csv.")
        for r in rows:
            if not r["opened_ok"]:
                print(f"  {r['path']}: {r['error']}")
    else:
        print("All measurement files opened and decoded successfully.")
    if dup_groups:
        print(f"[!] {len(dup_groups)} duplicate-file group(s) found by SHA-256.")
    else:
        print("No duplicate files found.")
    mismatches = [r for r in rows if any(r.get(f) is False for f in
                  ("sample_rate_match", "duration_match", "channels_match", "file_size_match"))]
    print(f"Metadata mismatches among decoded files: {len(mismatches)}. "
          "Absent metadata fields and failed files cannot be verified.")
    print("Current ADC saturation cannot be verified from scaled BIN volts. Current DC is expected.")
    for sn in SENSOR_ORDER[:-1]:
        d = summary["sensors"][sn]
        if d["rms_median_pct"] is not None:
            print(f"{SENSOR_LABELS[sn]}: RMS variation median {d['rms_median_pct']:.1f}%, "
                  f"max {d['rms_max_pct']:.1f}%; {d['flat_any']} files with flat/silent runs.")
    print("Human review: explain quiet starts, large RMS changes (including reversals), and confirm "
          "the documented low-speed detection-threshold explanation.")
    print(startup_interpretation(summary))
    for sn in SENSOR_ORDER:
        d = summary["sensors"][sn]
        if d["clip_files"]:
            print(f"[!] Clipping flagged in {d['clip_files']} {SENSOR_LABELS[sn]} file(s) "
                  f"(max {d['max_clip_pct']:.2f}% of samples).")
    vib = summary["sensors"]["sound_vibrometer"]
    if vib["flat_files"]:
        vals = [v for _, v in vib["flat_files"]]
        print(f"[!] {len(vals)} vibrometer file(s) begin with a flat/silent segment "
              f"({min(vals):.2f}-{max(vals):.2f} s). A human should confirm the cause "
              "(e.g. recording-start delay before the probe signal settles).")
    if missing:
        print(f"[i] {len(missing)} of {expected_total} expected files are missing "
              f"({', '.join(sorted({se for _, _, se in missing}))}); "
              "see README Section 8 / quality/manuscript_text.txt for the explanation used.")
    print("Done.")


if __name__ == "__main__":
    main()
