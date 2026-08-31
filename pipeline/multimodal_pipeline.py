"""Multi-modal dual-task pipeline for the DC servo-motor condition-monitoring dataset.

Task 1 (classification): 8 operating conditions (condition x reversal folders).
Task 2 (regression):     commanded speed setpoint, 1..100 % of rated speed.

Modalities (recorded separately at identical operating states, aligned by
``(condition, speed_percent)``):

    sound_vibrometer  .wav  44.1 kHz 16-bit stereo   -> log-Mel spectrogram -> 2D CNN
    sound_phone       .m4a  lossy AAC                -> log-Mel spectrogram -> 2D CNN
    current           .bin  Rigol MSO5074 ('RG01')   -> log Welch PSD       -> 1D CNN
    vibration         .xls  AV-160B spot readings    -> tabular vector      -> MLP

Fusion is a masked gated-attention pool over the four modality embeddings, so
missing modalities are handled by excluding them from the attention softmax
(no zero-padding bias) and the learned attention weights double as an
interpretable per-modality importance score.

Usage
-----
    python pipeline/multimodal_pipeline.py --stage all
    python pipeline/multimodal_pipeline.py --stage cache          # build feature cache only
    python pipeline/multimodal_pipeline.py --stage eval           # evaluate existing checkpoint

Splits are made with ``GroupShuffleSplit`` over ``(condition, speed_percent)``
recordings, so windows cut from the same recording never straddle the
train/test boundary.
"""

from __future__ import annotations

import argparse
import json
import struct
import warnings
from dataclasses import dataclass, asdict, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.signal import resample_poly, welch
from sklearn.metrics import (
    accuracy_score,
    auc,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import label_binarize
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings("ignore", category=UserWarning)

MODALITIES = ("sound_vibrometer", "sound_phone", "current", "vibration")
MODALITY_LABELS = ("Vibrometer audio\n(WAV)", "Phone audio\n(M4A)", "Armature current\n(BIN)", "Vibration spots\n(XLS)")
VIB_METRICS = ("Velocity", "Acceleration", "Displacement")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    root: Path = Path("DCData_mendeley")
    out_dir: Path = Path("pipeline_outputs/multimodal")

    # windowing
    window_s: float = 1.0
    n_windows: int = 8
    skip_head_s: float = 1.0  # discard transient at the start of each capture
    usable_s: float = 17.0

    # audio front end
    audio_fs: int = 16_000
    n_fft: int = 1024
    hop_length: int = 256
    n_mels: int = 64
    mel_frames: int = 64

    # current front end
    current_fs: int = 50_000
    psd_bins: int = 512
    psd_fmax: float = 5_000.0

    # model / optimisation
    embed_dim: int = 128
    dropout: float = 0.3
    modality_dropout: float = 0.15
    batch_size: int = 32
    epochs: int = 60
    lr: float = 1e-3
    weight_decay: float = 1e-4
    reg_loss_weight: float = 5.0
    test_size: float = 0.25
    val_size: float = 0.15
    seed: int = 1337
    num_workers: int = 0

    class_names: list[str] = field(default_factory=list)

    @property
    def cache_file(self) -> Path:
        return self.out_dir / "feature_cache.npz"

    @property
    def ckpt_file(self) -> Path:
        return self.out_dir / "model.pt"

    @property
    def fig_dir(self) -> Path:
        return self.out_dir / "figures"

    @property
    def table_dir(self) -> Path:
        return self.out_dir / "tables"


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# --------------------------------------------------------------------------- #
# Raw readers -- one per modality
# --------------------------------------------------------------------------- #
def load_wav_segment(path: Path, offset_s: float, dur_s: float, target_fs: int) -> np.ndarray:
    """Stereo 44.1 kHz vibrometer WAV -> mono float32 at ``target_fs`` (soundfile)."""
    with sf.SoundFile(str(path)) as fh:
        fs = int(fh.samplerate)
        fh.seek(int(offset_s * fs))
        sig = fh.read(frames=int(round(dur_s * fs)), dtype="float32", always_2d=True)
    if sig.size == 0:
        return np.zeros(0, dtype=np.float32)
    sig = sig.mean(axis=1)
    if fs != target_fs:
        sig = resample_poly(sig, target_fs, fs)
    return np.asarray(sig, dtype=np.float32)


def load_m4a_segment(path: Path, offset_s: float, dur_s: float, target_fs: int) -> np.ndarray:
    """Lossy AAC phone recording -> mono float32 at ``target_fs``.

    ``librosa.load`` delegates to libsndfile, which has no AAC decoder (the
    ``audioread`` fallback was removed in librosa 1.0), so the container is
    decoded and resampled with PyAV/FFmpeg first; librosa is still used for the
    Mel front end downstream.
    """
    import av

    chunks: list[np.ndarray] = []
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=int(target_fs))
        for frame in container.decode(stream):
            out = resampler.resample(frame)
            for f in out if isinstance(out, list) else [out]:
                if f is not None:
                    chunks.append(f.to_ndarray().reshape(-1))
        flushed = resampler.resample(None)
        for f in flushed if isinstance(flushed, list) else [flushed]:
            if f is not None:
                chunks.append(f.to_ndarray().reshape(-1))

    if not chunks:
        return np.zeros(0, dtype=np.float32)

    sig = np.concatenate(chunks).astype(np.float32)
    start = int(max(0.0, offset_s) * target_fs)
    return sig[start: start + int(round(dur_s * target_fs))]


def parse_rigol_bin(path: Path, offset_s: float, dur_s: float, target_fs: int) -> np.ndarray:
    """Parse a Rigol MSO5074 native binary waveform ('RG01'/'AG' magic).

    Layout: ``file header`` (magic + sizes) -> ``waveform header`` (contains the
    x-increment, i.e. 1/fs) -> ``buffer header`` (bytes-per-point, buffer size)
    -> raw ADC payload (8-bit for this dataset).  Only the requested window is
    read from disk, so the 80 MB captures never have to be loaded in full.
    """
    with path.open("rb") as fh:
        head = fh.read(64)
        if head[:2] not in (b"RG", b"AG"):
            raise ValueError(f"{path.name}: not a Rigol RG/AG binary waveform")

        off = 12
        wh_size = struct.unpack_from("<i", head, off)[0]
        fh.seek(off)
        wave_header = fh.read(wh_size)
        x_inc = struct.unpack_from("<d", wave_header, 32)[0]
        fs = 1.0 / x_inc if x_inc > 0 else 1_000_000.0

        off += wh_size
        fh.seek(off)
        buf_header = fh.read(12)
        bh_size = struct.unpack_from("<i", buf_header, 0)[0]
        _buf_type, bytes_per_point = struct.unpack_from("<hh", buf_header, 4)
        buf_size = struct.unpack_from("<i", buf_header, 8)[0]

        dtype = {1: np.uint8, 2: np.int16, 4: np.float32, 8: np.float64}.get(bytes_per_point)
        if dtype is None:
            raise ValueError(f"{path.name}: unsupported bytes-per-point {bytes_per_point}")

        n_samples = int(buf_size // bytes_per_point)
        start = int(max(0.0, offset_s) * fs)
        stop = int(min(n_samples, start + round(dur_s * fs)))
        if stop <= start:
            return np.zeros(0, dtype=np.float32)

        itemsize = np.dtype(dtype).itemsize
        fh.seek(off + bh_size + start * itemsize)
        raw = fh.read((stop - start) * itemsize)

    sig = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    sig -= sig.mean()  # 8-bit ADC codes are unipolar: remove the DC pedestal
    if int(fs) != target_fs:
        sig = resample_poly(sig, target_fs, int(fs))
    return np.asarray(sig, dtype=np.float32)


def load_vibration_xls(path: Path) -> np.ndarray:
    """AV-160B spot readings (.xls) -> [mean, std, min, max] per ISO 2954 metric."""
    df = pd.read_excel(path, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    metric_col = next(c for c in df.columns if "project" in c.lower())
    value_col = next(c for c in df.columns if "value" in c.lower())

    feats: list[float] = []
    for metric in VIB_METRICS:
        vals = pd.to_numeric(df.loc[df[metric_col].astype(str).str.strip() == metric, value_col], errors="coerce")
        vals = vals.dropna().to_numpy(dtype=np.float64)
        if vals.size == 0:
            feats.extend([0.0, 0.0, 0.0, 0.0])
        else:
            feats.extend([vals.mean(), vals.std(), vals.min(), vals.max()])
    return np.asarray(feats, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Feature transforms
# --------------------------------------------------------------------------- #
def log_mel(sig: np.ndarray, cfg: Config) -> np.ndarray:
    """Per-sample normalised log-Mel spectrogram, shape ``(n_mels, mel_frames)``."""
    import librosa

    need = int(cfg.window_s * cfg.audio_fs)
    if sig.size < need:
        sig = np.pad(sig, (0, need - sig.size))
    sig = sig[:need]

    mel = librosa.feature.melspectrogram(
        y=sig, sr=cfg.audio_fs, n_fft=cfg.n_fft, hop_length=cfg.hop_length, n_mels=cfg.n_mels, power=2.0
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)

    if mel_db.shape[1] < cfg.mel_frames:
        mel_db = np.pad(mel_db, ((0, 0), (0, cfg.mel_frames - mel_db.shape[1])), mode="edge")
    mel_db = mel_db[:, : cfg.mel_frames]
    return ((mel_db - mel_db.mean()) / (mel_db.std() + 1e-6)).astype(np.float32)


def log_psd(sig: np.ndarray, cfg: Config) -> np.ndarray:
    """Log Welch power spectral density of the armature current, ``psd_bins`` long."""
    need = int(cfg.window_s * cfg.current_fs)
    if sig.size < need:
        sig = np.pad(sig, (0, need - sig.size))
    sig = sig[:need]

    freqs, pxx = welch(sig, fs=cfg.current_fs, nperseg=min(4096, sig.size), noverlap=None, scaling="density")
    keep = freqs <= cfg.psd_fmax
    freqs, pxx = freqs[keep], pxx[keep]

    grid = np.linspace(0.0, cfg.psd_fmax, cfg.psd_bins)
    spec = np.interp(grid, freqs, 10.0 * np.log10(pxx + 1e-20))
    return ((spec - spec.mean()) / (spec.std() + 1e-6)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Cache construction: metadata -> aligned 4-modality windowed samples
# --------------------------------------------------------------------------- #
def _window_offsets(cfg: Config) -> np.ndarray:
    span = max(cfg.usable_s - cfg.window_s, cfg.window_s)
    return np.linspace(0.0, span, cfg.n_windows, endpoint=False)


def build_cache(cfg: Config) -> dict[str, np.ndarray]:
    """Read ``metadata.csv``, align modalities on (condition, speed_percent) and
    materialise every window as a fixed-shape feature tensor.

    Each recording is decoded exactly once (the whole usable span) and then
    sliced into windows, which avoids re-decoding the M4A/BIN captures ``n_windows``
    times.
    """
    meta = pd.read_csv(cfg.root / "metadata.csv")
    meta = meta[meta["condition"].notna() & meta["speed_percent"].notna()].copy()
    meta["speed_percent"] = meta["speed_percent"].astype(int)

    class_names = sorted(meta["condition"].unique())
    cfg.class_names = class_names
    class_to_idx = {c: i for i, c in enumerate(class_names)}

    offsets = _window_offsets(cfg)
    groups = meta.groupby(["condition", "speed_percent"], sort=True)

    mel_vib, mel_phone, cur_psd, vib_tab = [], [], [], []
    masks, y_cls, y_reg, group_ids, speeds = [], [], [], [], []
    failures: list[tuple[str, str]] = []

    readers = (
        ("sound_vibrometer", load_wav_segment, log_mel, cfg.audio_fs),
        ("sound_phone", load_m4a_segment, log_mel, cfg.audio_fs),
        ("current", parse_rigol_bin, log_psd, cfg.current_fs),
    )

    for gid, ((condition, speed), rows) in enumerate(groups):
        paths = {r["sensor"]: cfg.root / r["new_path"] for _, r in rows.iterrows() if r["sensor"] in MODALITIES}

        # tabular spot readings are per-recording, not per-window
        vib_vec = np.zeros(len(VIB_METRICS) * 4, dtype=np.float32)
        vib_ok = False
        if "vibration" in paths and paths["vibration"].exists():
            try:
                vib_vec, vib_ok = load_vibration_xls(paths["vibration"]), True
            except Exception as exc:  # noqa: BLE001 - degrade to "missing modality"
                failures.append((str(paths["vibration"]), repr(exc)))

        # decode each waveform modality once
        signals: dict[str, np.ndarray] = {}
        for name, reader, _transform, fs in readers:
            path = paths.get(name)
            if path is None or not path.exists():
                continue
            try:
                sig = reader(path, cfg.skip_head_s, cfg.usable_s, fs)
                if sig.size:
                    signals[name] = sig
            except Exception as exc:  # noqa: BLE001
                failures.append((str(path), repr(exc)))

        for offset in offsets:
            feats = {
                "sound_vibrometer": np.zeros((cfg.n_mels, cfg.mel_frames), dtype=np.float32),
                "sound_phone": np.zeros((cfg.n_mels, cfg.mel_frames), dtype=np.float32),
                "current": np.zeros(cfg.psd_bins, dtype=np.float32),
            }
            mask = np.zeros(len(MODALITIES), dtype=np.float32)

            for name, _reader, transform, fs in readers:
                sig = signals.get(name)
                if sig is None:
                    continue
                start = int(offset * fs)
                chunk = sig[start: start + int(cfg.window_s * fs)]
                if chunk.size < int(0.5 * cfg.window_s * fs):
                    continue
                feats[name] = transform(chunk, cfg)
                mask[MODALITIES.index(name)] = 1.0

            mask[MODALITIES.index("vibration")] = float(vib_ok)
            if mask.sum() == 0:
                continue

            mel_vib.append(feats["sound_vibrometer"])
            mel_phone.append(feats["sound_phone"])
            cur_psd.append(feats["current"])
            vib_tab.append(vib_vec)
            masks.append(mask)
            y_cls.append(class_to_idx[condition])
            y_reg.append(float(speed))
            group_ids.append(gid)
            speeds.append(int(speed))

        print(f"  [{gid + 1:>3}] {condition:<36} speed={speed:>3}%  modalities={sorted(paths)}")

    cache = {
        "mel_vib": np.stack(mel_vib),
        "mel_phone": np.stack(mel_phone),
        "current": np.stack(cur_psd),
        "vibration": np.stack(vib_tab),
        "mask": np.stack(masks),
        "y_cls": np.asarray(y_cls, dtype=np.int64),
        "y_reg": np.asarray(y_reg, dtype=np.float32),
        "group": np.asarray(group_ids, dtype=np.int64),
        "speed": np.asarray(speeds, dtype=np.int64),
        "class_names": np.asarray(class_names),
    }

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cfg.cache_file, **cache)
    if failures:
        pd.DataFrame(failures, columns=["path", "error"]).to_csv(cfg.out_dir / "load_failures.csv", index=False)
        print(f"\n{len(failures)} file(s) could not be read -> treated as missing modalities "
              f"(see {cfg.out_dir / 'load_failures.csv'})")

    n, m = cache["mask"].shape
    print(f"\nCached {n} windowed samples over {len(set(group_ids))} recordings, {len(class_names)} classes.")
    for i in range(m):
        print(f"  modality coverage  {MODALITIES[i]:<18} {cache['mask'][:, i].mean() * 100:5.1f} %")
    return cache


def load_cache(cfg: Config) -> dict[str, np.ndarray]:
    if not cfg.cache_file.exists():
        raise FileNotFoundError(f"{cfg.cache_file} not found - run with --stage cache first")
    with np.load(cfg.cache_file, allow_pickle=False) as data:
        cache = {k: data[k] for k in data.files}
    cfg.class_names = [str(c) for c in cache["class_names"]]
    return cache


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
class DCMotorMultiModalDataset(Dataset):
    """Yields one aligned 4-modality sample plus its availability mask.

    ``modality_dropout`` randomly hides available modalities during training so
    the fusion head cannot collapse onto a single sensor and stays robust to the
    missing-modality pattern present in the raw dataset.
    """

    def __init__(
        self,
        cache: dict[str, np.ndarray],
        indices: np.ndarray,
        stats: dict[str, tuple[np.ndarray, np.ndarray]],
        modality_dropout: float = 0.0,
    ) -> None:
        self.idx = np.asarray(indices)
        self.mel_vib = cache["mel_vib"]
        self.mel_phone = cache["mel_phone"]
        self.current = cache["current"]
        self.vibration = cache["vibration"]
        self.mask = cache["mask"]
        self.y_cls = cache["y_cls"]
        self.y_reg = cache["y_reg"]
        self.stats = stats
        self.modality_dropout = modality_dropout

    def __len__(self) -> int:
        return int(self.idx.size)

    def _norm(self, key: str, x: np.ndarray) -> np.ndarray:
        mu, sd = self.stats[key]
        return (x - mu) / sd

    def __getitem__(self, i: int) -> dict[str, torch.Tensor]:
        j = int(self.idx[i])
        mask = self.mask[j].copy()

        if self.modality_dropout > 0.0:
            drop = np.random.rand(mask.size) < self.modality_dropout
            if not np.all(drop | (mask == 0)):  # never drop every modality
                mask[drop] = 0.0

        sample = {
            "sound_vibrometer": torch.from_numpy(self.mel_vib[j][None]).float(),
            "sound_phone": torch.from_numpy(self.mel_phone[j][None]).float(),
            "current": torch.from_numpy(self._norm("current", self.current[j])[None]).float(),
            "vibration": torch.from_numpy(self._norm("vibration", self.vibration[j])).float(),
            "mask": torch.from_numpy(mask).float(),
            "y_cls": torch.tensor(int(self.y_cls[j])),
            "y_reg": torch.tensor((float(self.y_reg[j]) - 1.0) / 99.0),
            "speed": torch.tensor(float(self.y_reg[j])),
        }
        return sample


def compute_stats(cache: dict[str, np.ndarray], train_idx: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Standardisation statistics for the non-self-normalised modalities (train split only)."""
    stats = {}
    for key in ("current", "vibration"):
        arr = cache[key][train_idx]
        avail = cache["mask"][train_idx, MODALITIES.index(key)] > 0
        arr = arr[avail] if avail.any() else arr
        stats[key] = (arr.mean(axis=0), arr.std(axis=0) + 1e-6)
    return stats


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
class MelCNN(nn.Module):
    """Compact 2D CNN encoder for log-Mel spectrograms."""

    def __init__(self, embed_dim: int, dropout: float) -> None:
        super().__init__()
        chans = (1, 32, 64, 128, 128)
        blocks: list[nn.Module] = []
        for cin, cout in zip(chans[:-1], chans[1:]):
            blocks += [
                nn.Conv2d(cin, cout, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(cout),
                nn.GELU(),
                nn.MaxPool2d(2),
            ]
        self.features = nn.Sequential(*blocks)
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(dropout), nn.Linear(chans[-1], embed_dim), nn.GELU())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(F.adaptive_avg_pool2d(self.features(x), 1))


class SpectrumCNN(nn.Module):
    """1D CNN encoder for the log Welch PSD of the armature current."""

    def __init__(self, embed_dim: int, dropout: float) -> None:
        super().__init__()
        chans = (1, 32, 64, 128)
        blocks: list[nn.Module] = []
        for cin, cout in zip(chans[:-1], chans[1:]):
            blocks += [
                nn.Conv1d(cin, cout, kernel_size=7, padding=3, bias=False),
                nn.BatchNorm1d(cout),
                nn.GELU(),
                nn.MaxPool1d(4),
            ]
        self.features = nn.Sequential(*blocks)
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(dropout), nn.Linear(chans[-1], embed_dim), nn.GELU())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(F.adaptive_avg_pool1d(self.features(x), 1))


class TabularMLP(nn.Module):
    """MLP encoder for the ISO 2954 vibrometer spot readings."""

    def __init__(self, in_dim: int, embed_dim: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.BatchNorm1d(64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, embed_dim),
            nn.GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class MaskedGatedAttentionFusion(nn.Module):
    """Gated attention pooling (Ilse et al., 2018) over modality embeddings.

    Absent modalities receive ``-inf`` logits, so they are excluded from the
    softmax instead of contributing a zero vector.  The returned weights are
    directly interpretable as per-sample modality importance.
    """

    def __init__(self, embed_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.attn_v = nn.Linear(embed_dim, hidden)
        self.attn_u = nn.Linear(embed_dim, hidden)
        self.attn_w = nn.Linear(hidden, 1)

    def forward(self, tokens: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        logits = self.attn_w(torch.tanh(self.attn_v(tokens)) * torch.sigmoid(self.attn_u(tokens))).squeeze(-1)
        logits = logits.masked_fill(mask < 0.5, float("-inf"))
        weights = torch.softmax(logits, dim=1)
        weights = torch.nan_to_num(weights, nan=0.0)
        fused = torch.einsum("bm,bmd->bd", weights, tokens)
        return fused, weights


class MultiModalDualTaskNet(nn.Module):
    """Mid-level attention fusion with a classification and a regression head."""

    def __init__(self, n_classes: int, vib_dim: int, cfg: Config) -> None:
        super().__init__()
        d = cfg.embed_dim
        self.encoders = nn.ModuleDict(
            {
                "sound_vibrometer": MelCNN(d, cfg.dropout),
                "sound_phone": MelCNN(d, cfg.dropout),
                "current": SpectrumCNN(d, cfg.dropout),
                "vibration": TabularMLP(vib_dim, d, cfg.dropout),
            }
        )
        self.modality_embed = nn.Parameter(torch.zeros(len(MODALITIES), d))
        nn.init.normal_(self.modality_embed, std=0.02)

        self.fusion = MaskedGatedAttentionFusion(d)
        self.trunk = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d), nn.GELU(), nn.Dropout(cfg.dropout))
        self.cls_head = nn.Linear(d, n_classes)
        self.reg_head = nn.Linear(d, 1)

    def forward(self, batch: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        tokens = torch.stack([self.encoders[m](batch[m]) for m in MODALITIES], dim=1)
        tokens = tokens + self.modality_embed.unsqueeze(0)
        tokens = tokens * batch["mask"].unsqueeze(-1)  # zero out absent encoders

        fused, weights = self.fusion(tokens, batch["mask"])
        h = self.trunk(fused)
        return {
            "logits": self.cls_head(h),
            "speed": torch.sigmoid(self.reg_head(h)).squeeze(-1),
            "attention": weights,
        }


# --------------------------------------------------------------------------- #
# Train / inference
# --------------------------------------------------------------------------- #
def make_splits(cache: dict[str, np.ndarray], cfg: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Group-aware split: whole recordings go to exactly one split."""
    n = cache["y_cls"].size
    idx, groups, y = np.arange(n), cache["group"], cache["y_cls"]

    gss = GroupShuffleSplit(n_splits=1, test_size=cfg.test_size, random_state=cfg.seed)
    dev_idx, test_idx = next(gss.split(idx, y, groups))

    gss_val = GroupShuffleSplit(n_splits=1, test_size=cfg.val_size, random_state=cfg.seed + 1)
    tr_rel, val_rel = next(gss_val.split(dev_idx, y[dev_idx], groups[dev_idx]))
    return dev_idx[tr_rel], dev_idx[val_rel], test_idx


def run_epoch(model, loader, device, optimiser=None, cfg: Config | None = None) -> dict[str, float]:
    train = optimiser is not None
    model.train(train)
    tot_loss = tot_cls = tot_reg = 0.0
    n_correct = n_seen = 0

    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.set_grad_enabled(train):
            out = model(batch)
            loss_cls = F.cross_entropy(out["logits"], batch["y_cls"], label_smoothing=0.05)
            loss_reg = F.smooth_l1_loss(out["speed"], batch["y_reg"], beta=0.05)
            loss = loss_cls + (cfg.reg_loss_weight if cfg else 1.0) * loss_reg

        if train:
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimiser.step()

        bs = batch["y_cls"].size(0)
        tot_loss += loss.item() * bs
        tot_cls += loss_cls.item() * bs
        tot_reg += loss_reg.item() * bs
        n_correct += (out["logits"].argmax(1) == batch["y_cls"]).sum().item()
        n_seen += bs

    return {
        "loss": tot_loss / n_seen,
        "loss_cls": tot_cls / n_seen,
        "loss_reg": tot_reg / n_seen,
        "acc": n_correct / n_seen,
    }


def train_model(cache: dict[str, np.ndarray], cfg: Config, device: torch.device) -> dict:
    set_seed(cfg.seed)
    train_idx, val_idx, test_idx = make_splits(cache, cfg)
    stats = compute_stats(cache, train_idx)

    loaders = {
        "train": DataLoader(
            DCMotorMultiModalDataset(cache, train_idx, stats, cfg.modality_dropout),
            batch_size=cfg.batch_size, shuffle=True, num_workers=cfg.num_workers, drop_last=True,
        ),
        "val": DataLoader(
            DCMotorMultiModalDataset(cache, val_idx, stats),
            batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers,
        ),
    }

    model = MultiModalDualTaskNet(len(cfg.class_names), cache["vibration"].shape[1], cfg).to(device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=cfg.lr, total_steps=cfg.epochs, pct_start=0.25
    )

    history, best_val, best_state = [], float("inf"), None
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        tr = run_epoch(model, loaders["train"], device, optimiser, cfg)
        scheduler.step()
        va = run_epoch(model, loaders["val"], device, None, cfg)
        history.append({"epoch": epoch, **{f"train_{k}": v for k, v in tr.items()},
                        **{f"val_{k}": v for k, v in va.items()}})
        if va["loss"] < best_val:
            best_val = va["loss"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch % 5 == 0 or epoch == 1:
            print(f"  epoch {epoch:>3}/{cfg.epochs}  train loss {tr['loss']:.4f} acc {tr['acc']:.3f}"
                  f"   |  val loss {va['loss']:.4f} acc {va['acc']:.3f}")

    model.load_state_dict(best_state)
    torch.save(
        {
            "state_dict": best_state,
            "stats": {k: (v[0], v[1]) for k, v in stats.items()},
            "class_names": cfg.class_names,
            "vib_dim": int(cache["vibration"].shape[1]),
            "config": {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(cfg).items()},
            "splits": {"train": train_idx, "val": val_idx, "test": test_idx},
        },
        cfg.ckpt_file,
    )
    pd.DataFrame(history).to_csv(cfg.out_dir / "training_history.csv", index=False)
    print(f"  best val loss {best_val:.4f} -> {cfg.ckpt_file}")
    return {"model": model, "stats": stats, "splits": (train_idx, val_idx, test_idx)}


@torch.no_grad()
def predict(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, np.ndarray]:
    model.eval()
    logits, speeds, y_cls, y_speed, attn, masks = [], [], [], [], [], []
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(batch)
        logits.append(out["logits"].cpu().numpy())
        speeds.append(out["speed"].cpu().numpy())
        attn.append(out["attention"].cpu().numpy())
        masks.append(batch["mask"].cpu().numpy())
        y_cls.append(batch["y_cls"].cpu().numpy())
        y_speed.append(batch["speed"].cpu().numpy())

    logits = np.concatenate(logits)
    probs = torch.softmax(torch.from_numpy(logits), dim=1).numpy()
    return {
        "logits": logits,
        "probs": probs,
        "y_pred": probs.argmax(1),
        "y_true": np.concatenate(y_cls),
        "speed_pred": np.concatenate(speeds) * 99.0 + 1.0,
        "speed_true": np.concatenate(y_speed),
        "attention": np.concatenate(attn),
        "mask": np.concatenate(masks),
    }


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def _style() -> None:
    sns.set_theme(context="paper", style="whitegrid", font_scale=1.05)
    plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 300, "axes.grid": True, "grid.alpha": 0.3})


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"  figure -> {path.with_suffix('.png')}")


def plot_confusion_matrix(res: dict, class_names: list[str], fig_dir: Path) -> None:
    cm = confusion_matrix(res["y_true"], res["y_pred"], labels=range(len(class_names)))
    cm_norm = cm.astype(float) / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    labels = [c.replace("_", " ") for c in class_names]

    fig, ax = plt.subplots(figsize=(9.0, 7.4))
    sns.heatmap(
        cm_norm, annot=cm, fmt="d", cmap="mako_r", vmin=0.0, vmax=1.0, square=True,
        linewidths=0.4, linecolor="white", xticklabels=labels, yticklabels=labels,
        cbar_kws={"label": "Row-normalised recall"}, ax=ax,
    )
    ax.set_xlabel("Predicted operating condition")
    ax.set_ylabel("True operating condition")
    ax.set_title(f"Condition classification — confusion matrix\n"
                 f"accuracy = {accuracy_score(res['y_true'], res['y_pred']):.3f}, "
                 f"macro-F1 = {f1_score(res['y_true'], res['y_pred'], average='macro'):.3f}")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    plt.setp(ax.get_yticklabels(), rotation=0)
    ax.grid(False)
    _save(fig, fig_dir / "fig_confusion_matrix")


def plot_speed_parity(res: dict, class_names: list[str], fig_dir: Path) -> None:
    y_t, y_p = res["speed_true"], res["speed_pred"]
    mae = mean_absolute_error(y_t, y_p)
    rmse = float(np.sqrt(mean_squared_error(y_t, y_p)))
    r2 = r2_score(y_t, y_p)

    fig, ax = plt.subplots(figsize=(6.8, 6.2))
    palette = sns.color_palette("colorblind", len(class_names))
    for k, name in enumerate(class_names):
        sel = res["y_true"] == k
        if sel.any():
            ax.scatter(y_t[sel], y_p[sel], s=26, alpha=0.72, color=palette[k],
                       edgecolor="none", label=name.replace("_", " "))

    lims = (0.0, 105.0)
    ax.plot(lims, lims, "k--", lw=1.4, label="Ideal $y = x$", zorder=5)
    ax.fill_between(lims, [lims[0] - 10, lims[1] - 10], [lims[0] + 10, lims[1] + 10],
                    color="grey", alpha=0.12, label="$\\pm$10 % band", zorder=0)
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_aspect("equal")
    ax.set_xlabel("True speed setpoint (% of rated 2000 RPM)")
    ax.set_ylabel("Predicted speed setpoint (%)")
    ax.set_title(f"Speed-setpoint regression — parity plot\nMAE = {mae:.2f} %, RMSE = {rmse:.2f} %, $R^2$ = {r2:.3f}")
    ax.legend(loc="upper left", fontsize=7.5, frameon=True, ncols=1)
    _save(fig, fig_dir / "fig_speed_parity")

    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    ax.axhline(0.0, color="k", ls="--", lw=1.2)
    ax.scatter(y_t, y_p - y_t, s=24, alpha=0.7, color=sns.color_palette("colorblind")[0], edgecolor="none")
    ax.set_xlabel("True speed setpoint (%)")
    ax.set_ylabel("Residual: predicted − true (%)")
    ax.set_title("Speed-regression residuals versus setpoint")
    _save(fig, fig_dir / "fig_speed_residuals")


def plot_multiclass_roc(res: dict, class_names: list[str], fig_dir: Path) -> dict[str, float]:
    n_cls = len(class_names)
    y_bin = label_binarize(res["y_true"], classes=list(range(n_cls)))
    probs = res["probs"]

    # per-class one-vs-rest curves (integer keys kept separate from the averages)
    fpr: dict[int, np.ndarray] = {}
    tpr: dict[int, np.ndarray] = {}
    roc_auc: dict[int, float] = {}
    for k in range(n_cls):
        if y_bin[:, k].sum() == 0:
            continue
        fpr[k], tpr[k], _ = roc_curve(y_bin[:, k], probs[:, k])
        roc_auc[k] = float(auc(fpr[k], tpr[k]))

    micro_fpr, micro_tpr, _ = roc_curve(y_bin.ravel(), probs.ravel())
    micro_auc = float(auc(micro_fpr, micro_tpr))

    grid = np.unique(np.concatenate([fpr[k] for k in sorted(fpr)]))
    macro_tpr = np.mean([np.interp(grid, fpr[k], tpr[k]) for k in sorted(fpr)], axis=0)
    macro_auc = float(auc(grid, macro_tpr))

    fig, ax = plt.subplots(figsize=(7.0, 6.2))
    palette = sns.color_palette("colorblind", n_cls)
    for k in sorted(fpr):
        ax.plot(fpr[k], tpr[k], lw=1.4, color=palette[k],
                label=f"{class_names[k].replace('_', ' ')} (AUC = {roc_auc[k]:.3f})")
    ax.plot(micro_fpr, micro_tpr, lw=2.6, ls=":", color="deeppink",
            label=f"Micro-average (AUC = {micro_auc:.3f})")
    ax.plot(grid, macro_tpr, lw=2.6, ls="--", color="navy",
            label=f"Macro-average (AUC = {macro_auc:.3f})")
    ax.plot([0, 1], [0, 1], color="grey", lw=1.0, ls="-", label="Chance level")

    ax.set_xlim(-0.01, 1.0)
    ax.set_ylim(0.0, 1.02)
    ax.set_xlabel("False-positive rate")
    ax.set_ylabel("True-positive rate")
    ax.set_title("Multiclass ROC — one-vs-rest with micro/macro averaging")
    ax.legend(loc="lower right", fontsize=7.5, frameon=True)
    _save(fig, fig_dir / "fig_roc_multiclass")

    out = {class_names[k]: roc_auc[k] for k in sorted(fpr)}
    out["micro"] = micro_auc
    out["macro"] = macro_auc
    return out


def plot_modality_attention(res: dict, class_names: list[str], fig_dir: Path) -> pd.DataFrame:
    attn, mask = res["attention"], res["mask"]
    rows = []
    for m, name in enumerate(MODALITIES):
        avail = mask[:, m] > 0
        rows.append({
            "modality": name,
            "label": MODALITY_LABELS[m],
            "mean_attention": float(attn[avail, m].mean()) if avail.any() else 0.0,
            "std_attention": float(attn[avail, m].std()) if avail.any() else 0.0,
            "availability": float(avail.mean()),
        })
    df = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.8))
    palette = sns.color_palette("crest", len(MODALITIES))
    axes[0].bar(df["label"], df["mean_attention"], yerr=df["std_attention"], capsize=4,
                color=palette, edgecolor="black", linewidth=0.6)
    axes[0].set_ylabel("Mean fusion attention weight")
    axes[0].set_xlabel("Sensor modality")
    axes[0].set_title("Modality importance (attention weights, present modalities only)")
    for x, (val, av) in enumerate(zip(df["mean_attention"], df["availability"])):
        axes[0].text(x, val, f"{val:.3f}\n({av * 100:.0f} % avail.)", ha="center", va="bottom", fontsize=8)
    axes[0].set_ylim(0, max(df["mean_attention"].max() * 1.35, 0.1))

    per_class = np.zeros((len(class_names), len(MODALITIES)))
    for k in range(len(class_names)):
        sel = res["y_true"] == k
        if sel.any():
            per_class[k] = attn[sel].mean(axis=0)
    sns.heatmap(per_class, annot=True, fmt=".2f", cmap="rocket_r", ax=axes[1],
                xticklabels=[m.replace("_", "\n") for m in MODALITIES],
                yticklabels=[c.replace("_", " ") for c in class_names],
                cbar_kws={"label": "Mean attention weight"}, linewidths=0.4, linecolor="white")
    axes[1].set_title("Per-condition modality attention")
    axes[1].set_xlabel("Sensor modality")
    axes[1].set_ylabel("True operating condition")
    axes[1].grid(False)
    _save(fig, fig_dir / "fig_modality_attention")
    return df


def plot_training_curves(cfg: Config) -> None:
    hist_file = cfg.out_dir / "training_history.csv"
    if not hist_file.exists():
        return
    hist = pd.read_csv(hist_file)
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    axes[0].plot(hist["epoch"], hist["train_loss"], label="Train")
    axes[0].plot(hist["epoch"], hist["val_loss"], label="Validation")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Total loss (CE + $\\lambda\\cdot$ Huber)")
    axes[0].set_title("Optimisation curves")
    axes[0].legend()
    axes[1].plot(hist["epoch"], hist["train_acc"], label="Train")
    axes[1].plot(hist["epoch"], hist["val_acc"], label="Validation")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Condition accuracy")
    axes[1].set_ylim(0, 1.02)
    axes[1].set_title("Classification accuracy")
    axes[1].legend()
    _save(fig, cfg.fig_dir / "fig_training_curves")


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate(cache: dict[str, np.ndarray], cfg: Config, device: torch.device) -> dict:
    ckpt = torch.load(cfg.ckpt_file, map_location=device, weights_only=False)
    cfg.class_names = list(ckpt["class_names"])
    stats = {k: (np.asarray(v[0]), np.asarray(v[1])) for k, v in ckpt["stats"].items()}
    test_idx = ckpt["splits"]["test"]

    model = MultiModalDualTaskNet(len(cfg.class_names), ckpt["vib_dim"], cfg).to(device)
    model.load_state_dict(ckpt["state_dict"])

    loader = DataLoader(
        DCMotorMultiModalDataset(cache, test_idx, stats),
        batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers,
    )
    res = predict(model, loader, device)

    y_true, y_pred, probs = res["y_true"], res["y_pred"], res["probs"]
    present = np.unique(y_true)
    try:
        auc_macro = roc_auc_score(y_true, probs[:, present], multi_class="ovr", average="macro", labels=present)
        auc_weighted = roc_auc_score(y_true, probs[:, present], multi_class="ovr", average="weighted", labels=present)
    except ValueError:
        auc_macro = auc_weighted = float("nan")

    metrics = {
        "n_test_samples": int(y_true.size),
        "n_test_recordings": int(np.unique(cache["group"][test_idx]).size),
        "classification": {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
            "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
            "weighted_f1": float(f1_score(y_true, y_pred, average="weighted")),
            "roc_auc_ovr_macro": float(auc_macro),
            "roc_auc_ovr_weighted": float(auc_weighted),
        },
        "regression": {
            "mae_percent": float(mean_absolute_error(res["speed_true"], res["speed_pred"])),
            "rmse_percent": float(np.sqrt(mean_squared_error(res["speed_true"], res["speed_pred"]))),
            "r2": float(r2_score(res["speed_true"], res["speed_pred"])),
            "median_abs_err_percent": float(np.median(np.abs(res["speed_pred"] - res["speed_true"]))),
        },
    }

    cfg.table_dir.mkdir(parents=True, exist_ok=True)
    report = classification_report(
        y_true, y_pred, labels=present, target_names=[cfg.class_names[k] for k in present],
        output_dict=True, zero_division=0,
    )
    pd.DataFrame(report).T.to_csv(cfg.table_dir / "classification_report.csv")
    pd.DataFrame({
        "y_true": [cfg.class_names[k] for k in y_true],
        "y_pred": [cfg.class_names[k] for k in y_pred],
        "speed_true": res["speed_true"],
        "speed_pred": res["speed_pred"],
        "group": cache["group"][test_idx],
        **{f"attn_{m}": res["attention"][:, i] for i, m in enumerate(MODALITIES)},
    }).to_csv(cfg.table_dir / "test_predictions.csv", index=False)

    _style()
    cfg.fig_dir.mkdir(parents=True, exist_ok=True)
    plot_confusion_matrix(res, cfg.class_names, cfg.fig_dir)
    plot_speed_parity(res, cfg.class_names, cfg.fig_dir)
    roc_auc = plot_multiclass_roc(res, cfg.class_names, cfg.fig_dir)
    attn_df = plot_modality_attention(res, cfg.class_names, cfg.fig_dir)
    plot_training_curves(cfg)

    metrics["classification"]["roc_auc_micro"] = roc_auc.get("micro")
    metrics["classification"]["roc_auc_macro_curve"] = roc_auc.get("macro")
    metrics["modality_attention"] = attn_df.drop(columns=["label"]).to_dict(orient="records")

    (cfg.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("\n=== Test-set metrics ===")
    print(json.dumps(metrics["classification"], indent=2))
    print(json.dumps(metrics["regression"], indent=2))
    print(f"\nArtefacts written to {cfg.out_dir.resolve()}")
    return metrics


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("DCData_mendeley"), help="dataset root containing metadata.csv")
    p.add_argument("--out", type=Path, default=Path("pipeline_outputs/multimodal"), help="output directory")
    p.add_argument("--stage", choices=("all", "cache", "train", "eval"), default="all")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--windows", type=int, default=8, help="windows extracted per recording")
    p.add_argument("--window-s", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        root=args.root, out_dir=args.out, epochs=args.epochs, batch_size=args.batch_size,
        lr=args.lr, n_windows=args.windows, window_s=args.window_s, seed=args.seed,
    )
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)
    print(f"device: {device}  |  dataset: {cfg.root.resolve()}")

    if args.stage in ("all", "cache") or not cfg.cache_file.exists():
        print("\n[1/3] Building feature cache")
        cache = build_cache(cfg)
    else:
        cache = load_cache(cfg)

    if args.stage == "cache":
        return

    if args.stage in ("all", "train"):
        if not cfg.class_names:
            cache = load_cache(cfg)
        print("\n[2/3] Training multi-modal dual-task model")
        train_model(cache, cfg, device)

    if args.stage in ("all", "eval", "train"):
        if not cfg.ckpt_file.exists():
            raise FileNotFoundError(f"{cfg.ckpt_file} not found - run with --stage train first")
        if not cfg.class_names:
            cache = load_cache(cfg)
        print("\n[3/3] Evaluating and rendering figures")
        evaluate(cache, cfg, device)


if __name__ == "__main__":
    main()
