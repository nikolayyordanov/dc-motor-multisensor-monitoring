#!/usr/bin/env python3
"""
Analyze Rigol MSO5000-series oscilloscope CSV exports.

The MSO5074 produces two different CSV layouts depending on how you export:

1) "Save Screen"  (e.g. proben0.csv)
   Header:  Time(s),CH1(V)
   Every row carries an explicit time stamp and one (or more) voltage value(s).

2) "Save Memory" (e.g. proben1.csv)
   Header:  CH1(V),t0 = -25s, tInc = 2e-06s,
   Only the voltage samples are stored. The time base is reconstructed from
   the metadata in the header:  t[i] = t0 + i * tInc.
   (Several channels may appear, each followed by its own t0/tInc, or sharing
   a single t0/tInc.)

3) Binary waveform (e.g. RigolDS0.bin)
   Rigol/Agilent-style ".bin" export with an "RG01" magic. A compact binary
   header carries the sample count, X-increment/origin and Y scaling, followed
   by the raw sample buffer (float volts or scaled integer codes). Far smaller
   and more precise than CSV, and it embeds model/serial/date metadata.

4) Native deep-memory waveform (e.g. normal.wfm)
   Rigol MSO5000 ".wfm" export: a 4200-byte proprietary (undocumented) header
   followed by the raw 8-bit ADC codes, one byte per sample. This is the most
   compact way to keep a *full* deep-memory record (e.g. 25 M points in 25 MB
   vs ~380 MB as CSV). The vertical scale (Y increment / LSB) is recovered from
   the header; the horizontal scale is NOT openly documented, so the sample
   rate is ASSUMED from the standard deep-memory setup and can be overridden
   with the WFM_FS environment variable (samples per second).

Usage:
    python analyze_rigol.py                  # analyze the default CSV files
    python analyze_rigol.py file1.csv ...    # analyze the given file(s)
    python analyze_rigol.py RigolDS0.bin     # analyze a binary export
    python analyze_rigol.py normal.wfm       # analyze a deep-memory .wfm
"""

from __future__ import annotations

import os
import re
import struct
import sys

import numpy as np


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def eng(value: float, unit: str = "") -> str:
    """Format a number with an engineering (SI) prefix."""
    if value == 0 or not np.isfinite(value):
        return f"{value:g} {unit}".strip()
    prefixes = {
        -15: "f", -12: "p", -9: "n", -6: "u", -3: "m",
        0: "", 3: "k", 6: "M", 9: "G", 12: "T",
    }
    exp = int(np.floor(np.log10(abs(value)) / 3) * 3)
    exp = max(min(exp, 12), -15)
    scaled = value / (10 ** exp)
    return f"{scaled:.4g} {prefixes[exp]}{unit}".strip()


def parse_seconds(text: str) -> float:
    """Parse a value like '-25s', '2e-06s', '500ms', '2us' into seconds."""
    text = text.strip()
    m = re.match(
        r"^([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*([afpnumkM]?)s?$", text
    )
    if not m:
        return float(text.rstrip("s"))
    num = float(m.group(1))
    factor = {
        "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
        "": 1.0, "k": 1e3, "M": 1e6,
    }[m.group(2)]
    return num * factor


# --------------------------------------------------------------------------- #
# Format detection / loading
# --------------------------------------------------------------------------- #
def load_csv(path: str):
    """
    Return (mode, time_array, {channel_name: voltage_array}, meta_dict).
    mode is 'screen' or 'memory'.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline().strip()

    fields = [f.strip() for f in header.split(",")]
    lower = header.lower()

    # ---- Save-Screen layout: first column is an explicit time axis -------- #
    if fields and fields[0].lower().startswith("time"):
        ncols = len(fields)
        data = np.loadtxt(
            path, delimiter=",", skiprows=1, dtype=float,
            usecols=range(ncols), ndmin=2,
        )
        time = data[:, 0]
        channels = {}
        for idx in range(1, data.shape[1]):
            name = fields[idx] if idx < len(fields) else f"col{idx}(V)"
            channels[name] = data[:, idx]
        return "screen", time, channels, {"header": header}

    # ---- Save-Memory layout: header carries t0 / tInc --------------------- #
    # Examples:
    #   CH1(V),t0 = -25s, tInc = 2e-06s,
    #   CH1(V),CH2(V),Start,Increment            (older firmware)
    t0_match = re.search(r"t0\s*=\s*([^\s,]+)", header, re.IGNORECASE)
    tinc_match = re.search(r"tinc\s*=\s*([^\s,]+)", header, re.IGNORECASE)
    start_match = re.search(r"start\s*=\s*([^\s,]+)", header, re.IGNORECASE)
    inc_match = re.search(r"increment\s*=\s*([^\s,]+)", header, re.IGNORECASE)

    t0 = parse_seconds((t0_match or start_match).group(1)) \
        if (t0_match or start_match) else 0.0
    tinc_token = tinc_match or inc_match
    tinc = parse_seconds(tinc_token.group(1)) if tinc_token else None

    # voltage channel names = header fields that look like a channel
    chan_names = [f for f in fields
                  if re.match(r".+\(.+\)", f) and "t0" not in f.lower()
                  and "tinc" not in f.lower()]
    if not chan_names:
        chan_names = ["CH1(V)"]

    # Load the numeric columns (ignore trailing empty fields produced by
    # the trailing comma in the Rigol export).
    data = np.loadtxt(
        path, delimiter=",", skiprows=1, dtype=float,
        usecols=range(len(chan_names)), ndmin=2,
    )

    n = data.shape[0]
    if tinc is None:                              # fall back if missing
        tinc = 1.0
    time = t0 + np.arange(n) * tinc

    channels = {}
    for idx, name in enumerate(chan_names):
        channels[name] = data[:, idx]

    meta = {"header": header, "t0": t0, "tInc": tinc}
    return "memory", time, channels, meta


# --------------------------------------------------------------------------- #
# Binary loader (Rigol/Agilent "RG01" .bin waveform format)
# --------------------------------------------------------------------------- #
_X_UNITS = {0: "unknown", 1: "V", 2: "s", 3: "Hz"}
_Y_UNITS = {0: "unknown", 1: "V", 2: "s", 3: "Hz"}


def _cstr(raw: bytes) -> str:
    """Decode a NUL-padded fixed-width byte field to a clean string."""
    return raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()


def load_rigol_bin(path: str):
    """
    Parse a Rigol/Agilent-style binary waveform file ("RG01"/"AG01" magic).

    Returns (mode, time, {channel: volts}, meta) just like load_csv().
    Layout (little-endian):
      File header  : cookie[2] version[2] file_size(i) n_waveforms(i)
      For each waveform:
        Waveform header: header_size(i) wtype(i) n_buffers(i) points(i)
            count(i) x_disp_range(f) x_disp_origin(d) x_increment(d)
            x_origin(d) x_units(i) y_units(i) date[16] time[16] frame[24]
            label[16] time_tag(d) segment_index(I)
        For each buffer:
            Buffer header: header_size(i) buf_type(h) bytes_per_point(h)
                buffer_size(i)
            Raw samples (float32 volts, or int8/int16 codes).
    """
    with open(path, "rb") as fh:
        data = fh.read()

    cookie = data[0:2]
    if cookie not in (b"RG", b"AG"):
        raise ValueError(f"Not a Rigol/Agilent binary file (magic={cookie!r})")
    version = _cstr(data[2:4])
    file_size, n_waveforms = struct.unpack_from("<ii", data, 4)

    off = 12
    channels: dict[str, np.ndarray] = {}
    time = None
    x_inc = x_orig = None
    wmeta: dict = {}

    for _ in range(max(n_waveforms, 1)):
        wh_size = struct.unpack_from("<i", data, off)[0]
        wh = data[off:off + wh_size]
        (_hsize, wtype, n_buffers, points, _count) = struct.unpack_from(
            "<iiiii", wh, 0)
        x_inc, x_orig = struct.unpack_from("<dd", wh, 32)
        x_units, y_units = struct.unpack_from("<ii", wh, 48)
        date = _cstr(wh[56:72])
        tstr = _cstr(wh[72:88])
        frame = _cstr(wh[88:112])
        label = _cstr(wh[112:128]) or "CH1"
        wmeta = {"date": date, "time": tstr, "frame": frame,
                 "x_units": _X_UNITS.get(x_units, str(x_units)),
                 "y_units": _Y_UNITS.get(y_units, str(y_units))}
        off += wh_size

        for b in range(max(n_buffers, 1)):
            bh_size = struct.unpack_from("<i", data, off)[0]
            buf_type, bytes_per_point = struct.unpack_from("<hh", data, off + 4)
            buf_size = struct.unpack_from("<i", data, off + 8)[0]
            payload = data[off + bh_size: off + bh_size + buf_size]

            if bytes_per_point == 4:
                samples = np.frombuffer(payload, dtype="<f4").astype(float)
            elif bytes_per_point == 8:
                samples = np.frombuffer(payload, dtype="<f8").astype(float)
            elif bytes_per_point == 2:
                samples = np.frombuffer(payload, dtype="<i2").astype(float)
            else:  # 1 byte/point
                samples = np.frombuffer(payload, dtype=np.uint8).astype(float)

            yunit = wmeta["y_units"]
            name = f"{label}({yunit})" if not label.endswith(")") else label
            if max(n_buffers, 1) > 1:
                name = f"{label}_buf{b}({yunit})"
            channels[name] = samples
            off += bh_size + buf_size

    n = len(next(iter(channels.values()))) if channels else 0
    if x_inc is None or x_inc == 0:
        x_inc = 1.0
    time = (x_orig or 0.0) + np.arange(n) * x_inc

    meta = {
        "header": f"RG{version} binary, {n_waveforms} waveform(s), "
                  f"xInc={x_inc:g}s",
        "tInc": x_inc,
        "file_size": file_size,
        **wmeta,
    }
    return "binary", time, channels, meta


# Rigol MSO5000 ".wfm" deep-memory export layout.
_WFM_HEADER_BYTES = 4200          # fixed proprietary header
_WFM_YINC_OFFSETS = (633, 757, 881, 1005)   # per-channel Y increment (double)
_WFM_ASSUMED_FS = 500_000.0       # 25 M-pt / 50 s deep-memory default


def load_rigol_wfm(path: str):
    """
    Parse a Rigol MSO5000-series native ".wfm" deep-memory export.

    Returns (mode, time, {channel: volts}, meta) like the other loaders.

    The file is a fixed 4200-byte header followed by the raw 8-bit ADC codes,
    one unsigned byte per sample. The vertical scale (Y increment = LSB, in
    volts/code) is read from the header. The absolute vertical OFFSET and the
    horizontal (time) scale are not openly documented, so:
      * voltages are reported relative to code 0 (LSB and peak-to-peak are
        exact; the DC offset is NOT decoded), and
      * the sample rate is ASSUMED (``_WFM_ASSUMED_FS``; override via the
        WFM_FS environment variable) and flagged as such in the report.
    """
    file_size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(_WFM_HEADER_BYTES)

    # Y increment (volts per code). The same value is stored once per channel;
    # take the median of the candidate slots for robustness.
    yincs = []
    for o in _WFM_YINC_OFFSETS:
        if o + 8 <= len(head):
            v = struct.unpack_from("<d", head, o)[0]
            if 1e-9 < abs(v) < 1.0:
                yincs.append(v)
    y_inc = float(np.median(yincs)) if yincs else 1.0

    codes = np.fromfile(path, dtype=np.uint8, offset=_WFM_HEADER_BYTES)
    n = codes.size

    # Rail occupancy on the raw codes.
    n_low = int(np.count_nonzero(codes == 0))
    n_high = int(np.count_nonzero(codes == 255))

    # Distinguish an intentional ZERO-CURRENT BASELINE (a contiguous block of
    # code 0 while the motor is off — expected for a unipolar DC signal placed
    # at the bottom of the screen) from genuine CLIPPING of a live signal
    # (code-0 samples scattered through the running record).
    #
    # Strategy: find the longest contiguous run of code 0. If most of the
    # code-0 samples live in that single run, it is a baseline, not clipping;
    # confirm by checking that the rest of the record keeps clear headroom
    # above the bottom rail (1st percentile well above code 0).
    base_run = base_start = base_end = 0
    headroom_pct1 = None
    if n_low:
        is0 = (codes == 0).astype(np.int8)
        edges = np.diff(np.concatenate(([0], is0, [0])))
        run_starts = np.flatnonzero(edges == 1)
        run_ends = np.flatnonzero(edges == -1)
        run_lens = run_ends - run_starts
        k = int(np.argmax(run_lens))
        base_run = int(run_lens[k])
        base_start, base_end = int(run_starts[k]), int(run_ends[k])
        # codes outside the longest zero run
        mask = np.ones(n, dtype=bool)
        mask[base_start:base_end] = False
        rest = codes[mask]
        if rest.size:
            headroom_pct1 = int(np.percentile(rest, 1))
    frac_in_run = base_run / n_low if n_low else 0.0
    # Baseline (not clipping) when the zero samples are essentially one block
    # AND the running signal stays clear of the rail.
    zero_is_baseline = (
        n_low > 0
        and frac_in_run > 0.98
        and (headroom_pct1 is None or headroom_pct1 >= 4)
    )

    # Volts relative to code 0 (offset not decoded -> DC level is arbitrary).
    volts = codes.astype(float) * y_inc

    # Assumed sample rate (overridable).
    fs = float(os.environ.get("WFM_FS", _WFM_ASSUMED_FS))
    t_inc = 1.0 / fs if fs > 0 else 1.0
    time = np.arange(n) * t_inc

    meta = {
        "header": f"Rigol .wfm, {_WFM_HEADER_BYTES}-byte header, "
                  f"{n:,} x 8-bit codes, LSB={eng(y_inc, 'V')}",
        "tInc": t_inc,
        "tInc_assumed": True,
        "file_size": file_size,
        "y_inc": y_inc,
        "y_offset_decoded": False,
        "clip_low": n_low,
        "clip_high": n_high,
        "clip_low_pct": 100.0 * n_low / n if n else 0.0,
        "clip_high_pct": 100.0 * n_high / n if n else 0.0,
        "zero_is_baseline": zero_is_baseline,
        "base_run": base_run,
        "base_start": base_start,
        "base_end": base_end,
        "base_run_pct": 100.0 * base_run / n if n else 0.0,
        "headroom_pct1_code": headroom_pct1,
    }
    return "wfm", time, {"CH1(V)": volts}, meta


def load_file(path: str):
    """Dispatch to the binary or CSV loader based on magic / extension."""
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if path.lower().endswith(".wfm"):
        return load_rigol_wfm(path)
    if magic in (b"RG", b"AG") or path.lower().endswith(".bin"):
        return load_rigol_bin(path)
    return load_csv(path)


# --------------------------------------------------------------------------- #
# Analysis / reporting
# --------------------------------------------------------------------------- #
def analyze(path: str) -> None:
    if not os.path.exists(path):
        print(f"\n[!] File not found: {path}")
        return

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print("\n" + "=" * 70)
    print(f"FILE: {path}    ({size_mb:.2f} MB)")
    print("=" * 70)

    mode, time, channels, meta = load_file(path)

    export_kind = {
        "screen": "Save Screen (explicit time column)",
        "memory": "Save Memory (reconstructed time base)",
        "binary": "Binary waveform (RG01 .bin)",
        "wfm": "Native deep-memory waveform (.wfm, 8-bit codes)",
    }.get(mode, mode)
    print(f"Export type      : {export_kind}")
    print(f"Raw header       : {meta['header']}")
    if mode == "binary":
        if meta.get("frame"):
            print(f"Instrument       : {meta['frame']}")
        if meta.get("date") or meta.get("time"):
            print(f"Captured         : {meta.get('date', '')} "
                  f"{meta.get('time', '')}".strip())
    if mode == "wfm":
        clip_lo = meta.get("clip_low_pct", 0.0)
        clip_hi = meta.get("clip_high_pct", 0.0)
        if meta.get("zero_is_baseline"):
            t_inc = meta.get("tInc", 0.0)
            t0 = meta["base_start"] * t_inc
            t1 = meta["base_end"] * t_inc
            print(f"[i] Zero-current baseline (code 0) for "
                  f"{meta['base_run_pct']:.1f}% of the record "
                  f"(~{t0:.1f}-{t1:.1f} s, assumed rate).")
            print("    This looks INTENTIONAL: a unipolar DC signal sitting at "
                  "the bottom of the\n    screen while the motor is off — NOT "
                  "clipping. The running portion keeps")
            hp = meta.get("headroom_pct1_code")
            if hp is not None:
                print(f"    clear headroom above the rail (1st-pct = code "
                      f"{hp} of 255).")
            print("    Tip: analyse only the running window so the long flat "
                  "baseline doesn't\n    dominate the FFT.")
        elif clip_lo > 0.05 or clip_hi > 0.05:
            print("[!] CLIPPING DETECTED — the signal is railed against the "
                  "ADC limit:")
            if clip_lo > 0.05:
                print(f"    bottom rail (code 0)  : {meta['clip_low']:,} "
                      f"samples ({clip_lo:.2f}%)")
            if clip_hi > 0.05:
                print(f"    top rail (code 255)   : {meta['clip_high']:,} "
                      f"samples ({clip_hi:.2f}%)")
            print("    -> the true peak is unknown there; re-capture with more "
                  "vertical range/offset.")
        if not meta.get("y_offset_decoded", True):
            print("(Vertical OFFSET is not decoded from the .wfm header, so the "
                  "DC level below is\n relative to code 0; LSB and "
                  "peak-to-peak are exact.)")

    n = len(time)
    t_start, t_end = float(time[0]), float(time[-1])
    duration = t_end - t_start

    # Sample interval / rate.
    #
    # Save Memory / Binary: tInc (xInc) from the header is exact and
    # authoritative.
    #
    # Save Screen: the Time column is rounded to ~5 significant figures, so
    # several consecutive rows share the same timestamp. Taking the median of
    # timestamp differences therefore UNDER-estimates the rate (it returns the
    # rounding step, not the true interval). The reliable figure is
    # points / duration, which we use as the true rate.
    if mode in ("memory", "binary"):
        dt = meta["tInc"]
        dt_rounded = None
    elif mode == "wfm":
        dt = meta["tInc"]          # ASSUMED rate (see note below)
        dt_rounded = None
    else:
        dt = duration / (n - 1) if n > 1 else float("nan")  # true interval
        diffs = np.diff(time)
        diffs = diffs[diffs > 0]
        dt_rounded = float(np.median(diffs)) if diffs.size else None

    fs = 1.0 / dt if dt and np.isfinite(dt) and dt > 0 else float("nan")

    print("\n-- Time base ---------------------------------------------------")
    print(f"Samples          : {n:,}")
    print(f"Start time       : {eng(t_start, 's')}   ({t_start:.6e} s)")
    print(f"End time         : {eng(t_end, 's')}   ({t_end:.6e} s)")
    print(f"Total duration   : {eng(duration, 's')}   ({duration:.6e} s)")
    print(f"Sample interval  : {eng(dt, 's')}   ({dt:.6e} s)")
    print(f"Sample rate      : {eng(fs, 'Sa/s')}   ({fs:.6e} Sa/s)")
    if mode == "wfm" and meta.get("tInc_assumed"):
        print("(*** ASSUMED sample rate *** — the .wfm horizontal scale is not "
              "openly\n documented. Override with the WFM_FS environment "
              "variable, e.g. WFM_FS=500000.\n Time-base and dominant-frequency "
              "figures below depend on this assumption;\n the voltage, LSB and "
              "clipping figures do not.)")
    if mode == "screen":
        print("(rate derived from points/duration; the Time column is rounded")
        if dt_rounded:
            fs_rounded = 1.0 / dt_rounded
            uniq = len(np.unique(time))
            print(f" to ~5 sig figs, so timestamps repeat — {uniq:,} of {n:,} "
                  f"are distinct.")
            print(f" Naive median-of-timestamps would misreport "
                  f"{eng(fs_rounded, 'Sa/s')}.)")
        else:
            print(" to ~5 sig figs, so raw timestamps may repeat.)")

    # Per-channel signal statistics.
    for name, v in channels.items():
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        vmin, vmax = float(v.min()), float(v.max())
        vpp = vmax - vmin
        vmean = float(v.mean())
        vrms = float(np.sqrt(np.mean(v ** 2)))
        vstd = float(v.std())

        print(f"\n-- {name} -----------------------------------------------")
        print(f"Min              : {eng(vmin, 'V')}")
        print(f"Max              : {eng(vmax, 'V')}")
        print(f"Peak-to-peak     : {eng(vpp, 'V')}")
        print(f"Mean (DC offset) : {eng(vmean, 'V')}")
        print(f"RMS              : {eng(vrms, 'V')}")
        print(f"Std deviation    : {eng(vstd, 'V')}")

        # Amplitude quantization: distinct levels and the ADC step (LSB).
        levels = np.unique(v)
        if 1 < levels.size <= 5000:
            steps = np.diff(levels)
            steps = steps[steps > 1e-12]
            lsb = float(steps.min()) if steps.size else float("nan")
            eff_bits = np.log2(vpp / lsb) if lsb and lsb > 0 else float("nan")
            print(f"Distinct levels  : {levels.size}")
            print(f"Quantization LSB : {eng(lsb, 'V')} "
                  f"(~{eff_bits:.1f} effective bits over p-p)")

        # Dominant frequency via FFT (AC component only).
        if np.isfinite(fs) and v.size >= 8:
            ac = v - vmean
            spectrum = np.abs(np.fft.rfft(ac))
            freqs = np.fft.rfftfreq(v.size, d=dt)
            if spectrum.size > 1:
                peak = int(np.argmax(spectrum[1:]) + 1)
                f0 = freqs[peak]
                print(f"Dominant freq    : {eng(f0, 'Hz')} "
                      f"(period {eng(1 / f0, 's') if f0 else 'n/a'})")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        here = os.path.dirname(os.path.abspath(__file__))
        args = [os.path.join(here, "proben0.csv"),
                os.path.join(here, "proben1.csv")]
    for path in args:
        analyze(path)
    print()


if __name__ == "__main__":
    main()
