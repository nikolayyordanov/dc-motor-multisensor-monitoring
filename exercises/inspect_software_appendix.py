"""Read the author's legacy appendix without modifying the original DOC."""
import hashlib
import json
from pathlib import Path

from docx import Document
import win32com.client

HERE = Path(__file__).resolve().parent


def main():
    source = HERE / "17. Приложение 1.doc"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = HERE / "review_appendix1"
    output.mkdir(exist_ok=True)
    converted = output / "Appendix1_review.docx"
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        document = word.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False)
        try:
            document.SaveAs2(str(converted), FileFormat=16, AddToRecentFiles=False)
        finally:
            document.Close(SaveChanges=0)
    finally:
        word.Quit()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    document = Document(converted)
    lines = [f"P{i}: {p.text}" for i, p in enumerate(document.paragraphs)]
    for i, table in enumerate(document.tables):
        lines.append(f"TABLE {i}")
        lines.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
    (output / "source_text.txt").write_text("\n".join(lines), encoding="utf-8")
    (output / "inspection.json").write_text(json.dumps({
        "source": source.name, "source_sha256": digest, "source_unchanged": True,
        "paragraphs": len(document.paragraphs), "tables": len(document.tables),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Appendix inspected; original DOC unchanged.")


if __name__ == "__main__":
    main()