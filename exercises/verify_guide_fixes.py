"""Verify the corrected Word files: list tracked revisions and equations, export PDFs for visual checking."""
from pathlib import Path

import win32com.client

HERE = Path(__file__).resolve().parent
FILES = ["12. ЛУ 8_v.docx", "13. ЛУ 9_v.docx", "14. ЛУ 10_v.docx", "17. Приложение 1 (1).doc"]
OUT = HERE / "review_guide"
PDF = 17


def main():
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    lines = []
    try:
        for name in FILES:
            doc = word.Documents.Open(str(HERE / name), ReadOnly=True, AddToRecentFiles=False)
            try:
                lines.append(f"## {name} compat={doc.CompatibilityMode} revisions={doc.Revisions.Count} omaths={doc.OMaths.Count}")
                for i in range(1, doc.Revisions.Count + 1):
                    r = doc.Revisions(i)
                    lines.append(f"  rev{i} type={r.Type} {r.Range.Text[:120]!r}")
                for i in range(1, doc.OMaths.Count + 1):
                    m = doc.OMaths(i)
                    para = m.Range.Paragraphs(1).Range.Text.strip()[:60]
                    m.Linearize()
                    lines.append(f"  omath{i} {m.Range.Text!r} in {para!r}")
                    m.BuildUp()
                doc.ExportAsFixedFormat(str(OUT / f"verify_{Path(name).stem}.pdf"), PDF)
            finally:
                doc.Close(SaveChanges=0)
    finally:
        word.Quit()
    (OUT / "verify_log.txt").write_text("\n".join(lines), encoding="utf-8")
    print("OK")


if __name__ == "__main__":
    main()
