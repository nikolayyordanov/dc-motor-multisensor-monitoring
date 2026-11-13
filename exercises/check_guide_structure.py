"""Structural checks on the extracted guide: equation/figure/table numbering, references, TOC pages."""
import re
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent / "review_guide"
pages = sorted((OUT / "pages").glob("p*.txt"))
texts = {int(p.stem[1:]): p.read_text(encoding="utf-8") for p in pages}

eq_lab = re.compile(r"^\s*\((\d{1,2})\.(\d{1,2})\)\s*$", re.M)
cap = re.compile(r"(Фиг|Табл)\.\s*(\d{1,2})\.(\d{1,2})\.")
ref = re.compile(r"(?:фиг|табл)\.\s*(\d{1,2})\.(\d{1,2})", re.I)
eqref = re.compile(r"\((\d{1,2})\.(\d{1,2})\)")
head = re.compile(r"^[ \t]*(\d{1,2})\.(\d)\.(?:\d\.)?[ \t]+\S", re.M)

report = []
eqs, caps, refs = defaultdict(list), defaultdict(list), defaultdict(list)
for pg, t in texts.items():
    for m in eq_lab.finditer(t):
        eqs[int(m[1])].append((int(m[2]), pg))
    for m in cap.finditer(t):
        caps[(m[1], int(m[2]))].append((int(m[3]), pg))
    for m in ref.finditer(t):
        refs[(int(m[1]), int(m[2]))].append(pg)

report.append("== equation labels per lab (number@pdfpage) ==")
for lab in sorted(eqs):
    seq = eqs[lab]
    nums = [n for n, _ in seq]
    expected = list(range(1, max(nums) + 1))
    missing = sorted(set(expected) - set(nums))
    dup = sorted({n for n in nums if nums.count(n) > 1})
    disorder = nums != sorted(nums)
    report.append(f"L{lab}: {' '.join(f'{n}@{p}' for n, p in seq)}")
    report.append(f"   missing={missing} dup={dup} out_of_order={disorder}")

report.append("\n== captions ==")
cap_set = set()
for (kind, lab), seq in sorted(caps.items()):
    nums = [n for n, _ in seq]
    cap_set |= {(kind, lab, n) for n in nums}
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    dup = sorted({n for n in nums if nums.count(n) > 1})
    report.append(f"{kind} {lab}: {' '.join(f'{n}@{p}' for n, p in seq)} missing={missing} dup={dup} ooo={nums != sorted(nums)}")

report.append("\n== references to figures/tables without caption ==")
for pg, t in texts.items():
    for m in re.finditer(r"(фиг|табл)\.\s*(\d{1,2})\.(\d{1,2})", t, re.I):
        kind = "Фиг" if m[1].lower() == "фиг" else "Табл"
        key = (kind, int(m[2]), int(m[3]))
        if key not in cap_set:
            report.append(f"p{pg}: {m[0]} -> no caption found")

report.append("\n== figures/tables never referenced in text (lowercase refs) ==")
lower_refs = set()
for pg, t in texts.items():
    for m in re.finditer(r"(фиг|табл)\.\s*(\d{1,2})\.(\d{1,2})", t):
        lower_refs.add(("Фиг" if m[1] == "фиг" else "Табл", int(m[2]), int(m[3])))
for key in sorted(cap_set - lower_refs):
    report.append(f"{key[0]}. {key[1]}.{key[2]}")

report.append("\n== equation references to undefined labels ==")
defined = {(lab, n) for lab, seq in eqs.items() for n, _ in seq}
for pg, t in texts.items():
    for m in eqref.finditer(t):
        key = (int(m[1]), int(m[2]))
        if key not in defined and 1 <= key[0] <= 10:
            report.append(f"p{pg}: ({key[0]}.{key[1]}) referenced but no label line")

report.append("\n== section headings (printed page = pdf-1) ==")
for pg, t in texts.items():
    if pg < 9:
        continue
    for m in head.finditer(t):
        line = t[m.start():t.find("\n", m.start())].strip()
        if len(line) < 90:
            report.append(f"pdf{pg} printed{pg - 1}: {line}")

report.append("\n== TOC entries ==")
for pg in (4, 5, 6):
    for line in texts[pg].splitlines():
        m = re.match(r"\s*(\d{1,2}\.\d(?:\.\d)?\.)\s*(.*?)[….,\s]+(\d+)\s*$", line)
        if m:
            report.append(f"TOC {m[1]} -> {m[3]}")

(OUT / "structure_report.txt").write_text("\n".join(report), encoding="utf-8")
print("OK")
