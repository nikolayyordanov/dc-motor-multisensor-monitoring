#!/usr/bin/env python3
"""Generate a Data in Brief manuscript (.docx) for the DCData_mendeley dataset.

The script:
  1. Reads DCData_mendeley/metadata.csv to compute exact file inventories.
  2. Generates four data-descriptive figures (organisation schematic,
     armature-current waveform + spectrum, vibrometer waveform + spectrogram,
     vibration spot readings vs speed) into paper/figures/.
  3. Builds the manuscript following the Data in Brief template, in the style of
     the completed sample article, and embeds the figures.

All figures are wrapped in try/except so the manuscript is always produced even
if a raw file cannot be read; a caption-only note is inserted instead.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "DCData_mendeley"
FIGDIR = ROOT / "paper" / "figures_dib"
FIGDIR.mkdir(parents=True, exist_ok=True)
OUT_DOCX = ROOT / "paper" / "Data_in_Brief_DCData_mendeley.docx"

OPERATION_LABELS = {
    "normal": "Normal operation",
    "loose_foundation": "Loose foundation",
    "suboptimal_control": "Detuned speed regulator",
    "suboptimal_control_rt": "Detuned speed + current regulator",
}
SENSOR_ORDER = ["current", "sound_vibrometer", "sound_phone", "vibration"]
SENSOR_LABELS = {
    "current": "current",
    "sound_vibrometer": "sound_vibrometer",
    "sound_phone": "sound_phone",
    "vibration": "vibration",
}

# --------------------------------------------------------------------------- #
# Raw-file readers (reuse the repository's parsing conventions)
# --------------------------------------------------------------------------- #

def read_rigol_bin_segment(path: Path, seconds: float = 2.0):
    """Return (t, y, fs) for the first ``seconds`` of a Rigol RG01 .bin file."""
    with path.open("rb") as fh:
        head = fh.read(400)
        if head[0:2] not in (b"RG", b"AG"):
            raise ValueError("not a Rigol/Agilent RG01 file")
        wh_size = struct.unpack_from("<i", head, 12)[0]
        wh = head[12:12 + wh_size]
        x_inc = struct.unpack_from("<d", wh, 32)[0]
        buf_hdr = head[12 + wh_size:12 + wh_size + 12]
        bytes_per_point = struct.unpack_from("<h", buf_hdr, 6)[0]
        payload_offset = 12 + wh_size + 12
        fs = 1.0 / x_inc
        n = int(seconds * fs)
        dtype = {4: "<f4", 2: "<i2", 1: "i1"}.get(bytes_per_point, "<f4")
        fh.seek(payload_offset)
        raw = fh.read(n * abs(bytes_per_point if bytes_per_point else 4))
        y = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    t = np.arange(y.size) / fs
    return t, y, fs


def read_wav_mono(path: Path, seconds: float | None = None):
    with wave.open(str(path), "rb") as w:
        fr = w.getframerate()
        nch = w.getnchannels()
        sw = w.getsampwidth()
        nframes = w.getnframes()
        if seconds is not None:
            nframes = min(nframes, int(seconds * fr))
        frames = w.readframes(nframes)
    dtype = {1: np.uint8, 2: "<i2", 4: "<i4"}.get(sw, "<i2")
    data = np.frombuffer(frames, dtype=dtype).astype(np.float64)
    if nch > 1:
        data = data.reshape(-1, nch)[:, 0]
    if sw == 2:
        data /= 32768.0
    return data, fr


def read_vibration_xls_dir(folder: Path):
    """Return {quantity: [(load, mean_value), ...]} from a vibration/ folder."""
    import xlrd  # BIFF spot-reading spreadsheets
    quantities = {"Velocity": [], "Acceleration": [], "Displacement": []}
    for f in sorted(folder.glob("*.xls")):
        try:
            load = int("".join(ch for ch in f.stem if ch.isdigit())[:3])
        except ValueError:
            continue
        try:
            book = xlrd.open_workbook(str(f))
            sh = book.sheet_by_index(0)
        except Exception:
            continue
        acc = {k: [] for k in quantities}
        for r in range(1, sh.nrows):
            if sh.ncols < 5:
                continue
            qty = str(sh.cell_value(r, 3)).strip()
            val = sh.cell_value(r, 4)
            if qty in acc and isinstance(val, float):
                acc[qty].append(val)
        for k, lst in acc.items():
            if lst:
                quantities[k].append((load, float(np.mean(lst))))
    for k in quantities:
        quantities[k].sort()
    return quantities


# --------------------------------------------------------------------------- #
# Figure generation
# --------------------------------------------------------------------------- #

def fig1_organisation(path: Path):
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    ax.axis("off")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)

    def box(x, y, w, h, text, fc="#eaf2fb", ec="#2f5f9e", fs=9, weight="normal"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.6",
                                    linewidth=1.2, edgecolor=ec, facecolor=fc))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, fontweight=weight, color="#12233a")
        return (x + w / 2, y, x + w / 2, y + h)

    def connect(p_bottom, p_top):
        ax.add_patch(FancyArrowPatch((p_bottom[0], p_bottom[1]), (p_top[2], p_top[3]),
                                     arrowstyle="-", color="#7a8aa0", linewidth=1.0))

    root = box(35, 86, 30, 9, "DCData_mendeley/", fc="#d7e6f7", weight="bold", fs=11)

    lvl1 = [
        box(2, 66, 18, 8, "data/", weight="bold"),
        box(22, 66, 16, 8, "cad/\n1v_3v0.stp"),
        box(40, 66, 18, 8, "metadata.csv"),
        box(60, 66, 17, 8, "README.md"),
        box(79, 66, 18, 8, "LICENSE.txt"),
    ]
    for c in lvl1:
        connect((root[0], root[1]), c)

    cond = box(1, 44, 40, 12,
               "8 operating-condition folders\n<operation>_<reversal>/\n"
               "(normal · loose_foundation ·\ndetuned control · detuned control-RT)",
               fc="#eef7ee", ec="#3c8a45", fs=8.5)
    connect((lvl1[0][0], lvl1[0][1]), cond)

    sensors = [
        box(1, 20, 22, 12, "current/\nspeedNNN_current.bin\n(Rigol MSO5074,\n1 MSa/s, ~20 s)",
            fc="#fbf1e6", ec="#c07a2b", fs=8),
        box(25, 20, 24, 12, "sound_vibrometer/\nspeedNNN_sound_vibrometer.wav\n(AV-160B AC out,\n44.1 kHz/16-bit stereo)",
            fc="#fbf1e6", ec="#c07a2b", fs=8),
        box(51, 20, 22, 12, "sound_phone/\nspeedNNN_sound_phone.m4a\n(smartphone mic,\n~1 m, AAC)",
            fc="#fbf1e6", ec="#c07a2b", fs=8),
        box(75, 20, 23, 12, "vibration/\nspeedNNN_vibration.xls\n(AV-160B spot\nreadings, ISO 2954)",
            fc="#fbf1e6", ec="#c07a2b", fs=8),
    ]
    for s in sensors:
        connect((cond[0], cond[1]), s)

    ax.text(50, 6,
            "NNN = zero-padded speed setpoint (001-100, % of rated speed). Each sensor recorded separately under the same operating conditions.",
            ha="center", va="center", fontsize=8, style="italic", color="#44546a")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig2_current(path: Path, bin_path: Path):
    t, y, fs = read_rigol_bin_segment(bin_path, seconds=2.0)
    y = y - np.mean(y)
    # Time window: 60 ms
    win = t <= 0.06
    # Spectrum
    n = y.size
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = np.abs(np.fft.rfft(y * np.hanning(n))) * 2.0 / n
    fmask = freqs <= 1500

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.5))
    axes[0].plot(t[win] * 1e3, y[win], color="#c0392b", linewidth=0.8)
    axes[0].set_xlabel("Time (ms)")
    axes[0].set_ylabel("Armature-current signal (a.u., AC-coupled)")
    axes[0].set_title("(a) Time domain (60 ms window)")
    axes[0].grid(alpha=0.3)

    axes[1].plot(freqs[fmask], amp[fmask], color="#2c3e50", linewidth=0.9)
    for h in (300, 600, 900, 1200):
        axes[1].axvline(h, color="#7f8c8d", linestyle=":", linewidth=0.8)
    axes[1].annotate("300 Hz\n(6-pulse ripple)", xy=(300, amp[fmask].max()),
                     xytext=(430, amp[fmask].max() * 0.85), fontsize=8,
                     arrowprops=dict(arrowstyle="->", color="#555"))
    axes[1].set_xlabel("Frequency (Hz)")
    axes[1].set_ylabel("Amplitude (a.u.)")
    axes[1].set_title("(b) Single-sided amplitude spectrum")
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig3_vibrometer(path: Path, wav_path: Path):
    y, fs = read_wav_mono(wav_path, seconds=6.0)
    t = np.arange(y.size) / fs
    win = t <= 1.0

    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.5))
    axes[0].plot(t[win], y[win], color="#1f6f8b", linewidth=0.6)
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("Amplitude (normalised)")
    axes[0].set_title("(a) Vibration waveform (1 s window)")
    axes[0].grid(alpha=0.3)

    axes[1].specgram(y, NFFT=2048, Fs=fs, noverlap=1024, cmap="magma")
    axes[1].set_ylim(0, 10000)
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Frequency (Hz)")
    axes[1].set_title("(b) Spectrogram (0-10 kHz)")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig4_vibration(path: Path, vib_dir: Path):
    data = read_vibration_xls_dir(vib_dir)
    units = {"Velocity": "mm/s", "Acceleration": "m/s^2", "Displacement": "mm"}
    colors = {"Velocity": "#8e44ad", "Acceleration": "#16a085", "Displacement": "#d35400"}
    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.2))
    for ax, qty in zip(axes, ["Velocity", "Acceleration", "Displacement"]):
        pts = data.get(qty, [])
        if pts:
            loads = [p[0] for p in pts]
            vals = [p[1] for p in pts]
            ax.plot(loads, vals, "o-", color=colors[qty], markersize=4, linewidth=1.2)
        ax.set_title(qty)
        ax.set_xlabel("Speed setpoint (% of rated speed)")
        ax.set_ylabel(f"Mean {qty.lower()} ({units[qty]})")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Metadata statistics
# --------------------------------------------------------------------------- #

def compute_stats():
    meta = pd.read_csv(DATASET / "metadata.csv")
    data = meta[meta["sensor"].isin(SENSOR_ORDER)].copy()
    data["speed_percent"] = data["speed_percent"].astype(int)

    fmt_counts = meta["format"].value_counts().to_dict()
    total_files = len(meta)

    # Per-condition load union and per-sensor counts
    conditions = []
    for cond, g in data.groupby("condition"):
        op = g["operation"].iloc[0]
        rev = g["reversal"].iloc[0]
        loads = sorted(g["speed_percent"].unique().tolist())
        counts = {s: int((g["sensor"] == s).sum()) for s in SENSOR_ORDER}
        conditions.append({
            "condition": cond, "operation": op, "reversal": rev,
            "loads": loads, "counts": counts, "total": int(len(g)),
        })
    # stable order: normal, detuned, detuned-rt, loose; no before yes
    op_rank = {"normal": 0, "suboptimal_control": 1, "suboptimal_control_rt": 2, "loose_foundation": 3}
    conditions.sort(key=lambda c: (op_rank.get(c["operation"], 9), c["reversal"] == "yes"))

    # WAV/current specs
    wav = meta[meta["format"] == "wav"]
    cur = meta[meta["format"] == "bin"]
    wav_dur = (float(wav["duration_s"].min()), float(wav["duration_s"].max()))
    stats = {
        "fmt_counts": fmt_counts,
        "total_files": total_files,
        "conditions": conditions,
        "n_conditions": len(conditions),
        "wav_dur": wav_dur,
        "current_fs": int(cur["sample_rate_hz"].iloc[0]) if len(cur) else 1000000,
        "current_dur": float(cur["duration_s"].iloc[0]) if len(cur) else 20.0,
        "wav_fs": int(wav["sample_rate_hz"].iloc[0]) if len(wav) else 44100,
    }
    return stats


def fmt_loads(loads):
    return ", ".join(str(x) for x in loads)


# --------------------------------------------------------------------------- #
# DOCX helpers
# --------------------------------------------------------------------------- #

def setup_document():
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    return doc


def h1(doc, text):
    h = doc.add_heading(text, level=1)
    for r in h.runs:
        r.font.color.rgb = RGBColor(0, 0, 0)
        r.font.name = "Times New Roman"
        r.font.size = Pt(13)
    return h


def field(doc, label, value):
    p = doc.add_paragraph()
    r = p.add_run(label + ": ")
    r.bold = True
    p.add_run(value)
    return p


def para(doc, text):
    return doc.add_paragraph(text)


def bullet(doc, text):
    return doc.add_paragraph(text, style="List Bullet")


def caption(doc, text, center=False):
    p = doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(9)
    return p


def add_kv_table(doc, rows, widths=None):
    """Two-column table with bold left labels and no separate header row."""
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in rows:
        cells = table.add_row().cells
        cells[0].text = ""
        rk = cells[0].paragraphs[0].add_run(k)
        rk.bold = True
        rk.font.size = Pt(10)
        cells[1].text = ""
        rv = cells[1].paragraphs[0].add_run(v)
        rv.font.size = Pt(9.5)
    if widths:
        for row in table.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    return table


def add_table(doc, header, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, htext in enumerate(header):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(htext)
        run.bold = True
        run.font.size = Pt(10)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(val))
            run.font.size = Pt(9.5)
    if widths:
        for row in table.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    return table


def add_figure(doc, png_path: Path, width_in=6.3):
    if png_path.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(png_path), width=Inches(width_in))
        return True
    return False


# --------------------------------------------------------------------------- #
# Build manuscript
# --------------------------------------------------------------------------- #

def build(stats, fig_ok):
    doc = setup_document()
    fc = stats["fmt_counts"]
    inv = (f"{stats['total_files']} files "
           f"({fc.get('bin', 0)} BIN, {fc.get('wav', 0)} WAV, "
           f"{fc.get('m4a', 0)} M4A, {fc.get('xls', 0)} XLS, {fc.get('stp', 0)} STP)")

    # ---- ARTICLE INFORMATION ---- #
    h1(doc, "ARTICLE INFORMATION")

    field(doc, "Article title",
          "A Multi-Sensor Armature-Current, Vibration and Acoustic Dataset of a "
          "Brushed DC Servo Motor for Condition Monitoring")

    field(doc, "Authors",
          "Marin Zhilevski a,*, Nikolay Yordanov a, Mikho Mikhov a, "
          "Merve Ertar\u011f\u0131n b, Mihriban Gunay b")

    field(doc, "Affiliations",
          "a Faculty of Automatics, Technical University of Sofia, 8 Kliment "
          "Ohridski Blvd., 1000 Sofia, Bulgaria")
    doc.add_paragraph(
        "b University of Munzur, Department of Electrical and Electronics "
        "Engineering, Tunceli, T\u00fcrkiye")

    field(doc, "Corresponding author\u2019s email address", "mzhilevski@tu-sofia.bg")

    field(doc, "Keywords",
          "Armature current; AV-160B vibrometer; Smartphone microphone; "
          "Thyristor converter; Speed estimation; Foundation looseness; "
          "Fault diagnosis; Machine learning")

    field(doc, "Abstract", "")
    para(doc,
         "This article presents a multi-sensor condition-monitoring dataset "
         "recorded from a brushed permanent-magnet DC servo motor (3PI12.12; "
         "625 W, 110 V DC, 12.5 A, 5.4 N\u00b7m, 2000 rpm) driven by a four-quadrant "
         "thyristor (SCR) converter with armature voltage and current control. "
         "The machine was operated, with no external mechanical load, across up to "
         "thirteen speed setpoints (1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90 and "
         "100 % of rated speed) under "
         f"{stats['n_conditions']} operating conditions that combine four "
         "control/mechanical states \u2014 normal operation, a detuned "
         "speed-regulator gain, a detuned speed- and current-regulator gain, and "
         "a deliberately loosened foundation \u2014 each recorded without and with "
         "periodic direction reversal. For every operating point, four sensors "
         "were recorded separately under the same operating conditions: the "
         "armature current with a Rigol MSO5074 oscilloscope (native binary "
         "waveforms), the true vibration waveform from the AC output of an "
         "AV-160B piezoelectric vibrometer (44.1 kHz, 16-bit stereo WAV), the "
         "airborne sound from a budget Android smartphone microphone placed about "
         "1 m away (AAC/M4A), and AV-160B spot readings of velocity, acceleration "
         "and displacement (XLS). The repository is published as raw, "
         f"untransformed recordings and comprises {inv}, together with a per-file "
         "metadata index (sample rate, duration, channels, bit depth and file "
         "size), a 3-D CAD model of the test rig, a README and a CC BY 4.0 "
         "licence. The dataset supports speed estimation, operating-condition "
         "classification, direction-reversal and converter-ripple analysis, and "
         "benchmarking of low-cost smartphone audio against instrument-grade "
         "current and vibration references.")

    # ---- SPECIFICATIONS TABLE ---- #
    h1(doc, "SPECIFICATIONS TABLE")
    spec_rows = [
        ["Subject", "Electrical and Electronic Engineering"],
        ["Specific subject area",
         "Condition monitoring and fault diagnosis of brushed DC servo motors "
         "from armature-current, vibration and acoustic signals, including a "
         "smartphone-versus-instrument sensing comparison."],
        ["Type of data",
         "Raw armature-current waveforms (.bin); raw vibration waveforms (.wav); "
         "raw acoustic recordings (.m4a); vibration spot readings (.xls); "
         "metadata index (.csv); 3-D CAD model (.stp); tables and figures. "
         "Data are Raw (untransformed)."],
        ["Data collection",
         "Recorded on a laboratory test rig comprising a brushed PM DC servo "
         "motor (3PI12.12) driven by a four-quadrant thyristor (SCR) converter "
         "with no external mechanical load (the motor runs unloaded). Armature "
         "current was captured with a Rigol "
         "MSO5074 oscilloscope; the vibration waveform and spot readings (per "
         "ISO 2954) were taken with an AV-160B vibrometer; airborne sound was "
         "recorded with a budget Android smartphone at ~1 m. Each sensor was "
         "recorded separately under the same operating conditions."],
        ["Data source location",
         "Technical University of Sofia, Sofia, Bulgaria."],
        ["Data accessibility",
         "Repository name: Mendeley Data. Data identification number: DOI to be "
         "assigned. Direct URL to data: to be provided upon publication. "
         "Instructions: the dataset will be publicly available through the "
         "Mendeley Data repository under a CC BY 4.0 licence, organised as "
         "described in this article."],
        ["Related research article", "None."],
    ]
    add_kv_table(doc, spec_rows, widths=[2.0, 4.3])

    # ---- VALUE OF THE DATA ---- #
    h1(doc, "VALUE OF THE DATA")
    for b in [
        "The dataset provides raw, matched-condition multi-sensor recordings "
        "(armature current, vibrometer vibration waveform, smartphone audio and "
        "vibrometer spot readings) of a brushed DC servo motor across a wide "
        "speed range, giving ready-made regression (speed setpoint, % of rated "
        "speed) and classification (operating condition) labels.",
        "Because the smartphone microphone is recorded at ~1 m under the same "
        "operating conditions as the instrument-grade current and vibration "
        "references, the data enable a direct benchmark of whether low-cost "
        "smartphone audio can substitute for invasive or specialised diagnostic "
        "equipment.",
        "The data can be reused by researchers in electrical machines, condition "
        "monitoring, predictive maintenance and signal processing to develop and "
        "validate feature-extraction, machine-learning and sensor-fusion methods, "
        "and as a benchmark for comparing diagnostic algorithms.",
        "Four operating states (normal, two levels of controller detuning, and a "
        "loose foundation) combined with two reversal modes support studies of "
        "control-tuning effects, foundation-looseness detection and "
        "direction-reversal transients that are rarely available together in "
        "public datasets.",
        "Publishing the recordings raw and untransformed, with an exact per-file "
        "metadata index and a CAD model of the rig, lets users apply their own "
        "preprocessing and generate application-specific representations "
        "(spectrograms, Mel-spectrograms, scalograms, and current-signature or "
        "envelope spectra) and reproduce the acquisition geometry.",
    ]:
        bullet(doc, b)

    # ---- BACKGROUND ---- #
    h1(doc, "BACKGROUND")
    para(doc,
         "Condition monitoring of electrical drives traditionally relies on "
         "invasive or specialised instrumentation such as current probes and "
         "contact vibrometers, which can be costly or impractical to deploy "
         "widely [1,2]. Airborne sound captured by ubiquitous smartphones is an "
         "attractive low-cost, non-contact alternative, but its diagnostic value "
         "must be assessed against instrument-grade references acquired under the "
         "same operating conditions [3]. This dataset was compiled to enable that "
         "comparison for a brushed permanent-magnet DC servo motor driven by a "
         "four-quadrant thyristor converter \u2014 a drive whose armature current "
         "carries a characteristic 300 Hz (6 \u00d7 50 Hz) six-pulse converter ripple "
         "in addition to commutation signatures. The motor was exercised across a "
         "broad speed range under normal operation, two levels of controller "
         "detuning and a loosened-foundation condition, each without and with "
         "periodic direction reversal, while four sensors were recorded "
         "separately under matched conditions. The resulting raw recordings allow "
         "researchers to compare models trained on smartphone audio against those "
         "trained on current and vibration signals, and to study speed estimation, "
         "foundation-looseness detection, direction-reversal transients and "
         "converter/commutation signatures. The data are released raw and "
         "untransformed so that users can apply their own preprocessing "
         "pipelines [4].")

    # ---- DATA DESCRIPTION ---- #
    h1(doc, "DATA DESCRIPTION")
    para(doc,
         "The dataset contains raw multi-sensor recordings acquired from a single "
         "brushed permanent-magnet DC servo motor on a laboratory test rig. It is "
         "published as byte-for-byte raw recordings organised by operating "
         "condition, sensor and speed setpoint, together with a per-file metadata "
         "index, a 3-D CAD model of the rig, a README descriptor and a licence "
         f"file. In total the repository contains {inv}. Table 1 lists the "
         "top-level organisation of the repository.")

    para(doc, "Table 1. Organisation of the dataset repository.")
    add_table(doc, ["Folder / File", "Description", "Format"], [
        ["data/", "Raw recordings organised as <condition>/<sensor>/speedNNN_sensor.ext", "Folder"],
        ["cad/", "3-D CAD model of the test rig (1v_3v0.stp)", "STP"],
        ["metadata.csv", "One row per file with acquisition parameters and traceability fields", "CSV"],
        ["README.md", "Dataset descriptor (machine, conditions, sensors, methods, coverage)", "Markdown"],
        ["LICENSE.txt", "Creative Commons Attribution 4.0 (CC BY 4.0) licence", "TXT"],
    ], widths=[1.3, 4.2, 0.9])

    para(doc,
         "The machine under test is a brushed permanent-magnet DC servo motor "
         "with a commutator and graphite brushes. Its rated parameters are given "
         "in Table 2. The armature current is unipolar DC with ripple; the "
         "prominent 300 Hz component (6 \u00d7 50 Hz) is the six-pulse converter "
         "ripple of the drive, i.e. a drive signature rather than a fault.")

    para(doc, "Table 2. Rated parameters of the machine under test.")
    add_table(doc, ["Parameter", "Value"], [
        ["Type", "Brushed PM DC servo (commutator + graphite brushes)"],
        ["Designation", "3PI12.12"],
        ["Rated power", "625 W"],
        ["Rated voltage", "110 V DC"],
        ["Rated current", "12.5 A"],
        ["Rated torque", "5.4 N\u00b7m"],
        ["Rated speed", "2000 rpm"],
        ["Drive", "Four-quadrant thyristor (SCR) converter, armature voltage/current control"],
    ], widths=[1.8, 4.5])

    para(doc,
         f"The recordings span {stats['n_conditions']} operating conditions, each "
         "a folder under data/ formed by combining an operation state with a "
         "reversal mode (without or with periodic direction reversal). Table 3 "
         "lists the conditions and the speed setpoints (% of rated speed) present "
         "for each. Naming note: the detuned-speed-regulator condition uses a "
         "non-optimal speed-regulator gain, whereas the detuned "
         "speed-and-current-regulator (RT) condition additionally uses a "
         "non-optimal current-regulator gain.")

    para(doc, "Table 3. Operating conditions and available speed setpoints.")
    cond_rows = []
    for c in stats["conditions"]:
        cond_rows.append([
            f"{c['condition']}",
            OPERATION_LABELS.get(c["operation"], c["operation"]),
            "Yes" if c["reversal"] == "yes" else "No",
            fmt_loads(c["loads"]),
            str(len(c["loads"])),
        ])
    add_table(doc, ["Folder (data/)", "Operation", "Reversal", "Speed setpoints (%)", "No."],
              cond_rows, widths=[1.9, 1.5, 0.7, 1.9, 0.4])

    para(doc,
         "Each condition folder contains up to four sensor sub-folders. The "
         "sensors, instruments and file formats are summarised in Table 4. The "
         "sound_vibrometer WAV and the vibration XLS spot readings both originate "
         "from one AV-160B portable vibrometer (Amittari) with an external "
         "piezoelectric accelerometer probe (ranges 0.1\u2013400 m/s\u00b2 / "
         "0.1\u2013400 mm/s / 0.001\u20134 mm, accuracy \u00b15 % + 2 digits, "
         "acceleration bandwidth up to 10 kHz, 2.0 V AC analog output recorded as "
         "the WAV).")

    para(doc, "Table 4. Sensor channels, instruments and formats.")
    add_table(doc, ["Sub-folder", "Quantity", "Instrument", "Format", "Sampling / notes"], [
        ["current/", "Armature current", "Rigol MSO5074 oscilloscope", ".bin",
         f"{stats['current_fs']/1e6:g} MSa/s (native RG01 binary), ~{stats['current_dur']:.0f} s"],
        ["sound_vibrometer/", "Vibration waveform", "AV-160B vibrometer (AC output)", ".wav",
         f"{stats['wav_fs']} Hz, 16-bit, stereo, {stats['wav_dur'][0]:.1f}\u2013{stats['wav_dur'][1]:.1f} s"],
        ["sound_phone/", "Airborne sound", "Android smartphone microphone (~1 m)", ".m4a", "AAC (lossy)"],
        ["vibration/", "Velocity, acceleration, displacement (spot)", "AV-160B vibrometer (display mode)", ".xls",
         "BIFF spreadsheet, ISO 2954 spot readings"],
    ], widths=[1.2, 1.5, 1.7, 0.6, 1.6])

    para(doc,
         "Files follow the naming scheme speedNNN_sensor.ext, where NNN is the "
         "zero-padded speed setpoint (e.g. speed020 = 20 % of rated speed); the "
         "speed prefix denotes the commanded speed and the motor runs unloaded. "
         "The metadata.csv index has one row per file; its fields are described "
         "in Table 5.")

    para(doc, "Table 5. Fields in metadata.csv.")
    add_table(doc, ["Field", "Description"], [
        ["condition", "Canonical condition key (operation + reversal); matches the data/ sub-folder"],
        ["operation", "Mechanical/control state (normal, loose_foundation, suboptimal_control, suboptimal_control_rt)"],
        ["reversal", "Periodic direction reversal (yes/no)"],
        ["speed_percent", "Speed setpoint as a percentage of rated speed (2000 rpm)"],
        ["sensor", "Sensor channel (current, sound_vibrometer, sound_phone, vibration)"],
        ["format", "File format (bin, wav, m4a, xls, stp)"],
        ["sample_rate_hz", "Sampling rate (current and WAV only)"],
        ["duration_s", "Recording duration in seconds (current and WAV only)"],
        ["channels", "Number of audio channels (WAV only)"],
        ["bit_depth", "Bits per sample (WAV only)"],
        ["file_size_bytes", "File size in bytes"],
        ["new_path", "Path of the file within the repository"],
        ["original_name", "Original raw file name (traceability)"],
        ["original_path", "Original raw folder path (traceability)"],
    ], widths=[1.5, 4.8])

    para(doc,
         "Table 6 gives the number of files available per operating condition and "
         "sensor. Coverage is near-complete on the nominal speed grid; the "
         "detuned-control conditions reach only a ~65 % top speed setpoint because "
         "the detuned controller trips above that speed, the vibration spot "
         "readings omit the near-zero-speed points where vibration is negligible, "
         "and a few individual speed points may be absent in a branch. The 385 sensor "
         "recordings listed in Table 6 are complemented by the CAD model, giving "
         "386 files in total.")

    para(doc, "Table 6. File counts per operating condition and sensor.")
    cnt_rows = []
    totals = {s: 0 for s in SENSOR_ORDER}
    grand = 0
    for c in stats["conditions"]:
        row = [c["condition"]] + [str(c["counts"][s]) for s in SENSOR_ORDER] + [str(c["total"])]
        cnt_rows.append(row)
        for s in SENSOR_ORDER:
            totals[s] += c["counts"][s]
        grand += c["total"]
    cnt_rows.append(["Total"] + [str(totals[s]) for s in SENSOR_ORDER] + [str(grand)])
    add_table(doc, ["Condition", "current", "sound_vibrometer", "sound_phone", "vibration", "Total"],
              cnt_rows, widths=[1.9, 0.8, 1.3, 1.0, 0.9, 0.6])

    # Figures
    para(doc,
         "Figure 1 illustrates the overall organisation of the repository. "
         "Figures 2\u20134 present representative raw data from one operating point "
         "(normal operation, no reversal, 50 % speed setpoint): the armature "
         "current and its amplitude spectrum, the vibrometer vibration waveform "
         "and its spectrogram, and the trend of the AV-160B spot readings with "
         "speed. The "
         "figures illustrate the types of raw data included in the dataset "
         "without any additional interpretation.")

    if fig_ok.get("fig1"):
        add_figure(doc, FIGDIR / "fig1_organisation.png", width_in=6.4)
    caption(doc,
            "Fig. 1. Organisation of the dataset, showing the top-level files, "
            "the eight operating-condition folders and the four sensor "
            "sub-folders with their file formats.", center=True)

    if fig_ok.get("fig2"):
        add_figure(doc, FIGDIR / "fig2_current.png", width_in=6.4)
    caption(doc,
            "Fig. 2. Representative armature-current recording (normal operation, "
            "no reversal, 50 % speed setpoint): (a) a 60 ms window of the AC-coupled "
            "waveform and (b) its single-sided amplitude spectrum, showing the "
            "300 Hz six-pulse converter ripple and its harmonics.", center=True)

    if fig_ok.get("fig3"):
        add_figure(doc, FIGDIR / "fig3_vibrometer.png", width_in=6.4)
    caption(doc,
            "Fig. 3. Representative vibrometer vibration recording (normal "
            "operation, no reversal, 50 % speed setpoint): (a) a 1 s window of the waveform "
            "and (b) its spectrogram up to 10 kHz.", center=True)

    if fig_ok.get("fig4"):
        add_figure(doc, FIGDIR / "fig4_vibration.png", width_in=6.4)
    caption(doc,
            "Fig. 4. AV-160B vibration spot readings (mean velocity, acceleration "
            "and displacement) as a function of speed setpoint (% of rated speed) "
            "for the normal, no-reversal condition.", center=True)

    # ---- EXPERIMENTAL DESIGN, MATERIALS AND METHODS ---- #
    h1(doc, "EXPERIMENTAL DESIGN, MATERIALS AND METHODS")
    para(doc,
         "Test rig. The brushed PM DC servo motor described in Table 2 was driven "
         "by a four-quadrant thyristor (SCR) converter providing armature voltage "
         "and current control. No external mechanical load was applied — the motor "
         "ran unloaded — and the drive was commanded to a speed setpoint of 1, 2, "
         "5, 10, 20, 30, 40, 50, 60, 70, 80, 90 and 100 % of rated speed (2000 rpm; "
         "a reduced top speed applies to the detuned-control conditions, as noted "
         "below).")
    para(doc,
         "Operating conditions. The speed sweep was repeated for each operating "
         "condition. Normal operation uses the nominal controller tuning. The two "
         "detuned-control conditions use a non-optimal speed-regulator gain "
         "(suboptimal_control) and, additionally, a non-optimal current-regulator "
         "gain (suboptimal_control_rt). The loose-foundation condition uses a "
         "deliberately loosened mechanical foundation. Each condition was recorded "
         "both without and with periodic direction reversal.")
    para(doc,
         "Acquisition (each sensor recorded separately, under the same operating "
         "conditions, not simultaneously). Armature current was captured with a "
         "Rigol MSO5074 oscilloscope and saved as native binary waveforms (.bin); "
         "the sample rate and scaling are stored in each file header. The "
         "vibration waveform was obtained from the 2.0 V AC analog output of an "
         "AV-160B vibrometer external piezoelectric probe and recorded as "
         "44.1 kHz / 16-bit stereo WAV. Vibration spot readings (velocity, "
         "acceleration and displacement per ISO 2954) were logged from the same "
         "AV-160B in display mode to XLS. Airborne sound was recorded with a "
         "budget Android smartphone microphone placed approximately 1 m from the "
         "machine and saved as M4A (AAC).")
    para(doc,
         "Procedure. For each condition and speed setpoint the motor was brought to "
         "steady state, and then each sensor was recorded in turn. The equipment "
         "used is summarised in Table 7.")

    para(doc, "Table 7. Measurement equipment.")
    add_table(doc, ["Equipment", "Model", "Purpose"], [
        ["Brushed PM DC servo motor", "3PI12.12 (625 W, 110 V, 12.5 A, 2000 rpm)", "Machine under test"],
        ["Power converter", "Four-quadrant thyristor (SCR) converter", "Armature voltage/current control drive"],
        ["Oscilloscope", "Rigol MSO5074", "Armature-current waveform acquisition"],
        ["Vibrometer", "AV-160B (Amittari) with piezoelectric probe", "Vibration waveform (AC out) and spot readings"],
        ["Smartphone", "Budget Android phone", "Airborne acoustic acquisition (~1 m)"],
    ], widths=[1.8, 2.6, 1.9])

    para(doc,
         "Curation. Raw files were copied byte-for-byte from the acquisition "
         "folders into a publishable tree with English names and the sortable "
         "speedNNN_sensor.ext scheme, and indexed in metadata.csv (including "
         "sample rate, duration, channels, bit depth, file size and the original "
         "name/path for traceability). No signal transformation was applied. The "
         "complete dataset described in this article has been deposited in the "
         "Mendeley Data repository [4].")

    # ---- LIMITATIONS ---- #
    h1(doc, "LIMITATIONS")
    para(doc,
         "The four sensors were recorded separately under the same operating "
         "conditions rather than simultaneously; recordings are therefore aligned "
         "by operating condition and speed setpoint, not sample-synchronously. The "
         "detuned-control conditions reach only a ~65 % top speed setpoint because "
         "the detuned controller and DC-link protection trip above that speed. The "
         "vibration XLS files are spot readings rather than waveforms, and the "
         "near-zero-speed points are absent where vibration is negligible. The "
         "smartphone audio is lossy AAC and is intended for qualitative use; the "
         "vibrometer WAV is recommended for spectral work. The armature current "
         "is captured with the oscilloscope\u2019s 8-bit ADC, and a few individual "
         "speed points may be missing in a branch. All data come from a single "
         "machine and rig, so the dataset does not capture unit-to-unit or design "
         "variation, and the loose-foundation condition represents one induced "
         "severity. These characteristics should be considered when reusing the "
         "dataset or comparing it with data from other machines or setups.")

    # ---- ETHICS STATEMENT ---- #
    h1(doc, "ETHICS STATEMENT")
    para(doc,
         "The authors confirm that they have read and followed the ethical "
         "requirements for publication in Data in Brief. The current work does "
         "not involve human participants, animal experiments, or any data "
         "collected from social media platforms. The dataset was acquired "
         "exclusively from laboratory experiments on a brushed permanent-magnet "
         "DC servo motor.")

    # ---- CREDIT ---- #
    h1(doc, "CRediT AUTHOR STATEMENT")
    para(doc,
         "Marin Zhilevski: Conceptualization, Methodology, Investigation, "
         "Resources, Data Curation, Writing \u2013 Original Draft, Writing \u2013 Review "
         "& Editing, Supervision. Nikolay Yordanov: Investigation, Data Curation, "
         "Formal Analysis, Visualization, Writing \u2013 Original Draft. Mikho Mikhov: "
         "Conceptualization, Methodology, Resources, Supervision, Writing \u2013 "
         "Review & Editing. Mihriban Gunay: Investigation, Data Curation, "
         "Validation, Writing \u2013 Review & Editing. Merve Ertar\u011f\u0131n: "
         "Investigation, Data Curation, Validation, Writing \u2013 Review & Editing.")

    # ---- ACKNOWLEDGEMENTS ---- #
    h1(doc, "ACKNOWLEDGEMENTS")
    para(doc,
         "The authors would like to thank the Research and Development Sector at "
         "the Technical University of Sofia for the financial support.")

    # ---- DECLARATION ---- #
    h1(doc, "DECLARATION OF COMPETING INTERESTS")
    para(doc,
         "The authors declare that they have no known competing financial "
         "interests or personal relationships that could have appeared to "
         "influence the work reported in this paper.")

    # ---- REFERENCES ---- #
    h1(doc, "REFERENCES")
    refs = [
        "L. Li, S. Liao, B. Zou, J. Liu, Mechanism-based fault diagnosis deep "
        "learning method for permanent magnet synchronous motor, Sensors 24 "
        "(2024) 6349. https://doi.org/10.3390/s24196349.",
        "L. Ding, H. Guo, L. Bian, Convolutional neural networks based on "
        "resonance demodulation of vibration signal for rolling bearing fault "
        "diagnosis in permanent magnet synchronous motors, Energies 17 (2024) "
        "4334. https://doi.org/10.3390/en17174334.",
        "H. Uzel, Y. \u00d6z\u00fcpak, F. Alpsalaz, E. Aslan, I. Zaitsev, "
        "Acoustic-based fault diagnosis of electric motors using Mel spectrograms "
        "and convolutional neural networks, Scientific Reports 16 (2026) 3379. "
        "https://doi.org/10.1038/s41598-025-33269-z.",
        "M. Zhilevski, N. Yordanov, M. Mikhov, M. Ertar\u011f\u0131n, M. Gunay, "
        "Multi-sensor condition-monitoring dataset of a brushed DC servo motor, "
        "Mendeley Data (2026). DOI: to be assigned.",
    ]
    for i, r in enumerate(refs, 1):
        p = doc.add_paragraph()
        p.add_run(f"[{i}] ").bold = True
        p.add_run(r)

    doc.save(str(OUT_DOCX))
    print(f"Saved manuscript: {OUT_DOCX}")


def main():
    stats = compute_stats()

    fig_ok = {}
    # Representative operating point
    cur_bin = DATASET / "data/normal_no_reversal/current/speed050_current.bin"
    wav_file = DATASET / "data/normal_no_reversal/sound_vibrometer/speed050_sound_vibrometer.wav"
    vib_dir = DATASET / "data/normal_no_reversal/vibration"

    try:
        fig1_organisation(FIGDIR / "fig1_organisation.png")
        fig_ok["fig1"] = True
        print("fig1 OK")
    except Exception as e:
        print("fig1 FAILED:", e)

    try:
        fig2_current(FIGDIR / "fig2_current.png", cur_bin)
        fig_ok["fig2"] = True
        print("fig2 OK")
    except Exception as e:
        print("fig2 FAILED:", e)

    try:
        fig3_vibrometer(FIGDIR / "fig3_vibrometer.png", wav_file)
        fig_ok["fig3"] = True
        print("fig3 OK")
    except Exception as e:
        print("fig3 FAILED:", e)

    try:
        fig4_vibration(FIGDIR / "fig4_vibration.png", vib_dir)
        fig_ok["fig4"] = True
        print("fig4 OK")
    except Exception as e:
        print("fig4 FAILED:", e)

    build(stats, fig_ok)


if __name__ == "__main__":
    main()
