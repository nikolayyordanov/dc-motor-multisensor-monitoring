"""Export IJAME_2026_Slavov_Zhilevski.docx to PDF via Word COM, render PNGs, and verify sequential citations."""
import re
from pathlib import Path
from docx import Document
import pymupdf
import win32com.client

HERE = Path(__file__).resolve().parent
DOCX = HERE / "IJAME_2026_Slavov_Zhilevski.docx"
OUT = HERE / "_inspect" / "ijame_preview"
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / "ijame_preview.pdf"

# 1. Verify sequential citations in body text (before References)
doc = Document(DOCX)
body_texts = []
for p in doc.paragraphs:
    if p.text.strip() == "References":
        break
    body_texts.append(p.text)
full_body = "\n".join(body_texts)
seen = []
for m in re.finditer(r"\[(\d+)(?:\]\s*[–-]\s*\[(\d+))?\]", full_body):
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    for k in range(a, b + 1):
        if k not in seen:
            seen.append(k)
print("Citation order of first appearance:", seen)
print("Sequential 1..21?", seen == list(range(1, 22)))

# 2. Export PDF via hidden Word
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    wdoc = word.Documents.Open(str(DOCX), ReadOnly=True, AddToRecentFiles=False)
    try:
        wdoc.ExportAsFixedFormat(str(PDF), 17)
    finally:
        wdoc.Close(SaveChanges=0)
finally:
    word.Quit()

pdf = pymupdf.open(PDF)
for i, page in enumerate(pdf, start=1):
    page.get_pixmap(dpi=110).save(OUT / f"p{i:02d}.png")
print("OK PDF pages:", len(pdf))
