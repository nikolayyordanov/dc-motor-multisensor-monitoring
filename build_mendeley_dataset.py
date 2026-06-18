#!/usr/bin/env python3
"""
Build a clean, Mendeley-ready dataset from the raw DCData download.

The raw tree (``DCData_dl/изследвания``) uses Cyrillic folder names and
inconsistent file names. This script copies every raw file *unchanged* into a
publishable tree with English names, a sortable file-naming scheme, a
``metadata.csv`` index and a ``README.md`` data descriptor.

Nothing is transformed: the published files are byte-for-byte copies of the
raw recordings (raw-data publication). Suggested ML transformations are
documented in the README as guidance only.

Usage
-----
    python build_mendeley_dataset.py
    python build_mendeley_dataset.py --src DCData_dl/изследвания --out DCData_mendeley
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import struct
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Force UTF-8 console output (Cyrillic paths crash cp1252 terminals).
# --------------------------------------------------------------------------- #
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --------------------------------------------------------------------------- #
# Transliteration maps (Cyrillic raw folder names -> canonical English keys).
#
# Condition branches are discovered automatically as <operation>/<reversal>.
# Known folders are mapped below; any *new* folder (e.g. a controller-fault
# branch added later) is transliterated automatically and still included, so
# you can just drop it in and re-run.
# --------------------------------------------------------------------------- #
OPERATION_MAP = {
    "нормална работа": ("normal", "Normal operation"),
    "разхлабен фундамент": ("loose_foundation", "Loose foundation"),
    # Add explicit names here if you want nicer labels, e.g. a controller
    # fault branch:  "дефект от контролера": ("controller_fault", "Controller-induced fault"),
}

REVERSAL_MAP = {
    "без реверсиране": ("no_reversal", "no"),
    "с реверсиране": ("with_reversal", "yes"),
}

# Cyrillic -> Latin for transliterating unknown folder names (fallback only).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "", "ю": "yu", "я": "ya",
}


def slugify(name: str) -> str:
    """Transliterate Cyrillic and slugify to a safe lowercase key."""
    out = "".join(_TRANSLIT.get(ch, ch) for ch in name.strip().lower())
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")
    return out or "unknown"


def resolve_condition(op_dir: str, rev_dir: str) -> dict:
    """Map an <operation>/<reversal> folder pair to canonical metadata."""
    op_key, op_label = OPERATION_MAP.get(
        op_dir.strip().lower(), (slugify(op_dir), op_dir.strip()))
    rev_key, rev_flag = REVERSAL_MAP.get(
        rev_dir.strip().lower(), (slugify(rev_dir), "unknown"))
    return {
        "key": f"{op_key}_{rev_key}",
        "operation": op_key,
        "reversal": rev_flag,
        "label": f"{op_label}, {rev_dir.strip().lower()}",
    }


# Immediate sensor folder name (any case/variant) -> canonical sensor.
SENSOR_MAP = {
    "вибрации": ("vibration", ".xls"),
    "звук - виброметър": ("sound_vibrometer", ".wav"),
    "звук": ("sound_vibrometer", ".wav"),
    "звук - телефон 1м": ("sound_phone", ".m4a"),
    "звук - телефон": ("sound_phone", ".m4a"),
    "ток осцилоскоп": ("current", ".bin"),
    "ток": ("current", ".bin"),
}

SENSOR_ORDER = ["current", "sound_vibrometer", "sound_phone", "vibration"]


def parse_load(filename: str):
    """Return the integer load percent encoded in a raw file name (or None)."""
    m = re.match(r"\s*(\d+)", Path(filename).stem)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# Lightweight metadata readers (best-effort, never fatal).
# --------------------------------------------------------------------------- #
def wav_info(path: Path) -> dict:
    try:
        with wave.open(str(path), "rb") as w:
            fr = w.getframerate()
            n = w.getnframes()
            return {
                "sample_rate_hz": fr,
                "channels": w.getnchannels(),
                "bit_depth": w.getsampwidth() * 8,
                "duration_s": round(n / fr, 4) if fr else "",
            }
    except Exception:
        return {}


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()


def rigol_bin_info(path: Path) -> dict:
    """Best-effort parse of Rigol/Agilent 'RG01' binary waveform header."""
    try:
        data = path.read_bytes()
        if data[0:2] not in (b"RG", b"AG"):
            return {}
        off = 12
        wh_size = struct.unpack_from("<i", data, off)[0]
        wh = data[off:off + wh_size]
        (_hsize, _wtype, _nbuf, points, _count) = struct.unpack_from(
            "<iiiii", wh, 0)
        x_inc, _x_orig = struct.unpack_from("<dd", wh, 32)
        date = _cstr(wh[56:72])
        tstr = _cstr(wh[72:88])
        fs = round(1.0 / x_inc) if x_inc else ""
        dur = round(points * x_inc, 4) if x_inc else ""
        return {
            "sample_rate_hz": fs,
            "duration_s": dur,
            "n_samples": points,
            "captured": f"{date} {tstr}".strip(),
        }
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build(src_root: Path, out_root: Path):
    data_dir = out_root / "data"
    rows: list[dict] = []
    # Preserve discovery order of conditions for stable tables.
    cond_labels: dict[str, str] = {}

    # Auto-discover <operation>/<reversal> branches under the source root.
    for op_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        for rev_dir in sorted(p for p in op_dir.iterdir() if p.is_dir()):
            cond = resolve_condition(op_dir.name, rev_dir.name)
            branch = rev_dir
            cond_labels.setdefault(cond["key"], cond["label"])
            for sensor_dir in sorted(p for p in branch.iterdir() if p.is_dir()):
                sensor_key = SENSOR_MAP.get(sensor_dir.name.strip().lower())
                if not sensor_key:
                    print(f"  [!] unknown sensor folder: {sensor_dir.name}")
                    continue
                sensor, ext = sensor_key
                for f in sorted(sensor_dir.iterdir()):
                    if not f.is_file():
                        continue
                    load = parse_load(f.name)
                    if load is None:
                        print(f"  [!] cannot parse load from {f.name}; skipped")
                        continue
                    new_name = f"load{load:03d}_{sensor}{ext}"
                    dest = data_dir / cond["key"] / sensor / new_name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)

                    info = {}
                    if ext == ".wav":
                        info = wav_info(f)
                    elif ext == ".bin":
                        info = rigol_bin_info(f)

                    rows.append({
                        "condition": cond["key"],
                        "operation": cond["operation"],
                        "reversal": cond["reversal"],
                        "load_percent": load,
                        "sensor": sensor,
                        "format": ext.lstrip("."),
                        "sample_rate_hz": info.get("sample_rate_hz", ""),
                        "duration_s": info.get("duration_s", ""),
                        "channels": info.get("channels", ""),
                        "bit_depth": info.get("bit_depth", ""),
                        "file_size_bytes": f.stat().st_size,
                        "new_path": str(dest.relative_to(out_root)).replace("\\", "/"),
                        "original_name": f.name,
                        "original_path": str(f.relative_to(src_root)).replace("\\", "/"),
                    })
                    print(f"  + {dest.relative_to(out_root)}")

    # CAD model, if present.
    for stp in src_root.glob("*.stp"):
        dest = out_root / "cad" / stp.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stp, dest)
        rows.append({
            "condition": "", "operation": "", "reversal": "",
            "load_percent": "", "sensor": "cad", "format": "stp",
            "sample_rate_hz": "", "duration_s": "", "channels": "",
            "bit_depth": "", "file_size_bytes": stp.stat().st_size,
            "new_path": str(dest.relative_to(out_root)).replace("\\", "/"),
            "original_name": stp.name, "original_path": stp.name,
        })
        print(f"  + {dest.relative_to(out_root)}")

    return rows, cond_labels


def write_metadata(rows: list[dict], out_root: Path) -> None:
    cols = ["condition", "operation", "reversal", "load_percent", "sensor",
            "format", "sample_rate_hz", "duration_s", "channels", "bit_depth",
            "file_size_bytes", "new_path", "original_name", "original_path"]
    path = out_root / "metadata.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(
            rows,
            key=lambda r: (str(r["condition"]), str(r["sensor"]),
                           r["load_percent"] if isinstance(r["load_percent"], int) else 0),
        ))
    print(f"\nWrote {path.relative_to(out_root.parent)}  ({len(rows)} rows)")


def coverage_table(rows: list[dict], conds: list[str]) -> str:
    loads = [1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    sensors = SENSOR_ORDER
    lines = ["| Condition | Sensor | " + " | ".join(str(l) for l in loads) +
             " | Count |",
             "|---|---|" + "|".join(["---"] * (len(loads) + 1)) + "|"]
    for c in conds:
        for s in sensors:
            present = {r["load_percent"] for r in rows
                       if r["condition"] == c and r["sensor"] == s}
            marks = ["x" if l in present else "·" for l in loads]
            lines.append(f"| {c} | {s} | " + " | ".join(marks) +
                         f" | {len(present)} |")
    return "\n".join(lines)


def write_readme(rows: list[dict], cond_labels: dict, out_root: Path) -> None:
    n_files = len(rows)
    by_fmt: dict[str, int] = {}
    for r in rows:
        by_fmt[r["format"]] = by_fmt.get(r["format"], 0) + 1
    fmt_summary = ", ".join(f"{v} {k.upper()}" for k, v in sorted(by_fmt.items()))
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conds = list(cond_labels.keys())
    cond_rows = "\n".join(
        f"| `{k}` | {cond_labels[k]} |" for k in conds)

    readme = f"""# Multi-Sensor Condition-Monitoring Dataset of a Brushed DC Servo Motor

**Built:** {built}  ·  **Files:** {n_files} ({fmt_summary})  ·  **License:** CC BY 4.0

## 1. Overview

Raw multi-sensor recordings from a **brushed permanent-magnet DC servo motor**
(3PI12.12) driven by a 4-quadrant **thyristor (SCR) converter**. Each sensor data was
recorded separately under the **same operating conditions** — matched load level
and mechanical condition — using four sensors: armature current, an AV-160B
vibrometer probe, a budget Android phone microphone, and vibrometer spot
readings.

**Hypothesis.** The dataset is built to test whether **ordinary smartphone
audio** can replace invasive or specialised diagnostic equipment (current
probes, contact vibrometers) for motor condition monitoring. With the phone
recorded at ~1 m under the same conditions as the instrument-grade references,
researchers can compare models trained on phone audio against those trained on
current and vibrometer signals — i.e. whether a phone alone can estimate load
and tell apart normal operation, direction reversal, and a loose foundation.

Published **as recorded** (raw, untransformed). It also suits load estimation,
foundation-looseness detection, direction-reversal analysis, and
converter/commutation signature studies. Section 6 gives ML suggestions only as
guidance.

## 2. Machine under test

| Parameter | Value |
|---|---|
| Type | Brushed PM DC servo (commutator + graphite brushes) |
| Designation | 3PI12.12 |
| Rated power | 625 W |
| Rated voltage | 110 V DC |
| Rated current | 12.5 A |
| Rated torque | 5.4 N·m |
| Rated speed | 2000 RPM |
| Drive | 4-quadrant thyristor (SCR) converter, armature voltage/current control |

The armature current is **unipolar DC + ripple**. The prominent **300 Hz** line
(6 × 50 Hz) is the 6-pulse converter ripple — a drive signature, not a fault.

## 3. Conditions

Each condition is a folder under `data/`, recorded at up to **13 load levels**
(1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 % of rated power):

| Folder (`data/`) | Description |
|---|---|
{cond_rows}

## 4. Sensors

| Folder | Format | Notes |
|---|---|---|
| `sound_vibrometer` | WAV (44.1 kHz, 16-bit stereo, ~20.5 s) | True vibration waveform from the AV-160B probe's AC output jack (flat to 10 kHz in acceleration mode). Lossless and complete — **recommended primary source.** |
| `current` | BIN (Rigol MSO5074) | Armature-current waveform, 8-bit ADC; sample rate and scaling are in each file header. |
| `sound_phone` | M4A (AAC, lossy) | Budget Android phone microphone ~1 m away. Qualitative use only. |
| `vibration` | XLS | AV-160B **spot readings** (velocity mm/s, acceleration m/s², displacement mm), per ISO 2954. Not a waveform — use for trending vs load. |

The `sound_vibrometer` and `vibration` data both come from one **AV-160B
portable vibrometer** (Amittari) with an external piezoelectric accelerometer
probe: ranges 0.1–400 m/s² / 0.1–400 mm/s / 0.001–4 mm, accuracy ±5 % + 2
digits, acceleration bandwidth up to 10 kHz, AC 2.0 V analog output (recorded
as the WAV).

## 5. Methods (steps to reproduce)

**Test rig.** The 3PI12.12 motor (see Section 2) was driven by a 4-quadrant
thyristor (SCR) converter with armature voltage/current control. Mechanical load
was applied with a coupled load unit and set to 1, 2, 5, 10, 20, 30, 40, 50, 60,
70, 80, 90 and 100 % of rated power.

**Conditions.** The full load sweep was repeated for each condition in
Section 3 (normal without reversal, normal with periodic direction reversal, and
a deliberately loosened foundation without reversal).

**Acquisition (each sensor recorded separately, under the same operating
conditions — not simultaneously):**

- *Armature current* — Rigol MSO5074 oscilloscope, saved as native binary
  waveforms (`.bin`); sample rate and scaling are in each file header
  (~20 s per capture).
- *Vibration waveform* — AV-160B vibrometer external piezoelectric probe; the
  2.0 V AC analog output recorded as 44.1 kHz / 16-bit stereo WAV (~20.5 s).
- *Vibration spot readings* — the same AV-160B in display mode (velocity,
  acceleration, displacement per ISO 2954), logged to XLS.
- *Acoustic* — a budget Android smartphone microphone ~1 m from the machine,
  saved as M4A (AAC).

**Procedure.** For each condition and load level the motor was brought to steady
state, then each sensor was recorded in turn. Files are named
`load{{NNN}}_{{sensor}}` and organised under `data/<condition>/<sensor>/`; see
`metadata.csv` for the full inventory with sample rates and durations.

## 6. Folder structure

```
data/
  <condition>/
    current/            loadNNN_current.bin
    sound_vibrometer/   loadNNN_sound_vibrometer.wav
    sound_phone/        loadNNN_sound_phone.m4a
    vibration/          loadNNN_vibration.xls
cad/                    3D model of the rig (.stp)
metadata.csv            one row per file
README.md
```

`NNN` is the zero-padded load percent (e.g. `load020` = 20 % load).
`metadata.csv` has one row per file with `condition`, `operation`, `reversal`,
`load_percent`, `sensor`, `format`, `sample_rate_hz`, `duration_s`, `channels`,
`bit_depth`, `file_size_bytes`, `new_path`, and the original name/path for
traceability.

## 7. Suggested use (guidance)

- **Phone-vs-instrument benchmark (main hypothesis):** train a model on
  `sound_phone` and compare it against the same model trained on `current` and
  `sound_vibrometer` at matching operating conditions. Strong phone-only
  performance supports replacing invasive probes with a smartphone.
- **Time–frequency images** from the vibrometer WAV (1 s segments, optional
  50 % overlap): Mel-spectrogram, cochleogram, tempogram, chromagram, or CWT
  scalograms — e.g. resized to 224×224 for a CNN.
- **Current signature analysis:** FFT/envelope of the armature current; mind the
  300/600/900 Hz converter ripple and the speed-tracking commutation band.
- **Targets:** load percent and the condition folders give ready-made regression
  and classification labels.
- **Fusion:** combine current + vibrometer + vibration spot readings recorded
  under the same operating conditions.

```python
import soundfile as sf   # pip install soundfile
audio, fs = sf.read("data/normal_no_reversal/sound_vibrometer/load020_sound_vibrometer.wav")
# Rigol .bin: 'RG01' header + samples (sample rate in metadata.csv).
```

## 8. Coverage & limitations

- Not every condition is crossed with reversal — see the table below for the
  exact combinations.
- **Vibration (XLS)** are spot readings, not waveforms; the 1 % / 2 % points are
  absent because vibration is negligible at near-zero load (expected).
- **Current (BIN)** coverage is near-complete (8-bit Rigol ADC); a few load
  points may be missing in a branch.
- **Phone audio (M4A)** is lossy — prefer the vibrometer WAV for spectral work.

### Per-file coverage (x = present, · = missing)

{coverage_table(rows, conds)}

## 9. License & citation

Released under **Creative Commons Attribution 4.0 (CC BY 4.0)**:

> <Authors> ({datetime.now().year}). *Multi-Sensor Condition-Monitoring Dataset
> of a Brushed DC Servo Motor*. Mendeley Data. DOI: <to be assigned>.
"""
    path = out_root / "README.md"
    path.write_text(readme, encoding="utf-8")
    print(f"Wrote {path.relative_to(out_root.parent)}")


def write_license(out_root: Path) -> None:
    text = (
        "This dataset is licensed under the Creative Commons Attribution 4.0 "
        "International License (CC BY 4.0).\n"
        "You are free to share and adapt the material for any purpose, even "
        "commercially, provided you give appropriate credit.\n"
        "Full text: https://creativecommons.org/licenses/by/4.0/\n"
    )
    (out_root / "LICENSE.txt").write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", default="DCData_dl/изследвания",
                   help="Raw source tree (default: DCData_dl/изследвания).")
    p.add_argument("--out", default="DCData_mendeley",
                   help="Output dataset folder (default: DCData_mendeley).")
    args = p.parse_args()

    src_root = Path(args.src)
    out_root = Path(args.out)
    if not src_root.is_dir():
        raise SystemExit(f"Source not found: {src_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"Source: {src_root}\nOutput: {out_root}\n")
    rows, cond_labels = build(src_root, out_root)
    write_metadata(rows, out_root)
    write_readme(rows, cond_labels, out_root)
    write_license(out_root)
    print(f"\nDone. {len(rows)} files published to {out_root}/")


if __name__ == "__main__":
    main()
