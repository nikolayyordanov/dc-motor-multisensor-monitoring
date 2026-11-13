"""Inspect inline shapes (equation objects) in the target paragraphs of the Lab 8/9/10 Word files (read-only)."""
from pathlib import Path

import win32com.client

HERE = Path(__file__).resolve().parent
TARGETS = {"12. ЛУ 8_v.docx": [24, 26, 28, 29, 52, 54], "13. ЛУ 9_v.doc": [45, 50, 52, 59],
           "14. ЛУ 10_v.doc": [21]}
OUT = HERE / "review_guide" / "word_shapes.txt"


def main():
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    lines = []
    try:
        for name, paras in TARGETS.items():
            doc = word.Documents.Open(str(HERE / name), ReadOnly=True, AddToRecentFiles=False)
            try:
                lines.append(f"######## {name} format={doc.SaveFormat}")
                for p in paras:
                    rng = doc.Paragraphs(p).Range
                    lines.append(f" P{p} shapes={rng.InlineShapes.Count} fields={rng.Fields.Count}")
                    for i in range(1, rng.InlineShapes.Count + 1):
                        s = rng.InlineShapes(i)
                        info = [f"type={s.Type}", f"start={s.Range.Start}", f"w={s.Width:.1f}", f"h={s.Height:.1f}"]
                        for attr in ("ClassType", "ProgID", "IconLabel"):
                            try:
                                info.append(f"{attr}={getattr(s.OLEFormat, attr)}")
                            except Exception as exc:
                                info.append(f"{attr}=ERR")
                        try:
                            info.append(f"field={s.Field.Code.Text.strip()}")
                        except Exception:
                            pass
                        font = s.Range.Font
                        info.append(f"bold={font.Bold} color={font.Color}")
                        lines.append("   " + " ".join(info))
                    for i in range(1, rng.Fields.Count + 1):
                        f = rng.Fields(i)
                        lines.append(f"   FIELD type={f.Type} code={f.Code.Text.strip()[:80]}")
            finally:
                doc.Close(SaveChanges=0)
    finally:
        word.Quit()
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("OK")


if __name__ == "__main__":
    main()
