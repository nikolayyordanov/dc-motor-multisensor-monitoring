"""Analyze the vibration (.XLS BIFF4) and sound (.wav) folders."""
import os
import glob
import wave
import numpy as np

try:
    import xlrd
except ImportError:
    xlrd = None


def parse_load(name):
    base = os.path.splitext(os.path.basename(name))[0]
    try:
        return int(base)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Vibration .XLS (BIFF4 spot readings)
# --------------------------------------------------------------------------- #
def analyze_vibration(folder):
    print("=" * 70)
    print("VIBRATION  (" + folder + ")")
    print("=" * 70)
    files = sorted(glob.glob(os.path.join(folder, "*.XLS")),
                   key=lambda p: (parse_load(p) is None, parse_load(p)))
    rows = []
    for f in files:
        load = parse_load(f)
        try:
            book = xlrd.open_workbook(f, logfile=open(os.devnull, "w"))
            sh = book.sheet_by_index(0)
        except Exception as e:
            print("  [!] cannot read", f, e)
            continue
        # Columns: Status | No. | Date & Time | Project Name(type) | Value | Unit
        headers = [str(sh.cell_value(0, c)).strip()
                   for c in range(sh.ncols)] if sh.nrows else []
        vals = {"Velocity": [], "Acceleration": [], "Displacement": []}
        for r in range(1, sh.nrows):
            if sh.ncols < 5:
                continue
            qty = str(sh.cell_value(r, 3)).strip()
            val = sh.cell_value(r, 4)
            if qty in vals and isinstance(val, float):
                vals[qty].append(val)
        summ = {}
        for key, lst in vals.items():
            if lst:
                arr = np.array(lst)
                rms = float(np.sqrt((arr ** 2).mean()))
                summ[key] = (arr.mean(), arr.min(), arr.max(), len(arr), rms)
        rows.append((load, os.path.basename(f), sh.nrows, headers, summ))

    for load, fn, nrows, headers, summ in rows:
        print(f"\n-- {fn}  (load {load}%, {nrows} rows) --")
        for key, (mean, lo, hi, n, rms) in summ.items():
            unit = {"Velocity": "mm/s", "Acceleration": "m/s^2",
                    "Displacement": "mm"}[key]
            print(f"   {key:13s}: mean {mean:.4g}  rms {rms:.4g}  "
                  f"(min {lo:.4g}, max {hi:.4g}, n={n}) {unit}")

    # Trend of mean velocity vs load
    print("\n-- Velocity (mean) trend vs load --")
    trend = [(load, summ.get("Velocity", (None,))[0])
             for load, _, _, _, summ in rows if load is not None]
    trend = [(l, v) for l, v in trend if v is not None]
    vmax = max((v for _, v in trend), default=1) or 1
    for l, v in sorted(trend):
        bar = "#" * int(round(v / vmax * 40))
        print(f"   {l:3d}% : {v:7.3f} mm/s  {bar}")
    print("\n-- Acceleration (mean) trend vs load --")
    atrend = [(load, summ.get("Acceleration", (None,))[0])
              for load, _, _, _, summ in rows if load is not None]
    atrend = [(l, v) for l, v in atrend if v is not None]
    amax = max((v for _, v in atrend), default=1) or 1
    for l, v in sorted(atrend):
        bar = "#" * int(round(v / amax * 40))
        print(f"   {l:3d}% : {v:7.3f} m/s^2  {bar}")


# --------------------------------------------------------------------------- #
# Sound .wav (stereo: mic + piezo)
# --------------------------------------------------------------------------- #
def wav_read(path):
    w = wave.open(path, "rb")
    n, ch, sw, fr = (w.getnframes(), w.getnchannels(),
                     w.getsampwidth(), w.getframerate())
    raw = w.readframes(n)
    w.close()
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    data = np.frombuffer(raw, dtype=dtype).astype(float)
    if sw == 2:
        data /= 32768.0
    data = data.reshape(-1, ch)
    return data, fr, ch, sw


def dom_freq(sig, fr, fmin=10):
    sig = sig - sig.mean()
    if sig.size < 16:
        return float("nan")
    win = np.hanning(sig.size)
    spec = np.abs(np.fft.rfft(sig * win))
    freqs = np.fft.rfftfreq(sig.size, 1.0 / fr)
    spec[freqs < fmin] = 0
    return freqs[int(np.argmax(spec))]


def analyze_sound(folder):
    print("\n" + "=" * 70)
    print("SOUND  (" + folder + ")")
    print("=" * 70)
    files = sorted(glob.glob(os.path.join(folder, "*.wav")),
                   key=lambda p: (parse_load(p) is None, parse_load(p)))
    # first, characterise channels on one file
    sample = files[-1]
    data, fr, ch, sw = wav_read(sample)
    print(f"\nFormat (from {os.path.basename(sample)}): "
          f"{ch} ch, {fr} Hz, {sw*8}-bit, {data.shape[0]} frames, "
          f"{data.shape[0]/fr:.2f} s")
    if ch == 2:
        l, r = data[:, 0], data[:, 1]
        corr = np.corrcoef(l, r)[0, 1]
        print(f"L/R correlation: {corr:.3f}  "
              f"(low => the two channels are different signals, "
              f"e.g. mic vs piezo)")
        print(f"L  rms {np.sqrt((l**2).mean()):.4f}  peak {np.abs(l).max():.3f} "
              f" dom {dom_freq(l, fr):.1f} Hz")
        print(f"R  rms {np.sqrt((r**2).mean()):.4f}  peak {np.abs(r).max():.3f} "
              f" dom {dom_freq(r, fr):.1f} Hz")

    print("\n-- Per-load summary (load | ch | RMS | peak | clip% | dom freq) --")
    for f in files:
        load = parse_load(f)
        data, fr, ch, sw = wav_read(f)
        for c in range(ch):
            sig = data[:, c]
            rms = np.sqrt((sig ** 2).mean())
            peak = np.abs(sig).max()
            clip = 100.0 * np.count_nonzero(np.abs(sig) > 0.985) / sig.size
            f0 = dom_freq(sig, fr)
            tag = "mic?" if c == 0 else "piezo?"
            print(f"   {str(load)+'%':>5}  ch{c}({tag:6s}) "
                  f"rms {rms:.4f}  peak {peak:.3f}  "
                  f"clip {clip:5.2f}%  dom {f0:7.1f} Hz")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    if xlrd is None:
        print("xlrd not installed; skipping vibration.")
    else:
        analyze_vibration(os.path.join(here, "вибрации"))
    analyze_sound(os.path.join(here, "звук"))
