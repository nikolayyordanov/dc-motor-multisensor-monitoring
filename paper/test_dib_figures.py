"""Focused tests for the Data in Brief figure units, statistics and exports."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xlrd
from PIL import Image

import build_dib_article as figures


class FigureTests(unittest.TestCase):
    def test_amplitude_units_and_dc_for_even_and_odd_lengths(self):
        for n in (10000, 10001):
            fs = float(n)
            t = np.arange(n) / fs
            y = 0.4 + 0.25 * np.cos(2 * np.pi * 300 * t)
            freq, amplitude = figures.single_sided_amplitude(y, fs)
            self.assertAlmostEqual(amplitude[0], 0.4, places=6)
            self.assertAlmostEqual(amplitude[np.argmin(abs(freq - 300))], 0.25, places=6)
        _, amplitude = figures.single_sided_amplitude(0.3 * (-1.0) ** np.arange(10000), 10000)
        self.assertAlmostEqual(amplitude[-1], 0.3, places=6)

    def test_spot_statistics_match_source_cells(self):
        folder = figures.DATASET / "data/normal_no_reversal/vibration"
        data = figures.read_vibration_xls_dir(folder)
        self.assertTrue(any(data.values()))
        for qty, points in data.items():
            for speed, mean, sd, count in points:
                book = xlrd.open_workbook(str(folder / f"speed{speed:03d}_vibration.xls"))
                samples = [float(sheet.cell_value(row, 4)) for sheet in book.sheets()
                           for row in range(sheet.nrows) if sheet.ncols >= 5
                           and str(sheet.cell_value(row, 3)).strip() == qty]
                self.assertEqual(count, len(samples))
                self.assertAlmostEqual(mean, np.mean(samples))
                if count > 1:
                    self.assertAlmostEqual(sd, np.std(samples, ddof=1))
                else:
                    self.assertTrue(np.isnan(sd))
                book.release_resources()

    def test_current_preserves_recorded_volts(self):
        fs = 10000.0
        t = np.arange(20000) / fs
        y = 0.4 + 0.25 * np.cos(2 * np.pi * 300 * t)
        with patch.object(figures, "read_rigol_bin_segment", return_value=(t, y, fs)), \
                patch.object(figures, "export_figure_panels") as exporter:
            figures.fig2_current(Path("fig2_current.png"), Path("unused.bin"))
            fig, axes, _ = exporter.call_args.args
            self.assertEqual(axes[0].get_ylabel(), "Current signal (V)")
            self.assertEqual(axes[1].get_ylabel(), "Amplitude (V)")
            np.testing.assert_array_equal(axes[0].lines[0].get_ydata(), y[t <= 0.06])
            self.assertEqual(axes[1].texts[0].get_text(), "300 Hz (6 × 50 Hz converter ripple)")
            figures.plt.close(fig)

    def test_vibrometer_retains_silent_onset(self):
        y = np.concatenate([np.zeros(270), np.ones(5730) * 0.1])
        with patch.object(figures, "read_wav_mono", return_value=(y, 1000)), \
                patch.object(figures, "export_figure_panels") as exporter:
            figures.fig3_vibrometer(Path("fig3_vibrometer.png"), Path("unused.wav"))
            fig, axes, _ = exporter.call_args.args
            self.assertEqual(axes[0].get_ylabel(), "Amplitude (normalized)")
            np.testing.assert_array_equal(axes[0].lines[0].get_ydata(), y[:1001])
            figures.plt.close(fig)

    def test_export_names_and_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            fig, axes = figures.plt.subplots(1, 2, figsize=(4, 2))
            for ax in axes:
                ax.plot([0, 1], [0, 1])
                ax.set_ylabel("Value (V)")
            figures.export_figure_panels(fig, axes, Path(tmp) / "fig2_current.png")
            for stem in ("fig2_current", "fig2_current_a", "fig2_current_b"):
                for suffix in (".png", ".tif"):
                    with Image.open(Path(tmp) / (stem + suffix)) as image:
                        self.assertTrue(all(abs(dpi - 600) < 0.1 for dpi in image.info["dpi"]))
                        self.assertGreater(image.width, 100)
                        self.assertGreater(image.height, 100)


if __name__ == "__main__":
    unittest.main()