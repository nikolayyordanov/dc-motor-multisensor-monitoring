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
    "неоптимално управление": (
        "suboptimal_control",
        "Suboptimal control (non-optimal speed-regulator gain coefficient)"),
    "неоптимално управление - коеф. рт": (
        "suboptimal_control_rt",
        "Suboptimal control (non-optimal speed-regulator gain coefficient + non-optimal current-regulator gain coefficient)"),
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
    "tок": ("current", ".bin"),  # mixed-script typo: Latin 'T' + Cyrillic 'ок'
    "ток - кр2=0.1": ("current", ".bin"),
}

SENSOR_ORDER = ["current", "sound_vibrometer", "sound_phone", "vibration"]

# Discrete speed setpoints (% of rated speed) targeted for every branch.
EXPECTED_LOADS = [1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# The plain "suboptimal_control" branch cannot run above ~65 % of rated speed:
# the detuned controller / DC-link protection trips, so the sweep stops at a
# 65 % top setpoint instead of 70-100 % (intentional, not a gap). The "coeff.
# РТ" variant is a milder detuning and is recorded across the full 1-100 % range.
SUBOPTIMAL_CAPPED_KEYS = {"suboptimal_control"}
SUBOPTIMAL_TOP_LOAD = 65

# All speed setpoints that may appear anywhere (for table columns).
ALL_LOADS = [1, 2, 5, 10, 20, 30, 40, 50, 60, 65, 70, 80, 90, 100]

# Vibration is a spot RMS reading and is negligible at near-zero speed, so the
# 1 % / 2 % points are intentionally absent for the vibration sensor.
VIBRATION_SKIP_LOADS = {1, 2}


def expected_loads_for(operation_key: str, sensor: str) -> list[int]:
    """Loads that *should* exist for a given operation/sensor combination."""
    if operation_key in SUBOPTIMAL_CAPPED_KEYS:
        loads = [l for l in EXPECTED_LOADS if l < SUBOPTIMAL_TOP_LOAD]
        loads.append(SUBOPTIMAL_TOP_LOAD)
    else:
        loads = list(EXPECTED_LOADS)
    if sensor == "vibration":
        loads = [l for l in loads if l not in VIBRATION_SKIP_LOADS]
    return loads



def parse_load(filename: str):
    """Return the integer speed-setpoint percent encoded in a raw file name (or None)."""
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
                    if f.suffix == ".part":
                        print(f"  [!] skipping incomplete download: {f.name}")
                        continue
                    load = parse_load(f.name)
                    if load is None:
                        print(f"  [!] cannot parse load from {f.name}; skipped")
                        continue
                    new_name = f"speed{load:03d}_{sensor}{ext}"
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
                        "speed_percent": load,
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
            "speed_percent": "", "sensor": "cad", "format": "stp",
            "sample_rate_hz": "", "duration_s": "", "channels": "",
            "bit_depth": "", "file_size_bytes": stp.stat().st_size,
            "new_path": str(dest.relative_to(out_root)).replace("\\", "/"),
            "original_name": stp.name, "original_path": stp.name,
        })
        print(f"  + {dest.relative_to(out_root)}")

    return rows, cond_labels


def write_metadata(rows: list[dict], out_root: Path) -> None:
    cols = ["condition", "operation", "reversal", "speed_percent", "sensor",
            "format", "sample_rate_hz", "duration_s", "channels", "bit_depth",
            "file_size_bytes", "new_path", "original_name", "original_path"]
    path = out_root / "metadata.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(sorted(
            rows,
            key=lambda r: (str(r["condition"]), str(r["sensor"]),
                           r["speed_percent"] if isinstance(r["speed_percent"], int) else 0),
        ))
    print(f"\nWrote {path.relative_to(out_root.parent)}  ({len(rows)} rows)")


def coverage_table(rows: list[dict], conds: list[str]) -> str:
    loads = ALL_LOADS
    sensors = SENSOR_ORDER
    lines = ["| Condition | Sensor | " + " | ".join(str(l) for l in loads) +
             " | Count |",
             "|---|---|" + "|".join(["---"] * (len(loads) + 1)) + "|"]
    for c in conds:
        for s in sensors:
            present = {r["speed_percent"] for r in rows
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
recorded separately under the **same operating conditions** — matched speed setpoint
and mechanical condition — using four sensors: armature current, an AV-160B
vibrometer probe, a budget Android phone microphone, and vibrometer spot
readings.

**Hypothesis.** The dataset is built to test whether **ordinary smartphone
audio** can replace invasive or specialised diagnostic equipment (current
probes, contact vibrometers) for motor condition monitoring. With the phone
recorded at ~1 m under the same conditions as the instrument-grade references,
researchers can compare models trained on phone audio against those trained on
current and vibrometer signals — i.e. whether a phone alone can estimate speed
and tell apart normal operation, direction reversal, and a loose foundation.

Published **as recorded** (raw, untransformed). It also suits speed estimation,
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

Each condition is a folder under `data/`, recorded at up to **13 speed setpoints**
(1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 % of rated speed = 2000 RPM).
The motor runs **unloaded** — no external mechanical load is applied, so each
percentage is a commanded speed, not a load level:

| Folder (`data/`) | Description |
|---|---|
{cond_rows}

Naming note: `suboptimal_control_*` means a non-optimal **speed-regulator
gain coefficient**, while `suboptimal_control_rt_*` means non-optimal
**speed-regulator and current-regulator gain coefficients** (RT variant).

## 4. Sensors

| Folder | Format | Notes |
|---|---|---|
| `sound_vibrometer` | WAV (44.1 kHz, 16-bit stereo, ~20.5 s) | True vibration waveform from the AV-160B probe's AC output jack (flat to 10 kHz in acceleration mode). Lossless and complete — **recommended primary source.** |
| `current` | BIN (Rigol MSO5074) | Armature-current waveform, 8-bit ADC; sample rate and scaling are in each file header. |
| `sound_phone` | M4A (AAC, lossy) | Budget Android phone microphone ~1 m away. Qualitative use only. |
| `vibration` | XLS | AV-160B **spot readings** (velocity mm/s, acceleration m/s², displacement mm), per ISO 2954. Not a waveform — use for trending vs speed. |

The `sound_vibrometer` and `vibration` data both come from one **AV-160B
portable vibrometer** (Amittari) with an external piezoelectric accelerometer
probe: ranges 0.1–400 m/s² / 0.1–400 mm/s / 0.001–4 mm, accuracy ±5 % + 2
digits, acceleration bandwidth up to 10 kHz, AC 2.0 V analog output (recorded
as the WAV).

## 5. Methods (steps to reproduce)

**Test rig.** The 3PI12.12 motor (see Section 2) was driven by a 4-quadrant
thyristor (SCR) converter with armature voltage/current control. No external
mechanical load was applied — the motor ran **unloaded** — while the drive was
commanded to a speed setpoint of 1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90 and
100 % of rated speed (2000 RPM).

**Conditions.** The full speed sweep was repeated for each condition in
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

**Procedure.** For each condition and speed setpoint the motor was brought to steady
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

`NNN` is the zero-padded speed setpoint (e.g. `load020` = 20 % of rated speed).
File names keep the legacy `load` prefix for backward compatibility; it encodes
the commanded speed, not a mechanical load.
`metadata.csv` has one row per file with `condition`, `operation`, `reversal`,
`speed_percent`, `sensor`, `format`, `sample_rate_hz`, `duration_s`, `channels`,
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
- **Targets:** speed setpoint (% of rated speed) and the condition folders give
  ready-made regression and classification labels.
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
- **Suboptimal control (`suboptimal_control_*`)** is recorded only up to a
  **65 % top speed setpoint**: above it the detuned controller / DC-link
  protection trips, so 70–100 % of rated speed cannot be captured. This is a
  physical limit of that detuned setting, not a missing recording.
- **Current-regulator-coefficient variant (`suboptimal_control_rt_*`)** is a
  milder detuning that does reach 100 %; its `current` and `vibration`
  recordings are **scheduled to be added** — those folders may be empty in the
  current release and will be filled in a later version.
- **Vibration (XLS)** are spot readings, not waveforms; the 1 % / 2 % points are
  absent because vibration is negligible at near-zero speed (expected).
- **Current (BIN)** coverage is near-complete (8-bit Rigol ADC); a few speed
  points may be missing in a branch.
- **Phone audio (M4A)** is lossy — prefer the vibrometer WAV for spectral work.

### Per-file coverage (x = present, · = missing; columns = speed setpoint, % of rated speed)

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


# --------------------------------------------------------------------------- #
# Consistency analysis (read-only; does not copy anything).
# --------------------------------------------------------------------------- #
def scan_source(src_root: Path):
    """Walk the raw tree and return found points + discovered labels.

    Returns ``(found, cond_meta, unknown)`` where ``found`` maps
    ``(cond_key, sensor) -> set(load)``, ``cond_meta`` maps
    ``cond_key -> (operation_key, label)`` and ``unknown`` lists unmapped
    sensor folders.
    """
    found: dict[tuple[str, str], set[int]] = {}
    cond_meta: dict[str, tuple[str, str]] = {}
    unknown: list[str] = []

    for op_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        for rev_dir in sorted(p for p in op_dir.iterdir() if p.is_dir()):
            cond = resolve_condition(op_dir.name, rev_dir.name)
            cond_meta.setdefault(cond["key"], (cond["operation"], cond["label"]))
            for sensor_dir in sorted(p for p in rev_dir.iterdir() if p.is_dir()):
                sk = SENSOR_MAP.get(sensor_dir.name.strip().lower())
                if not sk:
                    rel = sensor_dir.relative_to(src_root)
                    unknown.append(str(rel).replace("\\", "/"))
                    continue
                sensor = sk[0]
                for f in sensor_dir.iterdir():
                    if not f.is_file() or f.suffix == ".part":
                        continue
                    load = parse_load(f.name)
                    if load is not None:
                        found.setdefault((cond["key"], sensor), set()).add(load)
    return found, cond_meta, unknown


def analyze(src_root: Path) -> None:
    """Print a folder-consistency report for the raw source tree."""
    found, cond_meta, unknown = scan_source(src_root)
    conds = list(cond_meta.keys())

    print(f"Consistency report for: {src_root}")
    print(f"Conditions discovered: {len(conds)}\n")

    total_present = total_gaps = 0
    for cond in conds:
        op_key, label = cond_meta[cond]
        print(f"== {cond}  ({label}) ==")
        for sensor in SENSOR_ORDER:
            present = found.get((cond, sensor), set())
            expected = expected_loads_for(op_key, sensor)
            missing = [l for l in expected if l not in present]
            extra = sorted(l for l in present if l not in expected)
            if not present and not expected:
                continue
            total_present += len(present)
            total_gaps += len(missing)
            status = "OK" if not missing else f"MISSING {missing}"
            line = (f"  {sensor:16s} {len(present):2d}/{len(expected):2d}  "
                    f"{status}")
            if extra:
                line += f"  [unexpected loads: {extra}]"
            if not present:
                line += "  (folder empty / not yet recorded)"
            print(line)
        print()

    if unknown:
        print("Unmapped sensor folders (add to SENSOR_MAP):")
        for u in unknown:
            print(f"  [!] {u}")
        print()

    print(f"Summary: {total_present} files present, {total_gaps} expected "
          f"points still missing across {len(conds)} conditions.")
    print("Notes:")
    print(f"  - 'suboptimal_control' is capped at a {SUBOPTIMAL_TOP_LOAD} % top "
          "level (controller/DC protection trips above it); 70-100 % are "
          "intentionally absent, not gaps.")
    print(f"  - vibration skips {sorted(VIBRATION_SKIP_LOADS)} % (negligible at "
          "near-zero load), not counted as gaps.")
    print("  - 'suboptimal_control_rt' (коеф. РТ): current and vibration are "
          "scheduled to be recorded later; those folders are expected to fill "
          "in soon.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", default="DCData_dl/изследвания",
                   help="Raw source tree (default: DCData_dl/изследвания).")
    p.add_argument("--out", default="DCData_mendeley",
                   help="Output dataset folder (default: DCData_mendeley).")
    p.add_argument("--analyze-only", action="store_true",
                   help="Print a folder-consistency report and exit "
                        "(does not copy or build anything).")
    args = p.parse_args()

    src_root = Path(args.src)
    out_root = Path(args.out)
    if not src_root.is_dir():
        raise SystemExit(f"Source not found: {src_root}")

    if args.analyze_only:
        analyze(src_root)
        return

    out_root.mkdir(parents=True, exist_ok=True)

    print(f"Source: {src_root}\nOutput: {out_root}\n")
    rows, cond_labels = build(src_root, out_root)
    write_metadata(rows, out_root)
    write_readme(rows, cond_labels, out_root)
    write_license(out_root)
    print(f"\nDone. {len(rows)} files published to {out_root}/")


if __name__ == "__main__":
    main()
