import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multimodal_pipeline import Config, MultiModalDualTaskNet  # noqa: E402

cfg = Config()
ckpt = torch.load(cfg.ckpt_file, map_location="cpu", weights_only=False)
cfg.class_names = list(ckpt["class_names"])
model = MultiModalDualTaskNet(len(cfg.class_names), ckpt["vib_dim"], cfg)
model.load_state_dict(ckpt["state_dict"])

params = {n: sum(p.numel() for p in m.parameters()) for n, m in model.encoders.items()}
params["fusion"] = sum(p.numel() for p in model.fusion.parameters())
params["trunk+heads"] = sum(p.numel() for p in list(model.trunk.parameters())
                            + list(model.cls_head.parameters()) + list(model.reg_head.parameters()))
params["total"] = sum(p.numel() for p in model.parameters())

pred = pd.read_csv(cfg.table_dir / "test_predictions.csv")
fam = lambda s: s.replace("_with_reversal", "").replace("_no_reversal", "")  # noqa: E731
rev = lambda s: "with" if "with_reversal" in s else "no"  # noqa: E731
pred["fam_true"], pred["fam_pred"] = pred.y_true.map(fam), pred.y_pred.map(fam)
pred["rev_true"], pred["rev_pred"] = pred.y_true.map(rev), pred.y_pred.map(rev)

err = (pred.speed_pred - pred.speed_true).abs()
splits = ckpt["splits"]

summary = {
    "params": params,
    "family_accuracy": float((pred.fam_true == pred.fam_pred).mean()),
    "reversal_accuracy": float((pred.rev_true == pred.rev_pred).mean()),
    "errors_within_family": int(((pred.y_true != pred.y_pred) & (pred.fam_true == pred.fam_pred)).sum()),
    "errors_total": int((pred.y_true != pred.y_pred).sum()),
    "mae_low_speed_le10": float(err[pred.speed_true <= 10].mean()),
    "mae_high_speed_gt10": float(err[pred.speed_true > 10].mean()),
    "split_sizes": {k: int(np.asarray(v).size) for k, v in splits.items()},
    "split_recordings": {k: int(np.unique(np.load(cfg.cache_file)["group"][np.asarray(v)]).size)
                         for k, v in splits.items()},
    "n_test_speeds": sorted(pred.speed_true.unique().tolist()),
}
Path("pipeline_outputs/multimodal/paper_facts.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
