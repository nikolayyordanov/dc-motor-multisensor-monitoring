"""Extract the lab guide PDF page by page into UTF-8 text files for chunked review."""
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
PDF = HERE / "Ръководство за ЛУ по СЕЗ.pdf"
OUT = HERE / "review_guide"
PAGES = OUT / "pages"
CHUNK = 12


def main() -> int:
    PAGES.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    index = [f"pages={doc.page_count}"]
    chunks: list[str] = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        (PAGES / f"p{i:03d}.txt").write_text(text, encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        head = " | ".join(lines[:3])[:160]
        index.append(f"p{i:03d} chars={len(text):5d} imgs={len(page.get_images()):2d} :: {head}")
        chunks.append(f"\n===== PAGE {i} =====\n{text}")
    (OUT / "index.txt").write_text("\n".join(index), encoding="utf-8")
    for start in range(0, len(chunks), CHUNK):
        end = min(start + CHUNK, len(chunks))
        (OUT / f"chunk_p{start + 1:03d}-p{end:03d}.txt").write_text("".join(chunks[start:end]), encoding="utf-8")
    toc = doc.get_toc()
    (OUT / "toc.txt").write_text("\n".join(f"{lvl} p{p}: {t}" for lvl, t, p in toc), encoding="utf-8")
    print(f"OK pages={doc.page_count} toc_entries={len(toc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
