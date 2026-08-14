# Multi-Sensor Condition-Monitoring Dataset of a Brushed DC Servo Motor

**Built:** 2026-06-26  ·  **Files:** 386 (98 BIN, 98 M4A, 1 STP, 98 WAV, 91 XLS)  ·  **License:** CC BY 4.0

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
| `suboptimal_control_no_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient), без реверсиране |
| `suboptimal_control_with_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient), с реверсиране |
| `suboptimal_control_rt_no_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient + non-optimal current-regulator gain coefficient), без реверсиране |
| `suboptimal_control_rt_with_reversal` | Suboptimal control (non-optimal speed-regulator gain coefficient + non-optimal current-regulator gain coefficient), с реверсиране |
| `normal_no_reversal` | Normal operation, без реверсиране |
| `normal_with_reversal` | Normal operation, с реверсиране |
| `loose_foundation_no_reversal` | Loose foundation, без реверсиране |
| `loose_foundation_with_reversal` | Loose foundation, с реверсиране |

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
`speed{NNN}_{sensor}` and organised under `data/<condition>/<sensor>/`; see
`metadata.csv` for the full inventory with sample rates and durations.

## 6. Folder structure

```
data/
  <condition>/
    current/            speedNNN_current.bin
    sound_vibrometer/   speedNNN_sound_vibrometer.wav
    sound_phone/        speedNNN_sound_phone.m4a
    vibration/          speedNNN_vibration.xls
cad/                    3D model of the rig (.stp)
metadata.csv            one row per file
README.md
```

`NNN` is the zero-padded speed setpoint (e.g. `speed020` = 20 % of rated speed).
The `speed` prefix encodes the commanded speed (% of rated speed); the motor
runs unloaded, so this is not a mechanical load.
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

## 9. License & citation

Released under **Creative Commons Attribution 4.0 (CC BY 4.0)**:

> <Authors> (2026). *Multi-Sensor Condition-Monitoring Dataset
> of a Brushed DC Servo Motor*. Mendeley Data. DOI: <to be assigned>.
