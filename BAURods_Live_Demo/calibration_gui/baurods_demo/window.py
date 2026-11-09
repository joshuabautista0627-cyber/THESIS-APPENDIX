"""BAURods defense display and operator controls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QStackedWidget, QTabWidget,
    QVBoxLayout, QWidget)

from core.live_sensor_contracts import load_canonical_live_layout
from scripts.live_sensor_common import PROJECT_ROOT
from .runtime import Session, View
from .optical_change import MODE_LABELS, MultiReading
from .optical_rois import SPOT_MODES, optical_layout
from .roi_editor import RoiEditor
from .setup import DEFAULTS, OUTPUT, SAMPLE, load_setup, save_setup, verified_mapping
from .sources import LIVE, REPLAY
from .widgets import CameraView, MappingDialog, OpticalStrip, label


STYLE = """
QMainWindow, QDialog, QWidget#root { background: #101b26; }
QWidget { color: #eef3f4; font: 10pt 'Segoe UI'; }
QFrame#card, QFrame#bar { background: #172633; border: 1px solid #324351; border-radius: 9px; }
QLabel { background: transparent; }
QLabel#brand { color: #85e5d2; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 28px; font-weight: 650; }
QLabel#sectionTitle { font-size: 17px; font-weight: 650; }
QLabel#muted, QCheckBox { color: #bed0d9; }
QLabel#small { color: #aac0cc; font-size: 11px; }
QLabel#taxel, QLabel#mappingCell { background: #203340; border: 1px solid #425b6b; border-radius: 6px;
                                   font-size: 24px; color: #cedfe5; font-weight: 600; }
QLabel#taxel[active="true"] { background: #7ce8ca; border: 3px solid #c8fff1; color: #092c26; }
QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #223542; color: #e8f2f4; border: 1px solid #405867; border-radius: 5px;
    padding: 5px 9px; min-height: 19px; }
QPushButton:hover, QComboBox:hover { background: #2b4555; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #a3f4dc; }
QPushButton#primary { background: #82e7cd; color: #0a302a; border-color: #82e7cd; font-weight: 700; }
QPushButton:disabled, QSpinBox:disabled, QComboBox:disabled { color: #8da1ad; background: #1c2b36; border-color: #344450; }
QPushButton#primary:disabled { background: #28483f; color: #a1b5ac; }
QComboBox QAbstractItemView, QPlainTextEdit, QTabWidget::pane, QTabBar::tab { background: #20313f; color: #edf4f5; }
QTabBar::tab { padding: 7px 14px; } QTabBar::tab:selected { background: #365463; }
QCheckBox::indicator { width: 15px; height: 15px; }
"""


def card():
    box = QFrame()
    box.setObjectName("card")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(15, 12, 15, 12)
    layout.setSpacing(7)
    return box, layout


class Window(QMainWindow):
    def __init__(self, *, output=OUTPUT, replay=None, session_factory=Session):
        super().__init__()
        # Offscreen Qt on Windows has no system font database during rehearsal tests.
        if os.name == "nt" and "Segoe UI" not in QFontDatabase.families():
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for filename in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
                QFontDatabase.addApplicationFont(str(fonts / filename))
        self.output, self.session_factory = Path(output), session_factory
        self.session = self.mapping_dialog = self.roi_dialog = None
        self.reference_frame = None
        self.layout_reset_pending = False
        self.last_frame = self.last_grid = self.last_status = None
        self.initial_error = ""
        self.close_started = None
        try:
            self.settings = load_setup(output)
            self.canonical_layout = load_canonical_live_layout(PROJECT_ROOT / self.settings["roi_layout"])
            self.layout_spec = optical_layout(self.settings.get("optical_rois"), self.canonical_layout)
            if self.settings["display_mode"] == "models":
                self.layout_spec = self.canonical_layout
        except Exception as exc:
            self.initial_error = str(exc)
            self.settings = json.loads(DEFAULTS.read_text())
            self.layout_spec = None
            self.canonical_layout = None
        if replay is not None:
            self.settings["replay"] = str(replay)
        self.setWindowTitle("BAURods Live Demo")
        self.resize(1150, 745)
        self.setMinimumSize(855, 580)
        self.setStyleSheet(STYLE)
        base = QWidget()
        base.setObjectName("root")
        self.setCentralWidget(base)
        root = QVBoxLayout(base)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)
        heading = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(0)
        title_group.addWidget(label("MECHANOLUMINESCENT VISUOTACTILE SENSOR", "brand"))
        title_group.addWidget(label("BAURods Live Demo", "title"))
        heading.addLayout(title_group, 1)
        self.advanced = QPushButton("Advanced…")
        self.advanced.clicked.connect(self.settings_dialog)
        self.full = QPushButton("Full screen  ·  F11")
        self.full.clicked.connect(self.fullscreen)
        heading.addWidget(self.advanced)
        heading.addWidget(self.full)
        root.addLayout(heading)
        bar = QFrame()
        bar.setObjectName("bar")
        controls = QHBoxLayout(bar)
        controls.setContentsMargins(12, 8, 12, 8)
        self.mode = QComboBox()
        self.mode.addItems([LIVE, REPLAY])
        self.mode.setAccessibleName("Input mode")
        controls.addWidget(self.mode)
        self.inputs = QStackedWidget()
        camera_row = QWidget()
        index_row = QHBoxLayout(camera_row)
        index_row.setContentsMargins(0, 0, 0, 0)
        index_row.addWidget(label("Camera index", "muted"))
        self.index = QSpinBox()
        self.index.setRange(0, 99)
        self.index.setValue(self.settings["camera_index"])
        index_row.addWidget(self.index)
        index_row.addStretch()
        self.inputs.addWidget(camera_row)
        video_row = QWidget()
        video = QHBoxLayout(video_row)
        video.setContentsMargins(0, 0, 0, 0)
        self.clips = QComboBox()
        self.clips.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.clips.setMinimumWidth(110)
        self.clips.addItem("Center press", str(SAMPLE / "center_press/session_video.mp4"))
        self.clips.addItem("Unloaded control", str(SAMPLE / "unloaded/session_video.mp4"))
        self.select_video(PROJECT_ROOT / self.settings["replay"])
        video.addWidget(self.clips, 1)
        self.browse = QPushButton("Open…")
        self.browse.clicked.connect(self.browse_video)
        video.addWidget(self.browse)
        self.inputs.addWidget(video_row)
        controls.addWidget(self.inputs, 1)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.baseline_button = QPushButton("Capture unloaded baseline")
        self.baseline_button.clicked.connect(self.capture_baseline)
        self.record = QCheckBox("Record session")
        self.record.setToolTip("Write lossless video, capture timing, raw scores and displayed predictions from Start to Stop.")
        for item in [self.start_button, self.stop_button, self.baseline_button, self.record]:
            controls.addWidget(item)
        root.addWidget(bar)
        panels = QHBoxLayout()
        panels.setSpacing(10)
        left, content = card()
        cam_title = QHBoxLayout()
        cam_title.addWidget(label("Underside camera", "sectionTitle"), 1)
        self.overlay = QCheckBox("Numbered ROIs")
        self.overlay.setChecked(bool(self.settings["overlay"]))
        self.overlay.toggled.connect(self.toggle_overlay)
        cam_title.addWidget(self.overlay)
        self.roi_button = QPushButton("Edit ROIs…")
        self.roi_button.setToolTip("Start the camera preview, then edit optical regions. Editing stops acquisition; Save and capture a fresh baseline.")
        self.roi_button.clicked.connect(self.edit_rois)
        cam_title.addWidget(self.roi_button)
        content.addLayout(cam_title)
        self.camera = CameraView(self.layout_spec)
        self.camera.overlay = self.overlay.isChecked()
        content.addWidget(self.camera, 1)
        self.camera_line = label("Raw 640 × 480   /   Oriented 480 × 640", "small")
        content.addWidget(self.camera_line)
        self.optical_title = label("", "small")
        content.addWidget(self.optical_title)
        self.optics = OpticalStrip()
        content.addWidget(self.optics)
        panels.addWidget(left, 10)
        right, content = card()
        rule_row = QHBoxLayout()
        rule_row.addWidget(label("CONTACT STATUS", "brand"), 1)
        self.rule = QComboBox()
        self.rule.setAccessibleName("Contact display rule")
        self.rule.setToolTip("Multi-press tracks 2–4 rods independently and requires a fresh unloaded baseline. "
                             "A green contact tile also requires a positive SVC decision. Stop to change the rule.")
        for key, title in MODE_LABELS.items():
            self.rule.addItem(title, key)
        self.rule.setCurrentIndex(max(0, self.rule.findData(self.settings["display_mode"])))
        self.minimum_v_step = self.settings["minimum_v_step"]
        self.rule.currentIndexChanged.connect(self.rule_changed)
        rule_row.addWidget(self.rule)
        content.addLayout(rule_row)
        self.status = label("", "state", True)
        content.addWidget(self.status)
        self.detail = label("", "muted", True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.detail)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#364d5a")
        content.addWidget(sep)
        row = QHBoxLayout()
        row.addWidget(label("Taxel location", "sectionTitle"), 1)
        self.map_button = QPushButton("Check mapping…")
        self.map_button.clicked.connect(self.check_orientation)
        row.addWidget(self.map_button)
        content.addLayout(row)
        self.grid_caption = label("", "small", True)
        content.addWidget(self.grid_caption)
        grid = QGridLayout()
        self.taxels = []
        for i in range(9):
            cell = label(f"R{i+1}", "taxel")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            cell.setMinimumHeight(31)
            grid.addWidget(cell, i//3, i%3)
            self.taxels.append(cell)
        content.addLayout(grid, 1)
        self.prediction = label("Active taxel   —", "sectionTitle")
        content.addWidget(self.prediction)
        panels.addWidget(right, 9)
        root.addLayout(panels, 1)
        bottom, content = card()
        content.setContentsMargins(13, 7, 13, 8)
        content.setSpacing(2)
        self.telemetry = label("", "muted", True)
        self.model_line = label("", "small", True)
        self.session_line = label("", "small", True)
        for item in (self.telemetry, self.model_line, self.session_line):
            content.addWidget(item)
        root.addWidget(bottom)
        self.clips.currentIndexChanged.connect(self.restore_rule)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.mode.setCurrentIndex(1 if replay is not None else 0)
        self.shortcut = QShortcut(QKeySequence("F11"), self, activated=self.fullscreen)
        self.escape = QShortcut(QKeySequence("Escape"), self, activated=self.leave_fullscreen)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(50)
        self.idle = View("SETUP ERROR", self.initial_error) if self.initial_error else View()
        self.refresh()

    def select_video(self, path):
        path = str(Path(path).resolve())
        i = self.clips.findData(path)
        if i < 0:
            self.clips.addItem(Path(path).name, path)
            i = self.clips.count()-1
        self.clips.setCurrentIndex(i)
        self.clips.setToolTip(path)

    def browse_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open original, unannotated recording", str(SAMPLE),
                                             "Video (*.mp4 *.avi *.mkv *.mov);;All files (*)")
        if path:
            self.select_video(path)

    def rule_changed(self):
        if self.mode.currentText() == LIVE:
            self.settings["display_mode"] = self.rule.currentData()
        self.refresh_layout()

    def regions_for_input(self):
        if self.rule.currentData() == "models":
            return self.canonical_layout
        values = self.settings.get("optical_rois")
        if self.mode.currentText() != LIVE:
            values = None
            clip = Path(self.clips.currentData())
            meta = clip.with_name("session.json")
            if clip.stem == "session_video" and meta.is_file():
                values = json.loads(meta.read_text(encoding="utf-8")).get("configuration", {}).get("optical_rois")
        return optical_layout(values, self.canonical_layout)

    def refresh_layout(self):
        try:
            if self.canonical_layout is not None:
                self.layout_spec = self.regions_for_input()
                self.camera.rois = self.layout_spec.rois
                self.camera.update()
        except (ValueError, OSError, AttributeError) as exc:
            self.initial_error = str(exc)

    def edit_rois(self):
        if self.roi_dialog is not None or self.reference_frame is None or self.mode.currentText() != LIVE:
            return
        if self.session and not self.session.done.is_set():
            self.session.stop("ROI EDITING", "Acquisition stopped. Save your regions, then Start and capture a fresh baseline.")
        layout = optical_layout(self.settings.get("optical_rois"), self.canonical_layout)
        self.roi_dialog = RoiEditor(self, layout, self.canonical_layout, self.reference_frame, self.apply_rois)
        self.roi_dialog.finished.connect(lambda _: setattr(self, "roi_dialog", None))
        self.roi_dialog.show()
        self.refresh()

    def apply_rois(self, values):
        layout = optical_layout(values, self.canonical_layout)
        previous = dict(self.settings)
        self.settings.update(optical_rois=values if layout.roi_layout_id != self.canonical_layout.roi_layout_id else None,
                             physical_mapping=None)
        if self.rule.currentData() == "models":
            self.settings["display_mode"] = "multi_v_rise"
        try:
            self.persist()
        except OSError:
            self.settings = previous
            raise
        if self.rule.currentData() == "models":
            self.rule.setCurrentIndex(self.rule.findData("multi_v_rise"))
        self.refresh_layout()
        self.idle = View("CALIBRATION REQUIRED", "ROI layout saved. Start and capture a fresh unloaded baseline.")
        self.layout_reset_pending = True
        self.refresh()
        return True

    def restore_rule(self):
        if self.mode.currentText() == LIVE:
            config = self.settings
        else:
            # Preserve the user's live choice. Ordinary thesis clips open in the original
            # mode. A recorded demo restores the policy and sensitivity used on that run.
            config = {}
            clip = Path(self.clips.currentData())
            meta = clip.with_name("session.json")
            if clip.stem == "session_video" and meta.is_file():
                try:
                    config = json.loads(meta.read_text(encoding="utf-8")).get("configuration", {})
                except (OSError, ValueError, AttributeError):
                    pass  # Replay.open reports an unreadable session when Start is pressed.
        self.rule.setCurrentIndex(max(0, self.rule.findData(config.get("display_mode", "models"))))
        self.minimum_v_step = config.get("minimum_v_step", 0.)
        self.refresh_layout()

    def change_mode(self, index):
        self.inputs.setCurrentIndex(index)
        self.restore_rule()
        if self.session is None or self.session.done.is_set():
            self.session = None
            self.idle = View() if not self.initial_error else View("SETUP ERROR", self.initial_error)
            self.refresh()

    def toggle_overlay(self, checked):
        self.camera.overlay = checked
        self.camera.update()
        self.settings["overlay"] = checked

    def persist(self):
        path = Path(self.clips.currentData())
        replay = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path)
        self.settings.update(camera_index=self.index.value(), replay=replay, overlay=self.overlay.isChecked())
        save_setup(self.settings, self.output)

    def start(self):
        if self.session and not self.session.done.is_set():
            return
        try:
            self.persist()
            self.canonical_layout = load_canonical_live_layout(PROJECT_ROOT / self.settings["roi_layout"])
            self.layout_spec = self.regions_for_input()
            self.camera.rois = self.layout_spec.rois
            self.initial_error = ""
            config = dict(self.settings, display_mode=self.rule.currentData(), minimum_v_step=self.minimum_v_step)
            self.session = self.session_factory(config, self.mode.currentText(), record=self.record.isChecked(), output=self.output)
            self.session.start()
        except Exception as exc:
            self.session = None
            self.idle = View("SETUP ERROR", str(exc))
        self.refresh()

    def stop(self):
        if self.session:
            self.session.stop()
        self.refresh()

    def capture_baseline(self):
        if self.session:
            self.session.request_baseline()
            self.refresh()

    def fullscreen(self):
        if self.isFullScreen():
            self.leave_fullscreen()
        else:
            self.showFullScreen()
            self.full.setText("Exit full screen  ·  F11")

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.full.setText("Full screen  ·  F11")

    def check_orientation(self):
        if self.mapping_dialog:
            self.mapping_dialog.raise_()
            return
        self.mapping_dialog = MappingDialog(self, self.layout_spec, self.save_mapping)
        self.mapping_dialog.finished.connect(self.mapping_closed)
        self.mapping_dialog.show()

    def mapping_closed(self, _):
        self.mapping_dialog = None

    def save_mapping(self, cells):
        session = self.session
        if not session or session.mode != LIVE or not session.view().result or session.record:
            return False
        previous = self.settings["physical_mapping"]
        self.settings["physical_mapping"] = verified_mapping(cells, session.info["device"], self.layout_spec.roi_layout_id)
        try:
            self.persist()
        except OSError as exc:
            self.settings["physical_mapping"] = previous
            QMessageBox.warning(self, "Cannot save orientation", str(exc))
            return False
        session.stop("MAPPING SAVED", "Press Start and capture a fresh unloaded baseline.")
        return True

    def refresh(self):
        s = self.session
        if self.layout_reset_pending and (s is None or s.done.is_set()):
            self.session = s = None
            self.layout_reset_pending = False
        state = s.view() if s else getattr(self, "idle", View())
        busy = bool(s and not s.done.is_set())
        running = busy and not s.cancel.is_set()
        live = self.mode.currentText() == LIVE
        self.start_button.setEnabled(not busy)
        self.roi_button.setEnabled(live and self.reference_frame is not None and self.roi_dialog is None)
        self.stop_button.setEnabled(running)
        for control in (self.mode, self.inputs, self.record, self.rule):
            control.setEnabled(not busy)
        self.baseline_button.setEnabled(bool(running and s.info and state.status not in {"CALIBRATING", "STALE INPUT"}))
        self.map_button.setEnabled(bool(running and live and state.result and not s.record))
        self.map_button.setToolTip("Check nine physical positions during a calibrated, unrecorded live run.")
        if state.status != self.last_status:
            self.last_status = state.status
            colors = {"CONTACT DETECTED": "#83eed0", "NO CONTACT DETECTED": "#c7e8ff", "NO CONFIRMED CONTACT": "#c7e8ff",
                      "STOPPED": "#e7eff2", "REPLAY COMPLETE": "#c7e8ff"}
            self.status.setStyleSheet(f"color:{colors.get(state.status, '#ffca84')};font-size:24px;font-weight:700")
            self.status.setText(state.status)
        self.detail.setText(state.detail)
        self.camera.placeholder = "Select a recording and press Start" if not live else "Waiting for the underside camera"
        if self.last_frame is not state.frame:
            self.camera.set_image(state.frame.image if state.frame else None)
            if state.frame is not None and live:
                self.reference_frame = state.frame.image.copy()
            self.last_frame = state.frame
        if self.mapping_dialog:
            self.mapping_dialog.fresh = bool(running and live and state.result)
            self.mapping_dialog.preview.set_image(state.frame.image if state.frame else None)
            self.mapping_dialog.optics.set_values(state.optical if state.result else ())
            self.mapping_dialog.optical_title.setText(self.optical_title.text())
        signal = ("mean positive ΔV" if self.rule.currentData() == "models" else
                  "brightest 5% V, denoised" if self.rule.currentData() in SPOT_MODES else "mean HSV V")
        self.optical_title.setText(f"Optical response per ROI  ·  {signal} (digital levels)")
        self.optics.set_values(state.optical if state.result else ())
        key = (state.cells, state.active_rois)
        if key != self.last_grid:
            self.last_grid = key
            for cell, number in zip(self.taxels, state.cells):
                cell.setText(f"R{number}")
                cell.setProperty("active", number in state.active_rois)
                cell.style().unpolish(cell)
                cell.style().polish(cell)
        self.grid_caption.setText("Physical top view  ·  nine positions verified" if state.mapping else
                                  ("ROI order  ·  physical orientation unchecked" if live else "Recorded view  ·  ROI order"))
        origin = "Optical taxels" if self.rule.currentData().startswith("multi_") else (
            "Optical taxel" if self.rule.currentData() != "models" else "Predicted taxel")
        if state.result and state.change and state.change.rois and not state.result["contact"]:
            names = ", ".join(f"R{i}" for i in state.change.rois)
            self.prediction.setText(f"Optical {names}  ·  contact unconfirmed")
        else:
            names = ", ".join(f"R{i}" for i in state.active_rois)
            self.prediction.setText(f"{origin}   {names}" if names else f"{origin}   —")
        info = s.info if s else {}
        size = " × ".join(map(str, info.get("resolution", (640, 480))))
        self.camera_line.setText(f"{self.mode.currentText()}   ·   {size} input   ·   480 × 640 ROI view")
        if state.frame:
            fresh = f"{state.age_ms():.0f} ms old"
            stats = f"Capture  {state.capture_hz:.1f} Hz     Inference  {state.inference_hz:.1f} Hz     Process  {state.ms:.1f} ms     Frame  {state.frame.number}  ·  {fresh}"
        else:
            stats = "Capture  —     Inference  —     Process  —     Frame age  —"
        baseline = f"ready · {state.baseline[-8:]}" if state.baseline.startswith("baseline-") else state.baseline.lower()
        self.telemetry.setText(f"{stats}     Baseline  {baseline}")
        loaded = "Loaded" if s and s.models else "Configured"
        self.model_line.setText(f"{loaded}   RBF SVC / con_022     ·     Logistic regression / loc_036     ·     2026-09-09 refit     ·     Score averaging 1.0 s")
        score = ""
        if state.result:
            raw = state.result
            score = f"   ·   Raw SVC {raw['contact']} ({raw['contact_score']:.3f})   ·   Raw logistic R{raw['localization']}"
            if isinstance(state.change, MultiReading):
                score += f"   ·   {len(state.active_rois)} confirmed optical rods · experimental multi-press"
            elif state.change:
                score += f"   ·   Local change {state.change.change_v:.2f} / threshold {state.change.threshold_v:.2f} V levels"
                if state.change.rate_v_s is not None:
                    score += f"   ·   R{state.change.roi} {state.change.rate_v_s:+.1f} V levels/s"
        trace = f"   ·   Session {s.record_path.name}" if s and s.record_path else ""
        self.session_line.setText(f"{info.get('clock', 'Camera demonstration')}   ·   Experimental live inference{score}{trace}")

    def settings_dialog(self):
        busy = bool(self.session and not self.session.done.is_set())
        dlg = QDialog(self)
        dlg.setWindowTitle("Advanced settings")
        dlg.resize(660, 445)
        outer = QVBoxLayout(dlg)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(label("Setup can be edited while acquisition is stopped." if busy else
                          "The normal camera mode reads the current driver settings.", "muted", True))
        override = QCheckBox("Apply manual exposure and gain on Start")
        saved = self.settings["camera_controls"]
        override.setChecked(bool(saved))
        exposure, gain = QDoubleSpinBox(), QDoubleSpinBox()
        for box, name, default in [(exposure, "exposure", -2), (gain, "gain", 0)]:
            box.setRange(-10000, 10000)
            box.setValue(saved.get(name, default))
            box.setEnabled(not busy and override.isChecked())
            override.toggled.connect(box.setEnabled)
        form.addRow(override)
        form.addRow("Exposure (driver units)", exposure)
        form.addRow("Gain (driver units)", gain)
        step = QDoubleSpinBox()
        step.setRange(0., 255.)
        step.setDecimals(2)
        step.setSingleStep(.1)
        step.setSpecialValueText("Automatic")
        step.setValue(self.minimum_v_step)
        step.setEnabled(not busy and self.rule.currentData() != "models")
        form.addRow("Minimum optical step (selected V metric)", step)
        form.addRow(label("Recorded IMX179 reference: 640 × 480, exposure −2, manual exposure, gain 0. "
                          "A requested control must be confirmed by the driver.", "muted", True))
        path = QLineEdit(str(self.settings["model_run"]))
        path.setReadOnly(busy)
        override.setEnabled(not busy)
        form.addRow("Final tuning run", path)
        form.addRow("ROI layout", label(self.settings["roi_layout"], "muted", True))
        form.addRow("Optical detection regions", label(self.layout_spec.roi_layout_id if self.layout_spec else "Invalid", "muted", True))
        form.addRow("Setup and session folder", label(str(self.output), "muted", True))
        tabs.addTab(page, "Setup")
        diagnostics = QPlainTextEdit()
        diagnostics.setReadOnly(True)
        s = self.session
        diagnostics.setPlainText(json.dumps(dict(acquisition=s.info if s else {}, models=s.models if s else {},
                  physical_mapping=self.settings["physical_mapping"], recording=str(s.record_path) if s and s.record_path else None,
                  roi_layout=self.layout_spec.to_dict() if self.layout_spec else {}), indent=2))
        tabs.addTab(diagnostics, "Acquisition & model details")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close if busy else
                                    QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)
        if dlg.exec() and not busy:
            self.minimum_v_step = step.value()
            if self.mode.currentText() == LIVE:
                self.settings["minimum_v_step"] = self.minimum_v_step
            self.settings.update(model_run=path.text().strip(), camera_controls=
                                 dict(auto_exposure=False, exposure=exposure.value(), gain=gain.value()) if override.isChecked() else {})
            try:
                self.persist()
            except OSError as exc:
                QMessageBox.warning(self, "Cannot save setup", str(exc))

    def closeEvent(self, event):
        if self.session and not self.session.done.is_set():
            self.session.stop()
            if self.close_started is None:
                self.close_started = time.monotonic()
            # A wedged native USB read may only return when Windows closes the process.
            # Always finish the recorder first. Never reopen the same device in parallel.
            driver_hung = self.session.files_closed.is_set() and time.monotonic() - self.close_started > 2
            if not self.session.done.is_set() and not driver_hung:
                event.ignore()
                QTimer.singleShot(80, self.close)
                return
        self.timer.stop()
        try:
            self.persist()
        except OSError as exc:
            QMessageBox.warning(self, "Cannot save setup", str(exc))
        event.accept()
