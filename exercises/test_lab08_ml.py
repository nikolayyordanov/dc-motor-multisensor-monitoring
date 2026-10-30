"""Unit checks and an isolated, real-data smoke test of the distributable ZIP."""
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd
from PIL import Image

import lab08_ml as ml

HERE = Path(__file__).resolve().parent
FILES = ("lab08_ml.py", "requirements_lab08_ml.txt", "README_lab08_ml_bg.md")


class StandaloneTests(unittest.TestCase):
    def test_features_sine_and_zero_energy(self):
        y = 0.25 * np.sin(2 * np.pi * 300 * np.arange(22050) / 44100)
        values = ml.window_features(y, 44100)
        self.assertAlmostEqual(values[0], .25 / np.sqrt(2), places=10)
        self.assertAlmostEqual(values[2], np.sqrt(2), places=3)
        self.assertAlmostEqual(values[3], 1.5, places=10)
        self.assertAlmostEqual(values[6], 1, places=10)  # 250–500 Hz
        self.assertLessEqual(sum(values[4:]), 1.00000000001)
        for bad in (np.zeros(22050), np.full(22050, np.nan)):
            with self.assertRaises(ValueError):
                ml.window_features(bad, 44100)

    def test_majority_tie(self):
        self.assertEqual(ml.majority(np.array([2, 1, 2, 1])), 1)

    def test_metadata_missing_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pd.DataFrame({"sensor": ["bad"]}).to_csv(root / "metadata.csv", index=False)
            with self.assertRaises(ValueError):
                ml.select_records(root)
            rows = [{"sensor": "sound_vibrometer", "condition": condition, "speed_percent": speed,
                     "new_path": f"{condition}_{speed}.wav"}
                    for condition in ml.CONDITIONS for speed in range(1, 6)]
            rows.append(rows[0])
            pd.DataFrame(rows).to_csv(root / "metadata.csv", index=False)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                ml.select_records(root)

    def test_protect_dataset_and_nonempty_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for output in (root, root / "results"):
                with self.assertRaises(SystemExit) as exc:
                    ml.main([str(root), "--output", str(output)])
                self.assertEqual(exc.exception.code, 1)
            with tempfile.TemporaryDirectory() as another:
                (Path(another) / "keep.txt").write_text("keep", encoding="utf-8")
                with self.assertRaises(SystemExit):
                    ml.main([str(root), "--output", another])
                self.assertEqual((Path(another) / "keep.txt").read_text(encoding="utf-8"), "keep")


def integration():
    bundle = HERE / "lab08_ml.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(HERE / name, name)
    output = HERE / "results_lab08_shared"
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Choose a new test output; existing results will not be overwritten")
    dataset = HERE.parent / "DCData_mendeley"
    doc_hashes = {path: ml.sha(path) for path in HERE.glob("*.docx")}
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(bundle) as archive:
            if set(archive.namelist()) != set(FILES):
                raise AssertionError("Unexpected distributable files")
            archive.extractall(folder)
        # Isolated mode: excludes the repository/current directory from sys.path.
        subprocess.run([sys.executable, "-I", str(Path(folder) / "lab08_ml.py"),
                        str(dataset), "--output", str(output)], cwd=folder, check=True)
        subprocess.run([sys.executable, "-I", str(Path(folder) / "lab08_ml.py"), "--help"],
                       cwd=folder, check=True, stdout=subprocess.DEVNULL)
    info = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert (info["recordings"], info["windows"]) == (36, 1599)
    assert info["speeds"] == [1, 2, 5, 10, 20, 30, 40, 50, 60]
    assert info["rf_n_jobs"] == 1
    assert all(ml.sha(dataset / source["path"]) == source["sha256"] for source in info["sources"])
    frame = pd.read_csv(output / "features_predictions.csv")
    reference = pd.read_csv(HERE / "figures_lab08/features_predictions.csv")
    pd.testing.assert_frame_equal(frame[["record", "speed", "class", "window"]],
                                  reference[["record", "speed", "class", "window"]])
    np.testing.assert_allclose(frame[ml.FEATURES], reference[ml.FEATURES], rtol=1e-12, atol=1e-14)
    np.testing.assert_array_equal(frame.fold, reference.fold)
    assert frame.groupby("record").fold.nunique().eq(1).all()
    metrics = pd.read_csv(output / "classification_metrics.csv")
    approved = pd.read_csv(HERE / "figures_lab08/classification_metrics.csv")
    np.testing.assert_allclose(metrics[["accuracy_record", "macro_f1_record"]],
                               approved[["accuracy_record", "macro_f1_record"]], rtol=1e-12)
    records = pd.read_csv(output / "record_predictions.csv")
    assert records.groupby(["features", "model"]).size().eq(36).all()
    for stem in ("fig8_3_features", "fig8_4_confusion"):
        for ext in ("png", "pdf", "svg"):
            assert (output / f"{stem}.{ext}").stat().st_size > 1000
        with Image.open(output / f"{stem}.png") as image:
            assert abs(image.info["dpi"][0] - 600) < .1
    for filename in ("table8_2_classification.csv", "table8_3_feature_comparison.csv"):
        assert pd.read_csv(output / filename).shape == (3, 4 if "comparison" in filename else 3)
    assert all(ml.sha(path) == digest for path, digest in doc_hashes.items())
    report = {"zip": bundle.name, "isolated_execution": True, "recordings": 36, "windows": 1599,
              "features_and_folds_match_approved": True, "record_metrics_match_approved": True,
              "source_and_word_hashes_verified": True, "zip_sha256": ml.sha(bundle),
              "versions": info["versions"]}
    (HERE / "lab08_ml_package_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Standalone ZIP verified in an isolated folder; sources and Word files unchanged.")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StandaloneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    integration()