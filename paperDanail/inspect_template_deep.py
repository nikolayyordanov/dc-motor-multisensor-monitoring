"""Inspect IJAME template styles/structure and extract figures from the manuscript."""
import zipfile
from pathlib import Path
from docx import Document
from lxml import etree

HERE = Path(__file__).resolve().parent
TPL = HERE / "Template IJAME 2026-OTH.docx"
MS = HERE / "IJOMAM-2026_4_Zhilevski_2.docx"
OUT = HERE / "_inspect"
FIGS = OUT / "figs"
FIGS.mkdir(parents=True, exist_ok=True)

# Extract figures from manuscript
with zipfile.ZipFile(MS) as z:
    for n in sorted(z.namelist()):
        if n.startswith("word/media/"):
            (FIGS / Path(n).name).write_bytes(z.read(n))

doc = Document(TPL)
lines = ["=== TEMPLATE PARAGRAPH DETAILS ==="]
for i, p in enumerate(doc.paragraphs):
    pf = p.paragraph_format
    r0 = p.runs[0] if p.runs else None
    font = f"{r0.font.name}/{r0.font.size.pt if r0 and r0.font.size else None}pt/b={r0.bold if r0 else None}/i={r0.italic if r0 else None}" if r0 else "no-runs"
    lines.append(
        f"P{i:02d} style={p.style.name!r} align={pf.alignment} "
        f"sb={pf.space_before.pt if pf.space_before else None} sa={pf.space_after.pt if pf.space_after else None} "
        f"fi={pf.first_line_indent.cm if pf.first_line_indent else None} font={font} | {p.text[:70]!r}"
    )

lines.append("\n=== TEMPLATE HEADERS / FOOTERS ===")
for si, sec in enumerate(doc.sections):
    lines.append(f"Sec {si}: diff_first={sec.different_first_page_header_footer}")
    for name, hf in [("header", sec.header), ("first_header", sec.first_page_header),
                     ("footer", sec.footer), ("first_footer", sec.first_page_footer)]:
        txt = " | ".join(p.text.strip() for p in hf.paragraphs if p.text.strip())
        lines.append(f"  {name}: {txt[:120]}")

(OUT / "template_styles.txt").write_text("\n".join(lines), encoding="utf-8")
print("OK")
