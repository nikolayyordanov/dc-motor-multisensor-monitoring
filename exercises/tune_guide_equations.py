"""Enlarge inline fraction arguments of the new equations, fix the Lab 8 duplicate insertion, re-export PDFs."""
from pathlib import Path

import win32com.client

HERE = Path(__file__).resolve().parent
FILES = ["12. ЛУ 8_v.docx", "13. ЛУ 9_v.docx", "14. ЛУ 10_v.docx"]
NEW = "Относителната мощност в"
FRAC, SCALE = 7, 1.4


def enlarge_fractions(omath, base, log, seen):
    for i in range(1, omath.Functions.Count + 1):
        func = omath.Functions(i)
        key = (func.Range.Start, func.Range.End, func.Type)
        if key in seen:
            continue
        seen.add(key)
        if func.Type == FRAC:
            for arg in (func.Frac.Num, func.Frac.Den):
                if arg.Range.Font.Size < base * 1.2:  # inline math shrinks fraction arguments
                    arg.Range.Font.Size = round(base * SCALE * 2) / 2
                    log.append(f"frac arg -> {arg.Range.Font.Size}")
        for j in range(1, func.Args.Count + 1):
            enlarge_fractions(func.Args(j), base, log, seen)


def main():
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    lines = []
    try:
        for name in FILES:
            doc = word.Documents.Open(str(HERE / name), AddToRecentFiles=False)
            try:
                doc.TrackRevisions = False
                for i in range(1, doc.OMaths.Count + 1):
                    om = doc.OMaths(i)
                    base = om.Range.Paragraphs(1).Range.Characters(1).Font.Size
                    log = []
                    enlarge_fractions(om, base, log, set())
                    lines.append(f"{name} omath{i} base={base}: {log}")
                doc.TrackRevisions = True
                if name.startswith("12."):
                    rng = doc.Content
                    f = rng.Find
                    f.Text = NEW + NEW
                    f.MatchCase = True
                    if f.Execute():
                        doc.Range(rng.Start, rng.Start + len(NEW)).Delete()
                        lines.append(f"{name}: duplicate removed")
                doc.Save()
                doc.ExportAsFixedFormat(str(HERE / "review_guide" / f"verify_{Path(name).stem}.pdf"), 17)
            finally:
                doc.Close(SaveChanges=0)
    finally:
        word.Quit()
    (HERE / "review_guide" / "tune_log.txt").write_text("\n".join(lines), encoding="utf-8")
    print("OK")


if __name__ == "__main__":
    main()
