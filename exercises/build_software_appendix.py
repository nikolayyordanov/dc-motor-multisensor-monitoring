"""Build Appendix 2 DOCX and an allowlisted, validated three-exercise ZIP."""
from datetime import datetime
import hashlib
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from docx import Document
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
NAME = "labs_08_09_10_software_v1.0"
FILES = {
    "lab08/lab08_ml.py": "lab08_ml.py",
    "lab08/requirements_lab08_ml.txt": "requirements_lab08_ml.txt",
    "lab08/README_lab08_ml_bg.md": "README_lab08_ml_bg.md",
    "lab09/plot_lab_current.py": "plot_lab_current.py",
    "lab09/requirements_figures.txt": "requirements_figures.txt",
    "lab09/README_figures_bg.md": "README_figures_bg.md",
    "lab10/lab10_vibroacoustics.py": "lab10_vibroacoustics.py",
    "lab10/requirements_lab10.txt": "requirements_lab10.txt",
    "lab10/README_lab10_bg.md": "README_lab10_bg.md",
}
START = """# Програмни средства за упражнения №08, №09 и №10

Версия 1.0, 06.11.2026. Прочетете docs/Appendix2_software_bg.md или Word
варианта на приложението за описание и команди. Кодът е в lab08/, lab09/, lab10/.
Всяка папка може да се използва самостоятелно, със своя файл със зависимости.

Изисква 64-битов Python 3.11+. Разархивирайте пакета извън измерванията.
Инсталиране за трите упражнения от основната папка:

```text
python -m pip install -r requirements_all.txt
python lab08/lab08_ml.py "C:/work/DCData_mendeley" --output "../results08"
python lab09/plot_lab_current.py "C:/work/DCData_mendeley" --output "../results09"
python lab10/lab10_vibroacoustics.py "C:/work/DCData_mendeley" --output "../results10"
```

Пътят към набора се заменя с действителния. За параметри използвайте --help.
Създавайте отделни изходни папки. №09 замества съществуващите резултати със
същите имена; №08/10 изискват --overwrite при непразна изходна папка.
Не са нужни Word/Excel или други проектни програми. Библиотеките се
инсталират отделно, не са включени в ZIP. Данните също не са включени;
запазете структурата metadata.csv и data/ и спазвайте лиценза на набора.

SHA256SUMS.txt съдържа контролните суми на останалите файлове в пакета.
TESTED_ENVIRONMENT.json описва средата при проверката; това не означава
гаранция за еднакви числени стойности при всички версии на библиотеките.

За публикуване вижте docs/PUBLISH_software_bg.md. Публичният адрес на кода
и DOI/адресът на данните трябва да се попълнят в приложението след избор
на място за публикуване. Лиценз за собствения код не е избран автоматично.
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inline(paragraph, text):
    for token in re.split(r"(\*\*.*?\*\*)", text):
        run = paragraph.add_run(token[2:-2] if token.startswith("**") else token)
        if token.startswith("**"):
            run.bold = True


def make_docx(markdown):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2)
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(6)
    for name in ("Title", "Heading 1", "Heading 2"):
        doc.styles[name].font.name = "Times New Roman"
        doc.styles[name].font.color.rgb = RGBColor.from_string("000000")
    code = False
    pending = []
    table_lines = []
    def flush():
        if pending:
            p = doc.add_paragraph()
            inline(p, " ".join(pending))
            pending.clear()
    def flush_table():
        if not table_lines:
            return
        data = [[cell.strip() for cell in line.strip("|").split("|")] for line in table_lines]
        data = [row for row in data if not all(re.fullmatch(r":?-+:?", cell) for cell in row)]
        table = doc.add_table(rows=0, cols=len(data[0]))
        table.style = "Table Grid"
        for i, row in enumerate(data):
            cells = table.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = text
                for run in cell.paragraphs[0].runs:
                    run.font.size = Pt(9)
                    run.bold = i == 0
        table_lines.clear()
    for line in markdown.splitlines():
        if line.startswith("```"):
            flush()
            flush_table()
            code = not code
            continue
        if code:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(line)
            run.font.name = "Consolas"
            run.font.size = Pt(8)
            continue
        if line.startswith("|"):
            flush()
            table_lines.append(line)
            continue
        flush_table()
        if not line.strip():
            flush()
        elif line.startswith("# "):
            flush()
            doc.add_paragraph(line[2:], style="Title")
        elif line.startswith("## "):
            flush()
            doc.add_heading(line[3:], level=1)
        else:
            pending.append(line)
    flush()
    flush_table()
    assert not code
    doc.core_properties.title = "Приложение 2 — Програмни средства за упражнения 08–10"
    doc.core_properties.subject = "Електронни листинги и указания за използване"
    doc.core_properties.author = ""
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def save_new_version(path, data):
    candidate, counter = path, 1
    while True:
        try:
            candidate.write_bytes(data)
            return candidate
        except PermissionError:
            counter += 1
            candidate = path.with_stem(path.stem + f"_v{counter}")
            while candidate.exists():
                counter += 1
                candidate = path.with_stem(path.stem + f"_v{counter}")


def main():
    protected = {p: sha(p.read_bytes()) for p in HERE.glob("*.docx")
                 if not p.name.startswith("Appendix2_software_bg") and not p.name.startswith("~$")}
    appendix = (HERE / "Appendix2_software_bg.md").read_text(encoding="utf-8")
    document = make_docx(appendix)
    docpath = save_new_version(HERE / "Appendix2_software_bg.docx", document)
    payload = {target: (HERE / source).read_bytes() for target, source in FILES.items()}
    # Exclude an internal Word-builder section from the standalone Lab09 README.
    lab09 = payload["lab09/README_figures_bg.md"].decode("utf-8")
    payload["lab09/README_figures_bg.md"] = lab09.split("## Отделен редактиран документ")[0].rstrip().encode("utf-8") + b"\n"
    payload["README_START_BG.md"] = START.encode("utf-8")
    payload["docs/Appendix2_software_bg.md"] = appendix.encode("utf-8")
    payload["docs/Appendix2_software_bg.docx"] = document
    payload["docs/PUBLISH_software_bg.md"] = (HERE / "PUBLISH_software_bg.md").read_bytes()
    requirements = []
    for path in ("requirements_lab08_ml.txt", "requirements_figures.txt", "requirements_lab10.txt"):
        for line in (HERE / path).read_text(encoding="utf-8").splitlines():
            if line.strip() and line not in requirements:
                requirements.append(line)
    payload["requirements_all.txt"] = ("\n".join(requirements) + "\n").encode("utf-8")
    environment = {"python": sys.version, "checked_on": "2026-11-06",
                   "packages": {name: version(name) for name in
                                ("numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "soundfile", "av", "xlrd")}}
    payload["TESTED_ENVIRONMENT.json"] = json.dumps(environment, indent=2).encode("utf-8")
    payload["SHA256SUMS.txt"] = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(payload.items())).encode("utf-8")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, data in payload.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for script in ("lab08/lab08_ml.py", "lab09/plot_lab_current.py", "lab10/lab10_vibroacoustics.py"):
            compile(payload[script], script, "exec")
            result = subprocess.run([sys.executable, "-I", "-X", "utf8", str(root / script), "--help"],
                                    cwd=root, capture_output=True, check=True)
            assert b"usage:" in result.stdout.lower()
        check = Document(root / "docs/Appendix2_software_bg.docx")
        text = "\n".join(p.text for p in check.paragraphs)
        assert all(label in text for label in ("П2.4.", "П2.5.", "П2.6.", "ПОПЪЛВА СЕ"))
        assert len(check.tables) == 1
        assert "**" not in text and "```" not in text
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            archive.writestr(NAME + "/" + name, data)
    zippath = save_new_version(HERE / (NAME + ".zip"), stream.getvalue())
    with zipfile.ZipFile(zippath) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {NAME + "/" + name for name in payload}
        assert all(archive.read(NAME + "/" + name) == data for name, data in payload.items())
    assert all(sha(path.read_bytes()) == digest for path, digest in protected.items())
    validation = {"appendix": docpath.name, "archive": zippath.name,
                  "archive_sha256": sha(zippath.read_bytes()), "archive_bytes": zippath.stat().st_size,
                  "files": sorted(payload), "script_hashes_match_standalone_sources": True,
                  "three_isolated_help_checks_passed": True, "existing_word_documents_unchanged": True,
                  "includes_measurements_or_credentials": False, "uploaded": False,
                  "download_and_dataset_urls": "explicit placeholders; not yet published"}
    (HERE / "software_appendix_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(f"Created {docpath.name} and {zippath.name}; {len(payload)} allowlisted files; isolated CLI checks passed.")


if __name__ == "__main__":
    main()