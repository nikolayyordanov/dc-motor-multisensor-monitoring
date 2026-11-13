"""Render selected guide pages to PNG for visual checks: python render_guide_pages.py 12 14 26"""
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
OUT = HERE / "review_guide" / "png"
OUT.mkdir(parents=True, exist_ok=True)
doc = pymupdf.open(HERE / "Ръководство за ЛУ по СЕЗ.pdf")
for arg in sys.argv[1:]:
    n = int(arg)
    doc[n - 1].get_pixmap(dpi=110).save(OUT / f"p{n:03d}.png")
print("OK", sys.argv[1:])
