"""Render pages of the verification PDFs that contain given text snippets: python render_verify_pages.py"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent / "review_guide"
TARGETS = {"verify_12. ЛУ 8_v.pdf": ["Дискретният измерен", "(8.8)", "StratifiedGroupKFold", "Матрици на объркванията"],
           "verify_13. ЛУ 9_v.pdf": ["(9.6)", "(9.10)", "README_START_BG"],
           "verify_14. ЛУ 10_v.pdf": ["(10.1)", "README_START_BG", "Кои са основните източници на вибрации"],
           "verify_17. Приложение 1 (1).pdf": ["g28trvywnx"]}
for name, snippets in TARGETS.items():
    doc = pymupdf.open(OUT / name)
    done = set()
    for snippet in snippets:
        pages = [p.number for p in doc if p.search_for(snippet)]
        print(name, snippet, pages)
        for n in pages[:1]:
            if n not in done:
                done.add(n)
                doc[n].get_pixmap(dpi=100).save(OUT / "png" / f"v_{Path(name).stem}_{n + 1}.png")
