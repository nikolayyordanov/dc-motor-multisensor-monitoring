"""Export Презентация_ЛУ_8_9_10_и_AI.pptx to PDF via PowerPoint COM and render PNG thumbnails."""
from pathlib import Path
import pymupdf
import win32com.client

HERE = Path(__file__).resolve().parent
PPTX = HERE / "Презентация_ЛУ_8_9_10_и_AI.pptx"
OUT = HERE / "review_guide" / "slides_preview"
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / "slides.pdf"

ppt = win32com.client.DispatchEx("PowerPoint.Application")
try:
    pres = ppt.Presentations.Open(str(PPTX), WithWindow=False)
    try:
        pres.SaveAs(str(PDF), 32)  # 32 = ppSaveAsPDF
    finally:
        pres.Close()
finally:
    ppt.Quit()

doc = pymupdf.open(PDF)
for i, page in enumerate(doc, start=1):
    page.get_pixmap(dpi=110).save(OUT / f"s{i:02d}.png")
print("OK slides=", len(doc))
