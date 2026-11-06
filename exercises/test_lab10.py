"""Numerical, source-integrity and isolated ZIP checks for Lab10."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import zipfile
import numpy as np
import pandas as pd
from PIL import Image
from docx import Document
import win32com.client
import lab10_vibroacoustics as lab

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures_lab10"
report = json.loads((OUT / "document_validation.json").read_text(encoding="utf-8"))
assert lab.sha(HERE / "Lab10.doc") == report["original_doc_sha256"]
info = json.loads((OUT / "provenance.json").read_text(encoding="utf-8"))
assert len(info["sources"]) == 14
assert all(lab.sha(HERE.parent / "DCData_mendeley" / item["path"]) == item["sha256"] for item in info["sources"])
stats = pd.read_csv(OUT / "vibration_statistics.csv")
assert len(stats) == 30
assert set(stats.speed_percent) == {10, 20, 50, 80, 100}
assert (stats.n > 0).all()
y = .2 * np.sin(2 * np.pi * 300 * np.arange(44100) / 44100)
freq, amp = lab.amplitude(y, 44100)
assert abs(amp[300] - .2) < 1e-8
assert freq[300] == 300
for stem in ("fig10_4_amplitude_spectra", "fig10_5_spectrograms"):
    with Image.open(OUT / (stem + ".png")) as image:
        assert abs(image.info["dpi"][0] - 600) < .1
        image.thumbnail((1200, 800))
        image.save(OUT / (stem + "_preview.png"))
doc = Document(HERE / report["output"])
text = "\n".join(p.text for p in doc.paragraphs)
assert "10%, 20%, 50%, 80% и 100%" in text
assert "(10.7)" in text and "(m=5)" not in text
assert len(doc.inline_shapes) == 2
files = ("lab10_vibroacoustics.py", "requirements_lab10.txt", "README_lab10_bg.md")
with zipfile.ZipFile(HERE / "lab10_vibroacoustics.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(HERE / name, name)
with tempfile.TemporaryDirectory() as folder:
    with zipfile.ZipFile(HERE / "lab10_vibroacoustics.zip") as archive:
        assert set(archive.namelist()) == set(files)
        archive.extractall(folder)
    subprocess.run([sys.executable, "-I", str(Path(folder) / files[0]), "--help"],
                   cwd=folder, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([sys.executable, "-I", str(Path(folder) / files[0]),
                    str(HERE.parent / "DCData_mendeley"), "--output", str(Path(folder) / "results")],
                   cwd=folder, check=True)
    actual = pd.read_csv(Path(folder) / "results/vibration_statistics.csv")
    pd.testing.assert_frame_equal(stats, actual)
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    opened = word.Documents.Open(str(HERE / report["output"]), ReadOnly=True, AddToRecentFiles=False)
    try:
        opened.ExportAsFixedFormat(str(OUT / "Lab10_revised_review.pdf"), 17)
    finally:
        opened.Close(SaveChanges=0)
finally:
    word.Quit()
print("PASS: FFT, XLS30 rows, 14 source hashes, DOCX formula preservation, isolated ZIP full execution and Word PDF export.")