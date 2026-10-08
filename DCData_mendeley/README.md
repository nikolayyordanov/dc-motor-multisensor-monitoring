# Multi-Sensor Condition-Monitoring Dataset of a Brushed DC Servo Motor

**Built:** 2026-06-26  ·  **Data files:** 386 (98 BIN, 98 M4A, 1 STP, 98 WAV, 91 XLS)  ·  **License:** CC BY 4.0

## 1. Overview

Raw multi-sensor recordings from a **brushed permanent-magnet DC servo motor**
(3PI12.06) driven by a 4-quadrant **thyristor (SCR) converter**. Each sensor data was
recorded separately under the **same operating conditions** — matched speed setpoint
and mechanical condition — using four sensors: armature current, an AV-160B
vibrometer probe, a budget Android phone microphone, and vibrometer spot
readings. Recordings are condition-matched, not synchronized (see Section 5,
*Data structure and independence of recordings*).

**Motivation.** The dataset is built to support research on whether **ordinary
smartphone audio** can complement invasive or specialised diagnostic equipment
(current probes, contact vibrometers) for motor condition monitoring under
laboratory, no-load conditions. With the phone
recorded at ~1 m under the same conditions as the instrument-grade references,
researchers can compare models trained on phone audio against those trained on
current and vibrometer signals — i.e. whether a phone alone can estimate speed
and tell apart normal operation, direction reversal, and a loose foundation.

Published **as recorded** (raw, untransformed). It also suits speed estimation,
foundation-looseness detection, direction-reversal analysis, and
converter/commutation signature studies. Section 7 gives ML suggestions only as
guidance.

## 2. Machine under test

| Parameter | Value |
|---|---|
| Type | Brushed PM DC servo (commutator + graphite brushes) |
| Designation | 3PI12.06 |
| Rated electrical power output (P_el) | 350 W |
| Nominal input voltage (U) | 55 V |
| Continuous nominal current | 12.5 A |
| Maximum peak / starting current | 100 A |
| Nominal torque (M_nom) | 2.7 N·m (at S1 duty) |
| Torque constant (K_t) | 0.24 N·m/A |
| Electrical constant (K_e) | 25 V / 1000 rpm |
| Max. rotation speed (N_max) | 2000 rpm |
| Physical enclosure depth | 50 mm (shorter motor stack) |
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
| `suboptimal_control_no_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient), without reversal |
| `suboptimal_control_with_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient), with reversal |
| `suboptimal_control_rt_no_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient + non-optimal current-regulator gain coefficient), without reversal |
| `suboptimal_control_rt_with_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient + non-optimal current-regulator gain coefficient), with reversal |
| `normal_no_reversal` | Normal operation, without reversal |
| `normal_with_reversal` | Normal operation, with reversal |
| `loose_foundation_no_reversal` | Loose foundation, without reversal |
| `loose_foundation_with_reversal` | Loose foundation, with reversal |

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

**Test rig.** The 3PI12.06 motor (see Section 2) was driven by a 4-quadrant
thyristor (SCR) converter with armature voltage/current control. No external
mechanical load was applied — the motor ran **unloaded** — while the drive was
commanded to a speed setpoint of 1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90 and
100 % of rated speed (2000 RPM).

**Conditions.** The speed sweep was repeated for each of the eight conditions in
Section 3 (four operating states, each without and with periodic direction
reversal); the `suboptimal_control_*` conditions stop at 65 % (see Section 8).

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
`speed{NNN}_{sensor}` and organised under `data/<condition>/<sensor>/`; see
`metadata.csv` for the full inventory with sample rates and durations.

**Data structure and independence of recordings.** Each combination of
`condition` and `speed_percent` in `metadata.csv` is one *operating point*
(98 in total). At each operating point, each sensor was recorded **once**,
one after another, after the motor reached steady state; no operating point
was repeated. Recordings of one operating point are therefore
**condition-matched but not time-synchronized**, and they are not independent
repetitions. For machine learning, keep all recordings of an operating point
(and all segments cut from them) in the same training/validation/test split.

## 6. Folder structure

```
data/
  <condition>/
    current/            speedNNN_current.bin
    sound_vibrometer/   speedNNN_sound_vibrometer.wav
    sound_phone/        speedNNN_sound_phone.m4a
    vibration/          speedNNN_vibration.xls
scope_setup/            Rigol MSO5074 oscilloscope setup file (.stp)
metadata.csv            one row per file
quality/                qc_report.py, requirements.txt, qc_per_file.csv, checksums_sha256.txt
README.md
LICENSE.txt
```

`NNN` is the zero-padded speed setpoint (e.g. `speed020` = 20 % of rated speed).
The `speed` prefix encodes the commanded speed (% of rated speed); the motor
runs unloaded, so this is not a mechanical load.
`metadata.csv` has one row per file with `condition`, `operation`, `reversal`,
`speed_percent`, `sensor`, `format`, `sample_rate_hz`, `duration_s`, `channels`,
`bit_depth`, `file_size_bytes`, `new_path`, and the original name/path for
traceability. Together, `condition` and `speed_percent` identify the operating
point.

## 7. Suggested use (guidance)

- **Phone-vs-instrument comparison (main motivation):** train a model on
  `sound_phone` and compare it against the same model trained on `current` and
  `sound_vibrometer` at matching operating points, to explore whether a
  smartphone could complement invasive probes under these laboratory conditions.
- **Time–frequency images** from the vibrometer WAV (1 s segments, optional
  50 % overlap): Mel-spectrogram, cochleogram, tempogram, chromagram, or CWT
  scalograms — e.g. resized to 224×224 for a CNN.
- **Current signature analysis:** FFT/envelope of the armature current; mind the
  300/600/900 Hz converter ripple and the speed-tracking commutation band.
- **Targets:** speed setpoint (% of rated speed) and the condition folders give
  regression and classification labels. Use grouped splits by operating point
  (e.g. leave one speed setpoint out); random file-level splits overestimate
  performance.
- **Multimodal comparison:** compare current, vibrometer and vibration spot
  readings at matched operating points (recorded sequentially, not
  synchronized; not suitable for sample-level fusion).
- Results obtained on this single-motor, no-load laboratory dataset do not
  establish diagnostic performance on other machines or in industrial settings.

**Reading the files.** `quality/qc_report.py` contains readers for all file
formats (Rigol BIN, WAV, M4A, XLS) and for `metadata.csv`; they can be reused to
load and convert individual recordings (see *Reproducing the quality checks*).
The WAV files can also be read with any audio library, e.g.:

```python
import soundfile as sf   # pip install soundfile
audio, fs = sf.read("data/normal_no_reversal/sound_vibrometer/speed020_sound_vibrometer.wav")
```

The native Rigol `.bin` current files can be read with `load_rigol_file()` from
`quality/qc_report.py` (run from the dataset root):

```python
import sys; sys.path.insert(0, "quality")
from qc_report import load_rigol_file

_, _, channels, info = load_rigol_file("data/normal_no_reversal/current/speed050_current.bin")
name, values = next(iter(channels.items()))   # e.g. "CH1(V)"
dt = info["tInc"]                             # sample interval, s
```

**Example: first five current-channel samples.**

The following readings were decoded from
[data/normal_no_reversal/current/speed050_current.bin](data/normal_no_reversal/current/speed050_current.bin):
normal operation without reversal, at a **50 % commanded speed setpoint**
(1000 RPM nominal, not a measured speed). The channel is **CH1(V)** and its
header time origin is **0 s**. The header sample interval is
**9.99999997475 × 10⁻⁷ s**, corresponding to **1,000,000.00252 Hz**
(nominally **1 MHz**); the small discrepancy reflects header numeric precision.

| Sample index (zero-based) | Time (s) | Channel value (V) |
|---|---:|---:|
| 0 | 0 | 0.283589452505 |
| 1 | 9.99999997475 × 10⁻⁷ | 0.354486823082 |
| 2 | 1.99999999495 × 10⁻⁶ | 0.354486823082 |
| 3 | 2.99999999243 × 10⁻⁶ | 0.354486823082 |
| 4 | 3.9999999899 × 10⁻⁶ | 0.354486823082 |

These are the exported oscilloscope channel values in **volts**, not amperes.
Conversion to armature current requires the documented current-probe transfer
factor and any applicable offset correction; do not assume 1 V = 1 A.

## 8. Coverage & limitations

- Single motor and test rig, no external load, one recording per sensor and
  operating point (no repetitions); sensors recorded sequentially, not
  synchronized. See the table below for the exact per-file coverage.
- **Suboptimal control (`suboptimal_control_*`)** is recorded only up to a
  **65 % top speed setpoint**: above it the detuned controller / DC-link
  protection trips, so 70–100 % of rated speed cannot be captured. This is a
  physical limit of that detuned setting, not a missing recording.
- **Current-regulator-coefficient variant (`suboptimal_control_rt_*`)** is a
  milder detuning that does reach 100 %; all four sensors are complete
  (13 setpoints each).
- **Vibration (XLS)** are spot readings, not waveforms; 7 files at 1 % / 2 % are
  absent because vibration is negligible at near-zero speed (expected).
- **Current (BIN)**: all 98 files are present (8-bit Rigol ADC); one file
  (`normal_with_reversal`, 100 %) is incomplete (11.3 s of 20 s) and is
  retained as recorded — see *Data quality checks*.
- **Vibrometer (WAV)**: a small fraction of samples (at most 0.93 %) is clipped
  in 94 of 98 files; all WAV and M4A recordings begin with a short silent
  segment (see *Data quality checks*).
- **Phone audio (M4A)** is lossy — prefer the vibrometer WAV for spectral work.

### Per-file coverage (x = present, · = missing; columns = speed setpoint, % of rated speed)

| Condition | Sensor | 1 | 2 | 5 | 10 | 20 | 30 | 40 | 50 | 60 | 65 | 70 | 80 | 90 | 100 | Count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| suboptimal_control_no_reversal | current | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_no_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_no_reversal | sound_phone | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_no_reversal | vibration | · | · | x | x | x | x | x | x | x | x | · | · | · | · | 8 |
| suboptimal_control_with_reversal | current | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_with_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_with_reversal | sound_phone | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_with_reversal | vibration | x | x | x | x | x | x | x | x | x | x | · | · | · | · | 10 |
| suboptimal_control_rt_no_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_no_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_no_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_no_reversal | vibration | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_with_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_with_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_with_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| suboptimal_control_rt_with_reversal | vibration | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_no_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_no_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_no_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_no_reversal | vibration | · | · | x | x | x | x | x | x | x | · | x | x | x | x | 11 |
| normal_with_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_with_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_with_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| normal_with_reversal | vibration | · | x | x | x | x | x | x | x | x | · | x | x | x | x | 12 |
| loose_foundation_no_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_no_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_no_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_no_reversal | vibration | · | · | x | x | x | x | x | x | x | · | x | x | x | x | 11 |
| loose_foundation_with_reversal | current | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_with_reversal | sound_vibrometer | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_with_reversal | sound_phone | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |
| loose_foundation_with_reversal | vibration | x | x | x | x | x | x | x | x | x | · | x | x | x | x | 13 |

### Data quality checks

All 385 measurement files were checked automatically (see `quality/qc_per_file.csv` and `quality/checksums_sha256.txt`).

| Check | Current (BIN) | Vibrometer (WAV) | Phone (M4A) | Spot readings (XLS) |
|---|---|---|---|---|
| Opens / decodes completely | 97/98 | 98/98 | 98/98 | 91/91 |
| Matches `metadata.csv` (sample rate, duration, channels) | 194/194 populated fields agree; absent: channels; 1 failed files not verifiable | 294/294 populated fields agree | n/a (not recorded in metadata.csv) | n/a (not recorded in metadata.csv) |
| Duplicate files (identical SHA-256) | none | none | none | none |
| Clipping (files affected; max % of samples) | unverifiable (ADC rails absent from scaled-volts export) | 94 file(s); max 0.9347% | not detected at digital limits | n/a |
| Flat / silent segments | 0 files with flat/silent runs >=0.1 s; no leading run >=0.1 s | initial 0.27-0.27 s in 98 files; 98 files with runs >=0.1 s; cause requires confirmation | initial 0.40-0.41 s in 98 files; 98 files with runs >=0.1 s; cause requires confirmation | n/a |
| Within-recording RMS range, 1-s windows (max–min / median; includes silent start and reversals; median / max) | median 13.3%, max 430.6% | median 25.1%, max 176.2% | median 50.5%, max 234.3% | reading CV: median 168.0%, max 282.8% (not time windows) |
| Missing files | 0 | 0 | 0 | 7 (1%, 2% speed; paths listed below) |

Coverage: 98 expected operating points x 4 sensors = 392 expected measurements; 7 missing.

Methods: full-recording native samples, channels assessed separately (no mono mixing or resampling). RMS variation = 100 x (maximum - minimum) / median RMS over complete non-overlapping 1-s windows, including the start; the file statistic is the worst channel. Flat = constant samples within 10-ms blocks; silent = block RMS <= 1% of median block RMS (floor: 0.0001% of peak); report runs >=0.1 s. Leading durations have 10-ms resolution. Clipping counts every sample at either PCM limit or beyond +/-1 for decoded AAC; AAC overshoot is a digital-limit flag, not proof of analogue saturation. Observed BIN extrema are not ADC rails and cannot establish clipping. Rate tolerance: 1 Hz; duration tolerance: 0.000051 s (metadata rounded to 4 decimals). Missing metadata fields are not treated as agreement. Spot variation is the worst per-quantity coefficient of variation, never mixed across units.

DC offset is recorded per channel in the CSV. Maximum absolute mean / RMS: Current (BIN) 73.0%; Vibrometer (WAV) 0.2%; Phone (M4A) 5.6%. Current DC is physically expected and is not automatically an error.

**Quiet starts.** All WAV and M4A recordings begin with a silent segment
(0.27 s and 0.40–0.41 s, respectively), consistent across all operating points.
Exclude it from steady-state analysis; the raw files are kept unmodified.

Missing expected measurements:
- data/loose_foundation_no_reversal/vibration/speed001_vibration.xls
- data/loose_foundation_no_reversal/vibration/speed002_vibration.xls
- data/normal_no_reversal/vibration/speed001_vibration.xls
- data/normal_no_reversal/vibration/speed002_vibration.xls
- data/normal_with_reversal/vibration/speed001_vibration.xls
- data/suboptimal_control_no_reversal/vibration/speed001_vibration.xls
- data/suboptimal_control_no_reversal/vibration/speed002_vibration.xls

Opening / metadata exceptions:
- data/normal_with_reversal/current/speed100_current.bin: open/decode failed: truncated BIN payload: 11264000 of 20000000 samples (11.264000 of 20.000000 s); file 45056164 bytes, header declares 80000164
  — retained as recorded (incomplete capture; 11.3 s of 20 s). Use with caution.

#### Reproducing the quality checks

`quality/` contains the standalone script `qc_report.py` (all readers embedded;
no other code needed) and `requirements.txt` (NumPy, pandas, SoundFile, PyAV,
xlrd). Tested with 64-bit Python 3.13 on Windows. From the dataset root (the
folder containing `metadata.csv`):

```text
python -m pip install -r quality/requirements.txt
python quality/qc_report.py .
```

The script reads every file completely (allow several minutes and 1–2 GB of
RAM). It never modifies measurement files, `metadata.csv` or this README. It
writes `qc_per_file.csv`, `checksums_sha256.txt` and `qc_summary.txt` to
`quality/`, **overwriting the published reports** — verify your download first
(Linux: `sha256sum -c quality/checksums_sha256.txt`; macOS:
`shasum -a 256 -c quality/checksums_sha256.txt`; Windows: `Get-FileHash -Algorithm SHA256`),
or keep a copy of the published files.

Outputs: `qc_per_file.csv` (one row per file; blank match fields mean
"not verifiable", not "pass"; `clip_fraction` is a fraction, not a percentage)
`checksums_sha256.txt`, and `qc_summary.txt` (summary table). The values are
quality-check flags, not fault labels.


## 9. License & citation

Released under **Creative Commons Attribution 4.0 (CC BY 4.0)**:

> Zhilevski, M., Slavov, D., Yordanov, N. (2026). *Multi-Sensor Condition-Monitoring Dataset
> of a Brushed DC Servo Motor*. Mendeley Data. DOI: 10.17632/g28trvywnx.[version].
