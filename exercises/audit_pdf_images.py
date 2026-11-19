"""Audit image resolutions (pixel size and effective DPI) in Ръководство за ЛУ по СЕЗ.pdf."""
from pathlib import Path
import pymupdf

HERE = Path(__file__).resolve().parent
PDF = HERE / "Ръководство за ЛУ по СЕЗ.pdf"
OUT = HERE / "review_guide" / "pdf_images_audit.txt"

doc = pymupdf.open(PDF)
lines = []
low = []
for pno, page in enumerate(doc, start=1):
    infos = page.get_image_info(xrefs=True)
    for idx, info in enumerate(infos, start=1):
        w, h = info["width"], info["height"]
        bbox = info["bbox"]
        bw_in = (bbox[2] - bbox[0]) / 72.0
        bh_in = (bbox[3] - bbox[1]) / 72.0
        dx = w / bw_in if bw_in > 0 else 0
        dy = h / bh_in if bh_in > 0 else 0
        eff = min(dx, dy)
        line = f"pdf{pno:03d} (printed {pno-1:03d}) img#{idx}: {w}x{h}px, box={bw_in*2.54:.1f}x{bh_in*2.54:.1f}cm, effDPI={eff:.0f}"
        lines.append(line)
        if eff < 150:
            low.append((eff, line))

summary = [
    f"Total image placements in PDF: {len(lines)}",
    f"Placements < 150 DPI: {len(low)}",
    f"Placements < 100 DPI: {sum(1 for e, _ in low if e < 100)}",
    "",
    "== Lowest 30 DPI placements ==",
    *[l for _, l in sorted(low, key=lambda x: x[0])[:30]],
    "",
    "== All placements ==",
    *lines,
]
OUT.write_text("\n".join(summary), encoding="utf-8")
print(f"OK total={len(lines)} <150dpi={len(low)}")
