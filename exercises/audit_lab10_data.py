"""Read-only inventory and spot-reading statistics supporting the Lab10 review."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DCData_mendeley"
OUT = ROOT / "exercises/review_lab10"
meta = pd.read_csv(DATA / "metadata.csv")
conditions = ["normal_no_reversal", "loose_foundation_no_reversal"]
report = {}
for condition in conditions:
    selected = meta[meta.condition == condition]
    entry = {sensor: sorted(selected[selected.sensor == sensor].speed_percent.astype(int).tolist())
             for sensor in ("vibration", "sound_vibrometer", "sound_phone")}
    stats = []
    for row in selected[selected.sensor == "vibration"].itertuples():
        book = xlrd.open_workbook(str(DATA / row.new_path))
        readings = {name: [] for name in ("Velocity", "Acceleration", "Displacement")}
        examples = []
        for sheet in book.sheets():
            for i in range(sheet.nrows):
                if sheet.ncols >= 5 and str(sheet.cell_value(i, 3)).strip() in readings:
                    quantity = str(sheet.cell_value(i, 3)).strip()
                    readings[quantity].append(float(sheet.cell_value(i, 4)))
                    if len(examples) < 3:
                        examples.append(sheet.row_values(i))
        stats.append({"speed": int(row.speed_percent), "file": row.new_path,
                      "readings": {name: {"n": len(values), "mean": float(np.mean(values)),
                                           "sd": float(np.std(values, ddof=1))}
                                   for name, values in readings.items() if values},
                      "example_rows": examples})
        book.release_resources()
    entry["xls_statistics"] = stats
    report[condition] = entry
(OUT / "dataset_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("Read-only dataset audit complete")