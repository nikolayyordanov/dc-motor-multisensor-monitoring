"""Build the code-only ZIP named in the author's Appendix 1; never edit Word files."""
import argparse
from datetime import date
import hashlib
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
NAME = "labs_8_9_10_software_v1.0"
FILES = {
    # Keep internal source names compatible with existing builders and tests.
    "lab8/lab8_ml.py": "lab08_ml.py",
    "lab9/plot_lab_current.py": "plot_lab_current.py",
    "lab10/lab10_vibroacoustics.py": "lab10_vibroacoustics.py",
}
START = """# Програмни средства за упражнения №8, №9 и №10

Кодът е в lab8/, lab9/, lab10/. Подробната методика е в Приложение 1
на лабораторното ръководство, което не е включено в този архив.

Изисква 64-битов Python 3.11+. Разархивирайте пакета извън измерванията.
Инсталиране за трите упражнения от основната папка:

```text
python -m pip install -r requirements_all.txt
python lab8/lab8_ml.py "C:/work/DCData_mendeley" --output "../results8"
python lab9/plot_lab_current.py "C:/work/DCData_mendeley" --output "../results9"
python lab10/lab10_vibroacoustics.py "C:/work/DCData_mendeley" --output "../results10"
```

Пътят към набора се заменя с действителния. За параметри използвайте --help.
Създавайте отделни изходни папки. №9 замества съществуващите резултати със
същите имена; №8/10 изискват --overwrite при непразна изходна папка.
Не са нужни Word/Excel или други проектни програми. Библиотеките се
инсталират отделно, не са включени в ZIP. Данните също не са включени;
запазете структурата metadata.csv и data/ и спазвайте лиценза на набора.

"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip-only", action="store_true", help="Compatibility option; builds always update only the ZIP")
    parser.parse_args()
    protected = {p: sha(p.read_bytes()) for pattern in ("*.doc", "*.docx") for p in HERE.glob(pattern)
                 if not p.name.startswith("~$")}
    payload = {target: (HERE / source).read_bytes() for target, source in FILES.items()}
    payload["README_START_BG.md"] = START.encode("utf-8")
    requirements = []
    for path in ("requirements_lab08_ml.txt", "requirements_figures.txt", "requirements_lab10.txt"):
        for line in (HERE / path).read_text(encoding="utf-8").splitlines():
            if line.strip() and line not in requirements:
                requirements.append(line)
    payload["requirements_all.txt"] = ("\n".join(requirements) + "\n").encode("utf-8")
    environment = {"python": sys.version, "checked_on": date.today().isoformat(),
                   "packages": {name: version(name) for name in
                                ("numpy", "pandas", "scipy", "matplotlib", "scikit-learn", "soundfile", "av", "xlrd")}}
    assert len(payload) == 5
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, data in payload.items():
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for script in FILES:
            compile(payload[script], script, "exec")
            result = subprocess.run([sys.executable, "-I", "-X", "utf8", str(root / script), "--help"],
                                    cwd=root, capture_output=True, check=True)
            assert b"usage:" in result.stdout.lower()
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
    validation = {"appendix": "17. Приложение 1.doc", "archive": zippath.name,
                  "archive_sha256": sha(zippath.read_bytes()), "archive_bytes": zippath.stat().st_size,
                  "files": sorted(payload), "script_hashes_match_standalone_sources": True,
                  "tested_environment": environment, "appendix_rebuilt": False,
                  "archive_to_source": FILES,
                  "protected_document_hashes": {p.name: digest for p, digest in protected.items()},
                  "three_isolated_help_checks_passed": True, "existing_word_documents_unchanged": True,
                  "includes_measurements_or_credentials": False, "uploaded": False,
                  "download_url": "https://drive.google.com/file/d/1LlVQMX3yqZYAH65RPqLYxUDout2uI_2R/view?usp=drive_link",
                  "dataset_url": "explicit placeholder; not provided"}
    (HERE / "software_appendix_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(f"Created {zippath.name}; {len(payload)} allowlisted files; isolated CLI checks passed; Word files unchanged.")


if __name__ == "__main__":
    main()