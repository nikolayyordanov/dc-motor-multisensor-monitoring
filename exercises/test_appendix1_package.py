"""Check the renamed ZIP against the author's Appendix 1, without retraining."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import zipfile

from docx import Document
import pandas as pd

import build_software_appendix as package

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inspection = json.loads((HERE / "review_appendix1/inspection.json").read_text(encoding="utf-8"))
    source = HERE / inspection["source"]
    assert sha(source) == inspection["source_sha256"], "Original author DOC changed"
    document = Document(HERE / "review_appendix1/Appendix1_review.docx")
    text = "\n".join(p.text for p in document.paragraphs)
    assert package.NAME + ".zip" in text
    scripts = {row.cells[2].text.strip() for row in document.tables[0].rows[1:]}
    assert scripts == set(package.FILES)
    documented_commands = re.findall(r"^python (\S+\.py)", text, flags=re.MULTILINE)
    assert set(documented_commands) == scripts
    archive_path = HERE / (package.NAME + ".zip")
    expected = scripts | {"README_START_BG.md", "requirements_all.txt"}
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {package.NAME + "/" + name for name in expected}
        for target, original in package.FILES.items():
            assert archive.read(package.NAME + "/" + target) == (HERE / original).read_bytes()
        readme = archive.read(package.NAME + "/README_START_BG.md").decode("utf-8")
        assert "Приложение 1" in readme and "Приложение 2" not in readme
        assert set(re.findall(r"^python (\S+\.py)", readme, flags=re.MULTILINE)) == scripts
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive.extractall(root)
            script = root / package.NAME / "lab8/lab8_ml.py"
            spec = importlib.util.spec_from_file_location("appendix1_ml", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = root / "results"
            output.mkdir()
            metrics = pd.read_csv(HERE / "figures_lab08/classification_metrics.csv")
            module.save_tables(metrics, output)
            assert "tables_lab8.md" in text
            assert (output / "tables_lab8.md").is_file()
            assert not (output / "tables_lab08.md").exists()
            for name in ("table8_2_classification.csv", "table8_3_feature_comparison.csv"):
                pd.testing.assert_frame_equal(pd.read_csv(output / name),
                                             pd.read_csv(HERE / "results_lab08_shared" / name))
    report = json.loads((HERE / "software_appendix_validation.json").read_text(encoding="utf-8"))
    assert report["archive"] == archive_path.name
    assert report["archive_sha256"] == sha(archive_path)
    assert not report["appendix_rebuilt"]
    assert all(sha(HERE / name) == digest for name, digest in report["protected_document_hashes"].items())
    result = {"author_document": source.name, "author_document_unchanged": True,
              "archive": archive_path.name, "archive_sha256": sha(archive_path),
              "five_files_only": True, "names_match_author_appendix": True,
              "readme_commands_match": True, "table_filename_matches": True,
              "numerical_tables_unchanged": True, "all_existing_word_documents_unchanged": True}
    (HERE / "appendix1_package_validation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PASS: Appendix 1 names, five ZIP files, README commands, table export and unchanged Word files.")


if __name__ == "__main__":
    main()