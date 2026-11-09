"""Independent rises, editable ROI geometry, and portable optical replay."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from core.live_sensor_contracts import load_canonical_live_layout
from baurods_demo.model import OpticalModel
from baurods_demo.light_check import LightCheckWindow, sliding_cue_plan
from baurods_demo.multi_rise import MultiRise
from baurods_demo.optical_rois import SIGNAL_PROFILE_KEY, layout_values, optical_layout, signal_profile, signal_values
from baurods_demo.recording import SessionRecorder
from baurods_demo.roi_editor import RoiEditor
from baurods_demo.runtime import FrameAnalysis, View
from baurods_demo.setup import DEFAULTS, SAMPLE, load_setup
from baurods_demo.sources import Replay
from baurods_demo.window import Window
from scripts.live_sensor_common import PROJECT_ROOT


class RiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.layout = load_canonical_live_layout(PROJECT_ROOT/"assets/live_sensor/roi_layout.json")

    def test_every_pair_has_independent_rise_and_release(self):
        for pair in combinations(range(9), 2):
            for spot in (False, True):
                d = MultiRise(spot=spot)
                b = np.array([12., 4., 20., .3, .6, .4, .1, .2, .05])
                for i in range(65):
                    v = b.copy()
                    pressed = pair if 15 <= i < 30 else pair[1:] if 30 <= i < 45 else ()
                    v[list(pressed)] += 4.
                    reading = d.update(i/15, v, b, np.full(9, .1))
                    if i in (24, 39, 54):
                        self.assertEqual(reading.rois, tuple(k+1 for k in pressed))

    def test_top_row_can_rise_while_other_rods_dim(self):
        d = MultiRise()
        base = np.full(9, 8.)
        for i in range(30):
            v = base.copy()
            if i >= 15:
                v[[0, 2]] += 3.
                v[[3, 4, 5]] = .01
            reading = d.update(i/15, v, base, np.full(9, .1))
        self.assertEqual(reading.rois, (1, 3))

    def test_sliding_keeps_constant_light_for_twenty_seconds_and_releases_separately(self):
        d = MultiRise(spot=True, sustained=True)
        b = np.arange(9, dtype=float)+2
        for i in range(400):
            v = b.copy()
            rods = (0, 2) if 15 <= i < 330 else (2,) if 330 <= i < 365 else ()
            v[list(rods)] += 5.
            reading = d.update(i/15, v, b, np.full(9, .1))
            if i in (30, 150, 320, 350, 390):
                self.assertEqual(reading.rois, tuple(k+1 for k in rods))
            if i == 320:
                self.assertTrue(all(abs(r.rate_v_s) < 1e-8 for r in reading.readings))
        # A release flash is insufficient to establish sustained light.
        d = MultiRise(spot=True, sustained=True)
        for i in range(45):
            v = b.copy()
            if i == 20:
                v[0] += 10
            self.assertFalse(d.update(i/15, v, b, np.full(9, .1)).rois)

    def test_sliding_light_moves_inside_roi_without_losing_identity(self):
        d = MultiRise(spot=True, sustained=True)
        for i in range(90):
            image = np.zeros((640, 480, 3), np.uint8)
            rods = (0, 2) if 15 <= i < 60 else (2,) if 60 <= i < 75 else ()
            for k in rods:
                r = self.layout.rois[k]
                x = r.x+8+(i % 20)
                image[r.y+25:r.y+32, x:x+7] = 80
            _, signal = signal_values(image, self.layout.rois)
            reading = d.update(i/15, signal, np.zeros(9), np.zeros(9))
            if i in (24, 45, 67, 85):
                self.assertEqual(reading.rois, tuple(k+1 for k in rods))

    def test_sliding_does_not_drop_a_lower_plateau_after_a_bright_flash(self):
        d = MultiRise(spot=True, sustained=True)
        for i in range(300):
            v = np.zeros(9)
            if 15 <= i < 25:
                v[[0, 2]] = 20.
            elif 25 <= i < 270:
                v[[0, 2]] = 1.
            reading = d.update(i/15, v, np.zeros(9), np.zeros(9))
            if 20 <= i < 270:
                self.assertEqual(reading.rois, (1, 3))
            if i >= 275:
                self.assertFalse(reading.rois)

    def test_common_lighting_noise_slow_drift_and_gap(self):
        b = np.arange(9, dtype=float)+2
        for change in (lambda v, i: v+4, lambda v, i: v*2, lambda v, i: v*.02,
                       lambda v, i: v+np.array([max(0, i-15)*.01]+[0.]*8)):
            d = MultiRise()
            for i in range(80):
                self.assertFalse(d.update(i/15, b if i < 15 else change(b.copy(), i), b, np.full(9, .1)).rois)
        d = MultiRise()
        for i in range(30):
            v = b.copy()
            if i >= 15:
                v[[0, 2]] += 1
            reading = d.update(i/15, v, b, [3., .1, .1, .1, .1, .1, .1, .1, .1])
        self.assertEqual(reading.rois, (3,))
        self.assertFalse(d.update(4., v, b, np.ones(9)).rois)
        with self.assertRaises(ValueError):
            d.update(4.1, [np.nan]*9, b, np.ones(9))

    def test_spatial_metric_rejects_hot_pixel_and_recovers_small_spot(self):
        image = np.zeros((640, 480, 3), np.uint8)
        r = self.layout.rois[0]
        image[r.y+20, r.x+20] = 255
        mean, spot = signal_values(image, self.layout.rois)
        self.assertEqual(spot[0], 0.)
        self.assertGreater(mean[0], 0.)
        image[r.y+30:r.y+35, r.x+30:r.x+35] = 60
        mean, spot = signal_values(image, self.layout.rois)
        self.assertGreater(spot[0], 20*mean[0]/2)
        d = MultiRise(spot=True)
        for i in range(25):
            reading = d.update(i/15, np.zeros(9) if i < 15 else spot, np.zeros(9), np.zeros(9))
        self.assertEqual(reading.rois, (1,))

    def test_layout_validation_rejects_overlap_bounds_and_identity(self):
        original = layout_values(self.layout)
        self.assertEqual(optical_layout(original, self.layout).roi_layout_id, self.layout.roi_layout_id)
        for key, value in (("width", 7), ("x", -1), ("y", 639), ("roi_id", 2), ("x", 1.5)):
            rows = deepcopy(original)
            rows[0][key] = value
            with self.assertRaises(ValueError):
                optical_layout(rows, self.layout)
        rows = deepcopy(original)
        rows[0].update(x=rows[1]["x"], y=rows[1]["y"])
        with self.assertRaises(ValueError):
            optical_layout(rows, self.layout)
        self.assertEqual(layout_values(self.layout), original)

    def test_editor_drag_save_cancel_reset_and_preview_only_gain(self):
        committed = []
        image = np.full((640, 480, 3), 5, np.uint8)
        dlg = RoiEditor(None, self.layout, self.layout, image, lambda x: committed.append(x) or True)
        dlg.show()
        self.app.processEvents()
        scale, x, y = dlg.canvas.transform()
        r = self.layout.rois[0]
        start = QPoint(round(x+r.center_x*scale), round(y+r.center_y*scale))
        end = start+QPoint(round(5*scale), 0)
        QTest.mousePress(dlg.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(dlg.canvas, end)
        QTest.mouseRelease(dlg.canvas, Qt.MouseButton.LeftButton, pos=end)
        self.assertAlmostEqual(dlg.canvas.rois[0].x, r.x+5, delta=1)
        dlg.brightness.setCurrentIndex(3)
        np.testing.assert_array_equal(dlg.original, image)
        dlg.fields["x"].setValue(470)
        self.assertFalse(dlg.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
        dlg.restore_defaults()
        self.assertEqual(dlg.values(), layout_values(self.layout))
        dlg.fields["width"].setValue(r.width-4)
        dlg.save()
        self.assertEqual(committed[0][0]["width"], r.width-4)
        cancelled = RoiEditor(None, self.layout, self.layout, image, lambda x: committed.append(x) or True)
        cancelled.fields["width"].setValue(r.width-8)
        cancelled.reject()
        self.assertEqual(len(committed), 1)

    def test_window_persists_regions_and_invalidates_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Window(output=tmp)
            w.timer.stop()
            rows = layout_values(self.layout)
            rows[0]["width"] -= 4
            w.settings["physical_mapping"] = {"old": "mapping"}
            self.assertTrue(w.apply_rois(rows))
            saved = load_setup(tmp)
            self.assertEqual(saved["optical_rois"], rows)
            self.assertEqual(saved["display_mode"], "multi_v_rise")
            self.assertIsNone(saved["physical_mapping"])
            self.assertEqual(w.idle.status, "CALIBRATION REQUIRED")
            self.assertEqual(w.camera.rois[0].width, rows[0]["width"])
            w.close()

    def test_sliding_check_waits_for_operator_and_targets_selected_rods(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = LightCheckWindow(output=tmp, sliding=True, rois=(1, 3))
            w.timer.stop()
            w.cue_timer.stop()
            self.assertEqual(w.rule.currentData(), "multi_slide")
            self.assertEqual(w.check_button.text(), "Start sliding check")
            self.assertIsNone(w.session)
            self.assertEqual(w.plan, sliding_cue_plan((1, 3)))
            self.assertIn(("slide_R1_R3", 8., "Slide the rods inside camera R1 + R3 together"), w.plan)
            w.close()
        with self.assertRaises(ValueError):
            LightCheckWindow(sliding=True, rois=(1, 1))

    def test_custom_spot_regions_record_replay_and_leave_raw_model_geometry_fixed(self):
        settings = json.loads(DEFAULTS.read_text())
        model = OpticalModel(settings)
        rows = layout_values(model.layout)
        rows[0].update(x=20, y=20, width=20, height=20)
        rows[1].update(x=60, y=20, width=20, height=20)
        custom = optical_layout(rows, model.layout)
        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(1) as pool:
            source = Replay(SAMPLE/"unloaded/session_video.mp4", model.layout)
            writer = None
            try:
                info = source.open()
                first = source.read()
                analysis = FrameAnalysis(model, source, info, Path(tmp), pool, "multi_spot", regions=custom)
                status, _, raw = analysis.analyze(first)
                self.assertEqual(status, "CALIBRATION REQUIRED")
                self.assertIsNone(raw)
                baseline = source.baselines[first.baseline_key]
                baseline.camera_settings[SIGNAL_PROFILE_KEY] = signal_profile([first]*30, custom)
                analysis.reset_history()
                config = dict(settings, display_mode="multi_spot", optical_rois=rows)
                writer = SessionRecorder(tmp, config, model, info, None)
                expected = []
                for i in range(60):
                    image = first.image.copy()
                    rods = (0, 1) if 15 <= i < 30 else (1,) if 30 <= i < 45 else ()
                    for k in rods:
                        r = custom.rois[k]
                        image[r.y:r.y+r.height, r.x:r.x+r.width] = 80
                    frame = replace(first, number=i, t=i/15, image=image)
                    status, detail, raw = analysis.analyze(frame)
                    state = View(status, detail, frame, result=raw, optical=analysis.optical, change=analysis.change)
                    expected.append((raw["contact"], raw["localization"], state.change.rois))
                    writer.frame(frame, state, analysis.baseline, analysis.epoch)
                self.assertEqual(expected[24][2], (1, 2))
                self.assertEqual(expected[39][2], (2,))
                self.assertEqual(expected[54][2], ())
                self.assertEqual(len({r[:2] for r in expected}), 1)
                self.assertEqual(model.layout.roi_layout_id, self.layout.roi_layout_id)
            finally:
                source.close()
                if writer:
                    writer.close("REPLAY COMPLETE")
            replay = Replay(writer.path/"session_video.avi", model.layout)
            try:
                info = replay.open()
                model.predictor.reset()
                analysis = FrameAnalysis(model, replay, info, Path(tmp), pool, "multi_spot")
                actual = []
                while (frame := replay.read()) is not None:
                    _, _, raw = analysis.analyze(frame)
                    actual.append((raw["contact"], raw["localization"], analysis.change.rois))
                self.assertEqual(actual, expected)
                self.assertEqual(analysis.regions.roi_layout_id, custom.roi_layout_id)
            finally:
                replay.close()
