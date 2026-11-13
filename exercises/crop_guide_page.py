"""Render a clipped region of a guide page at high DPI: python crop_guide_page.py PAGE Y0 Y1 (fractions of page height)."""
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
doc = pymupdf.open(HERE / "Ръководство за ЛУ по СЕЗ.pdf")
page = doc[int(sys.argv[1]) - 1]
r = page.rect
clip = pymupdf.Rect(r.x0, r.y0 + float(sys.argv[2]) * r.height, r.x1, r.y0 + float(sys.argv[3]) * r.height)
out = HERE / "review_guide" / "png" / f"crop_p{int(sys.argv[1]):03d}.png"
page.get_pixmap(dpi=250, clip=clip).save(out)
print("OK", out)
