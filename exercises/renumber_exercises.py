"""One-time safe numbering migration, then reproducible builds and checks.

New numbering: 08 = machine learning; 09 = current-signal analysis.
Original documents and superseded outputs are retained, never deleted.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile

from docx import Document

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARCHIVE = HERE / "archive_before_renumbering"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare():
    manifest = ARCHIVE / "manifest.json"
    if manifest.exists():
        return
    # Stage all script renames first: inspect_lab09.py is both source and target.
    moves = {
        "build_lab08_figures.py": "build_lab09_figures.py",
        "build_lab09.py": "build_lab08.py",
        "test_lab08.py": "test_lab09.py",
        "inspect_lab09.py": "inspect_lab08.py",
        "inspect_lab.py": "inspect_lab09.py",
        "requirements_lab09.txt": "requirements_lab08.txt",
    }
    for old, new in moves.items():
        if not (HERE / old).exists():
            raise FileNotFoundError(old)
        if (HERE / new).exists() and new not in moves:
            raise FileExistsError(new)
    names = ["Lab08.docx", "Lab08_with_figures.docx", "Lab09.doc",
             "Lab08_revised.docx", "Lab08_revised_withtrackchanges.docx",
             "Lab09_revised.docx", "Lab09_working.docx",
             "lab08_source_text.txt", "lab09_source_text.txt",
             "figures_lab08", "figures_lab09", "figures_lab08_shared",
             "plot_lab_current.zip"]
    existing = [HERE / name for name in names if (HERE / name).exists()]
    checksums = {}
    for path in existing:
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        checksums.update({p.relative_to(HERE).as_posix(): sha(p) for p in files if p.is_file()})
    ARCHIVE.mkdir(exist_ok=True)
    for path in existing:
        if (ARCHIVE / path.name).exists():
            raise FileExistsError(ARCHIVE / path.name)
    # Move, do not overwrite or delete any user document (including tracked changes).
    for path in existing:
        path.rename(ARCHIVE / path.name)
    for old in moves:
        (HERE / old).rename(HERE / (old + ".renumber_stage"))
    for old, new in moves.items():
        (HERE / (old + ".renumber_stage")).rename(HERE / new)
    shutil.copy2(ARCHIVE / "Lab09_working.docx", HERE / "Lab08_working.docx")
    manifest.write_text(json.dumps({"sha256": checksums, "script_renames": moves},
                                   indent=2, ensure_ascii=False), encoding="utf-8")


def run(script, *args):
    subprocess.run([sys.executable, str(HERE / script), *args], cwd=ROOT, check=True)


def embedded_objects(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()
                if name.startswith("word/embeddings/")}


def verify():
    manifest = json.loads((ARCHIVE / "manifest.json").read_text(encoding="utf-8"))
    for name, checksum in manifest["sha256"].items():
        assert sha(ARCHIVE / name) == checksum, name
    results = {}
    current_shapes = len(Document(ARCHIVE / "Lab08.docx").inline_shapes) + 2
    for number, expected_shapes in ((8, 4), (9, current_shapes)):
        path = HERE / f"Lab{number:02d}_revised.docx"
        doc = Document(path)
        paragraphs = doc.element.xpath(".//w:p")
        text = "\n".join("".join(p.xpath(".//w:t/text()")) for p in paragraphs)
        assert f"УПРАЖНЕНИЕ № {number}" in text
        other = 9 if number == 8 else 8
        assert not re.search(rf"\b(?:{other}|10)\.\d+", text), path.name
        assert len(doc.inline_shapes) == expected_shapes, (number, len(doc.inline_shapes))
        for i in range(1, 5 if number == 8 else 7):
            assert f"Фиг. {number}.{i}." in text
        assert "[Място за фигура" not in text
        results[path.name] = {"numbering_verified": True, "inline_shapes": len(doc.inline_shapes)}
    assert embedded_objects(HERE / "Lab08_revised.docx") == embedded_objects(ARCHIVE / "Lab09_working.docx")
    # Numbering is the only requested change: numerical outputs must be identical.
    for new, old in (("figures_lab08/classification_metrics.csv", "figures_lab09/classification_metrics.csv"),
                     ("figures_lab08/features_predictions.csv", "figures_lab09/features_predictions.csv"),
                     ("figures_lab09/example_metrics.csv", "figures_lab08/example_metrics.csv")):
        assert (HERE / new).read_bytes() == (ARCHIVE / old).read_bytes(), new
    with zipfile.ZipFile(HERE / "plot_lab_current.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("plot_lab_current.py", "requirements_figures.txt", "README_figures_bg.md"):
            archive.write(HERE / name, name)
    results["archived_files_sha256_verified"] = len(manifest["sha256"])
    results["legacy_equation_binaries_preserved"] = True
    results["numerical_results_unchanged"] = True
    (HERE / "numbering_validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Numbering verified: ML=08, current=09; originals and numerical results unchanged.")


if __name__ == "__main__":
    prepare()
    run("build_lab09_figures.py")
    run("plot_lab_current.py", str(ROOT / "DCData_mendeley"), "--output", str(HERE / "figures_lab09_shared"))
    run("build_lab08.py", "--reuse-results")
    run("test_lab09.py")
    verify()