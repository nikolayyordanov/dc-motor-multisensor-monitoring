"""Inspect the Lab 8/9/10 and Appendix 1 Word files (read-only) around the passages to be corrected."""
import json
import re
from pathlib import Path

import win32com.client

HERE = Path(__file__).resolve().parent
FILES = ["12. ЛУ 8_v.docx", "13. ЛУ 9_v.doc", "14. ЛУ 10_v.doc", "17. Приложение 1 (1).doc"]
KEYS = re.compile(r"T_?v|прозор|GroupKFold|lab8\.py|lab08_ml|10\.4|8\.8|\(8\.1\)|\(9\.6\)|\(9\.8\)|\(9\.10\)|\(10\.1\)|"
                  r"броя на отчета|README|Приложение 2|верига\.\.|Кои са|ПОПЪЛВА|results0|упражнение 08|МОНИТОРИ|f_r|rf", re.I)
OUT = HERE / "review_guide" / "word_inspection.txt"


def main():
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    lines = []
    try:
        for name in FILES:
            doc = word.Documents.Open(str(HERE / name), ReadOnly=True, AddToRecentFiles=False)
            try:
                lines.append(f"\n######## {name} paragraphs={doc.Paragraphs.Count} omaths={doc.OMaths.Count} "
                             f"inlineshapes={doc.InlineShapes.Count} revisions={doc.Revisions.Count} track={doc.TrackRevisions}")
                for i, shape in enumerate(doc.InlineShapes, start=1):
                    prog = ""
                    try:
                        prog = shape.OLEFormat.ProgID
                    except Exception:
                        pass
                    if prog:
                        para = shape.Range.Paragraphs(1).Range.Text.strip().replace("\r", " ")[:80]
                        lines.append(f"  ISH{i} type={shape.Type} prog={prog} start={shape.Range.Start} para='{para}'")
                for i, para in enumerate(doc.Paragraphs, start=1):
                    text = para.Range.Text
                    if KEYS.search(text):
                        lines.append(f"  P{i} [{para.Range.Start}-{para.Range.End}] {json.dumps(text.strip(), ensure_ascii=False)[:700]}")
            finally:
                doc.Close(SaveChanges=0)
    finally:
        word.Quit()
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("OK", OUT)


if __name__ == "__main__":
    main()
