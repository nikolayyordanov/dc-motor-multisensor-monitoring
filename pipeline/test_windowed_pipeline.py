#!/usr/bin/env python3
"""Focused tests for leakage-safe signal windowing and group folds."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_hypothesis import (
    build_paired_manifest,
    evaluate_modality,
    extract_features_for_modality,
    get_group_folds,
    iter_window_bounds,
)


class WindowingTests(unittest.TestCase):
    def test_two_second_windows_with_half_overlap(self):
        bounds = list(iter_window_bounds(18 * 16_000, 16_000, 2.0, 0.5))

        self.assertEqual(len(bounds), 17)
        self.assertEqual(bounds[0], (0, 0, 32_000))
        self.assertEqual(bounds[-1], (16, 256_000, 288_000))

    def test_partial_tail_is_not_emitted(self):
        bounds = list(iter_window_bounds(40_001, 20_000, 2.0, 0.5))

        self.assertEqual(bounds, [(0, 0, 40_000)])

    def test_group_folds_are_disjoint(self):
        rows = []
        for condition_index in range(8):
            for sample_index in range(10):
                rows.append({
                    "group_id": f"c{condition_index}_g{sample_index}",
                    "condition": f"condition_{condition_index}",
                })
        manifest = pd.DataFrame(rows)

        folds = get_group_folds(manifest, n_splits=5, seed=42)

        self.assertEqual(len(folds), 5)
        for train_groups, test_groups in folds:
            self.assertFalse(train_groups & test_groups)
            self.assertEqual(train_groups | test_groups, set(manifest["group_id"]))

    def test_real_vibrometer_uses_longest_common_span(self):
        workspace = Path(__file__).resolve().parent.parent
        dataset_root = workspace / "DCData_mendeley"
        if not (dataset_root / "metadata.csv").exists():
            self.skipTest("Dataset is not available")
        manifest = build_paired_manifest(dataset_root).head(1)

        modality_features = {
            modality: extract_features_for_modality(
                manifest,
                modality,
                offset_s=1.0,
                max_s=None,
                window_s=2.0,
                window_overlap=0.5,
                target_fs_audio=16_000.0,
                target_fs_current=20_000.0,
            )
            for modality in ("sound_phone", "sound_vibrometer", "current")
        }
        features = modality_features["sound_vibrometer"]

        available_s = float(manifest["common_duration_s"].iloc[0]) - 1.0
        used_s = float(features["segment_end_s"].iloc[-1]) - 1.0

        self.assertEqual(len({len(frame) for frame in modality_features.values()}), 1)
        self.assertGreaterEqual(len(features), 1)
        self.assertEqual(features["group_id"].nunique(), 1)
        self.assertAlmostEqual(features["segment_start_s"].iloc[0], 1.0)
        self.assertLessEqual(used_s, available_s + 1.0 / 16_000.0)
        self.assertLess(available_s - used_s, 1.0)

    def test_short_current_recording_is_excluded(self):
        workspace = Path(__file__).resolve().parent.parent
        dataset_root = workspace / "DCData_mendeley"
        if not (dataset_root / "metadata.csv").exists():
            self.skipTest("Dataset is not available")

        manifest = build_paired_manifest(dataset_root)

        self.assertEqual(len(manifest), 97)
        self.assertNotIn("normal_with_reversal__100", set(manifest["group_id"]))
        self.assertGreaterEqual(manifest["duration_current"].min(), 20.0 - 1e-3)

    def test_evaluation_aggregates_segments_to_recordings(self):
        rows = []
        for group_index in range(8):
            label = "normal" if group_index % 2 == 0 else "fault"
            for segment_index in range(3):
                rows.append({
                    "group_id": f"group_{group_index}",
                    "segment_id": f"group_{group_index}__seg{segment_index}",
                    "segment_index": segment_index,
                    "segment_start_s": float(segment_index),
                    "segment_end_s": float(segment_index + 1),
                    "condition": label,
                    "operation": label,
                    "reversal": "no",
                    "speed_percent": float(group_index * 10),
                    "modality": "test",
                    "path": "synthetic",
                    "feature": float(label == "fault") + segment_index * 0.01,
                })
        features = pd.DataFrame(rows)
        folds = [
            (
                {f"group_{index}" for index in range(4)},
                {f"group_{index}" for index in range(4, 8)},
            )
        ]

        metrics, predictions = evaluate_modality(
            features,
            folds,
            seed=42,
            n_estimators=20,
        )

        self.assertEqual(len(metrics), 1)
        self.assertEqual(len(predictions), 4)
        self.assertTrue(np.all(predictions["n_segments"] == 3))
        self.assertEqual(predictions["group_id"].nunique(), 4)


if __name__ == "__main__":
    unittest.main()