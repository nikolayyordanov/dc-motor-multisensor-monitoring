# Multi-Sensor Condition-Monitoring Dataset of a Brushed DC Servo Motor

**Built:** 2026-06-26  ·  **Files:** 386 (98 BIN, 98 M4A, 1 STP, 98 WAV, 91 XLS)  ·  **License:** CC BY 4.0

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
README.md
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
  regression and classification labels. Use grouped splits by operating point
  (e.g. leave one speed setpoint out); random file-level splits overestimate
  performance.
- **Multimodal comparison:** compare current, vibrometer and vibration spot
  readings at matched operating points (recorded sequentially, not
  synchronized; not suitable for sample-level fusion).
- Results obtained on this single-motor, no-load laboratory dataset do not
  establish diagnostic performance on other machines or in industrial settings.

```python
import soundfile as sf   # pip install soundfile
audio, fs = sf.read("data/normal_no_reversal/sound_vibrometer/speed020_sound_vibrometer.wav")
# Rigol .bin: 'RG01' header + samples (sample rate in metadata.csv).
```

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
- **Current (BIN)** coverage is complete (98 files; 8-bit Rigol ADC).
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

All 385 measurement files were checked automatically. Values in square
brackets are to be filled in from the check results before publication.

| Check | Current (BIN) | Vibrometer (WAV) | Phone (M4A) | Spot readings (XLS) |
|---|---|---|---|---|
| Opens / decodes completely | [98/98] | [98/98] | [98/98] | [91/91] |
| Matches `metadata.csv` (sample rate, duration, channels) | [ ] | [ ] | [ ] | n/a |
| Duplicate files (identical SHA-256) | [none] | [none] | [none] | [none] |
| Clipping (files affected; max % of samples) | [ ] | [ ] | [ ] | n/a |
| Flat / silent segments | [ ] | [initial X–Y s in N files – reason] | [ ] | n/a |
| Within-recording RMS variation, 1-s windows (median / max) | [ ] | [ ] | [ ] | [variation across readings] |
| Missing files | 0 | 0 | 0 | 7 (1–2 % speed, below detection threshold; see table above) |

## 9. License & citation

Released under **Creative Commons Attribution 4.0 (CC BY 4.0)**:

> Zhilevski, M., Slavov, D., Yordanov, N. (2026). *Multi-Sensor Condition-Monitoring Dataset
> of a Brushed DC Servo Motor*. Mendeley Data. DOI: 10.17632/g28trvywnx.[version].
