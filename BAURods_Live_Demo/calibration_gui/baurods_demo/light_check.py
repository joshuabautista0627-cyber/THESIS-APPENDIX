"""Operator-cued single-rod and multi-press checks with the normal camera and recorder."""
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton

from scripts.live_sensor_common import atomic_write_json
from .setup import OUTPUT, load_setup, save_setup
from .window import Window


def cue_plan():
    cues = [("idle", 2.5, "Keep all rods unloaded")]
    for repetition in (1, 2):
        for roi in (7, 8, 9):
            cues.extend([
                (f"press_{repetition}_R{roi}", 2.35, f"Round {repetition} · press and hold physical R{roi}"),
                (f"release_{repetition}_R{roi}", 2.1, f"Release R{roi} · keep the array unloaded"),
            ])
    return cues + [("final_idle", 1.5, "Leave all rods unloaded")]


def multi_cue_plan(rois=(7, 9)):
    a, b = rois
    return [
        ("idle", 3., "Keep all rods unloaded"),
        (f"press_1_R{a}_R{b}", 4., f"Press the rods inside camera R{a} + R{b} together"),
        (f"hold_1_R{b}", 3.5, f"Release R{a} only · keep holding R{b}"),
        ("release_1_all", 3.5, f"Release R{b} · keep all rods unloaded"),
        (f"press_2_R{a}_R{b}", 4., f"Press the rods inside camera R{a} + R{b} together"),
        (f"hold_2_R{a}", 3.5, f"Release R{b} only · keep holding R{a}"),
        ("release_2_all", 3.5, f"Release R{a} · keep all rods unloaded"),
        ("final_idle", 2., "Leave all rods unloaded"),
    ]


def sliding_cue_plan(rois=(1, 3)):
    a, b = rois
    return [
        ("idle", 3., "Keep all rods unloaded"),
        (f"slide_R{a}", 6., f"Slide the rod inside camera R{a} gently side to side"),
        ("release_1_all", 3., "Release all rods"),
        (f"slide_R{b}", 6., f"Slide the rod inside camera R{b} gently side to side"),
        ("release_2_all", 3., "Release all rods"),
        (f"slide_R{a}_R{b}", 8., f"Slide the rods inside camera R{a} + R{b} together"),
        (f"hold_R{b}", 4., f"Release camera R{a} · continue sliding camera R{b} only"),
        ("release_3_all", 4., "Release all rods"),
        ("final_idle", 2., "Leave all rods unloaded"),
    ]


class LightCheckWindow(Window):
    def __init__(self, output=OUTPUT, *, multi=False, sliding=False, rois=None, check_mode="multi_v_rise", **kwargs):
        multi = multi or sliding
        rois = tuple(rois or ((1, 3) if sliding else (7, 9)))
        if len(rois) != 2 or len(set(rois)) != 2 or any(type(i) is not int or i not in range(1, 10) for i in rois):
            raise ValueError("Choose two distinct rods from R1 through R9")
        settings = load_setup(output)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        prefix = "sliding" if sliding else "multi_press" if multi else "bright_row"
        check_folder = Path(output) / "diagnostics" / f"{prefix}_{stamp}_{uuid4().hex[:6]}"
        super().__init__(output=check_folder, **kwargs)
        self.demo_output = Path(output)
        self.demo_window = None
        self.return_requested = False
        self.settings.update(settings)
        self.index.setValue(settings["camera_index"])
        mode = "multi_slide" if sliding else check_mode if multi else "rapid_tap"
        if self.rule.findData(mode) < 0:
            raise ValueError("Unknown check mode")
        self.rule.setCurrentIndex(self.rule.findData(mode))
        self.minimum_v_step = settings["minimum_v_step"]
        self.record.setChecked(True)
        self.record.hide()
        self.start_button.hide()
        self.baseline_button.hide()
        self.mode.hide()  # This procedure is for live camera input.
        names = " + ".join(f"R{i}" for i in rois)
        self.setWindowTitle(f"BAURods · {names} {'sliding' if sliding else 'multi-press'} check" if multi else "BAURods · R7 / R8 / R9 light check")
        self.resize(1140, 770)
        self.stage = "waiting"
        self.multi = multi
        self.sliding = sliding
        self.events = []
        self.plan = sliding_cue_plan(rois) if sliding else multi_cue_plan(rois) if multi else cue_plan()
        self.confirmed = self.armed = False
        self.origin = None
        self.issue = ""
        banner = QFrame()
        banner.setStyleSheet("QFrame{background:#16475a;border-radius:6px;}")
        row = QHBoxLayout(banner)
        self.cue = QLabel("Select the Arducam index. Start records an unloaded baseline, then the guided cues.")
        self.cue.setWordWrap(True)
        self.cue.setStyleSheet("font-size:17px; font-weight:650; color:white")
        row.addWidget(self.cue, 1)
        self.check_button = QPushButton("Start sliding check" if sliding else "Start multi-press check" if multi else "Start light check")
        self.check_button.clicked.connect(self.check_action)
        row.addWidget(self.check_button)
        self.demo_button = QPushButton("Open normal demo")
        self.demo_button.clicked.connect(self.return_to_demo)
        row.addWidget(self.demo_button)
        self.centralWidget().layout().insertWidget(1, banner)
        self.cue_timer = QTimer(self)
        self.cue_timer.timeout.connect(self.tick)
        self.cue_timer.start(30)

    def apply_rois(self, values):
        if not super().apply_rois(values):
            return False
        # A layout adjusted in a guided check also belongs to the normal live GUI.
        settings = load_setup(self.demo_output)
        settings.update(optical_rois=self.settings.get("optical_rois"), physical_mapping=None)
        save_setup(settings, self.demo_output)
        return True

    def save_check(self):
        path = self.session.record_path if self.session else None
        atomic_write_json(self.output / "check.json", dict(stage=self.stage, confirmed=self.confirmed,
                          cues=self.events, plan=self.plan, rule=self.rule.currentData(),
                          camera_index=self.index.value(), session=str(path) if path else None, issue=self.issue))

    def check_action(self):
        if self.stage == "finished":
            self.confirmed = True
            self.return_to_demo()
            return
        if self.session and not self.session.done.is_set():
            return
        self.stage, self.issue = "capture", ""
        self.origin, self.armed = None, False
        self.events.clear()
        self.cue.setText("Keep the array unloaded while the camera warms up and captures its baseline.")
        self.check_button.hide()
        self.demo_button.setText("End check · open normal demo")
        self.start()

    def return_to_demo(self):
        if self.return_requested:
            return
        self.return_requested = True
        if self.stage == "capture":
            self.stage = "interrupted"
        if self.session or self.events:
            self.save_check()
        self.check_button.setEnabled(False)
        self.demo_button.setEnabled(False)
        self.cue.setText("Finishing the recording and releasing the camera…")
        self.stop()
        self.tick()

    def tick(self):
        if self.return_requested:
            if self.demo_window is None and (not self.session or self.session.done.is_set()):
                self.cue_timer.stop()
                self.demo_window = Window(output=self.demo_output, session_factory=self.session_factory)
                self.demo_window.show()
                if self.isFullScreen():
                    self.demo_window.fullscreen()
                self.close()
            return
        if self.stage != "capture":
            return
        state = self.session.view() if self.session else self.idle
        if not self.session or self.session.cancel.is_set():
            self.stage, self.issue = "waiting", f"{state.status} · {state.detail}"
            self.cue.setText(self.issue)
            self.check_button.setText("Retry sliding check" if self.sliding else "Retry multi-press check" if self.multi else "Retry light check")
            self.check_button.show()
            self.demo_button.setText("Open normal demo")
            self.save_check()
            return
        if state.frame is None:
            return
        if state.status == "STALE INPUT" and self.origin is not None:
            self.session.stop("INPUT STALLED", "The guided check needs a fresh camera stream. Retry when ready.")
            return
        if not self.armed and state.frame.t >= 4 and state.status == "CALIBRATION REQUIRED":
            self.armed = True
            self.capture_baseline()
        if self.origin is None:
            if not state.result:
                return
            self.origin = time.monotonic()
        elapsed, end = time.monotonic() - self.origin, 0.
        for phase, seconds, text in self.plan:
            end += seconds
            if elapsed < end:
                if not self.events or self.events[-1]["phase"] != phase:
                    self.events.append(dict(phase=phase, frame=state.frame.number, source_s=state.frame.t))
                    self.save_check()
                    if phase.startswith(("press", "hold", "release", "slide")):
                        QApplication.beep()
                self.cue.setText(f"{text}   ·   {end-elapsed:.1f} s")
                return
        self.stage = "finished"
        self.events.append(dict(phase="end", frame=state.frame.number, source_s=state.frame.t))
        self.stop()
        self.save_check()
        self.cue.setText("Did you complete all sliding and release cues?" if self.sliding else "Did you complete both press/release rounds?")
        self.check_button.setText("Yes · open normal demo")
        self.check_button.show()
        self.demo_button.setText("Timing uncertain · open demo")

    def closeEvent(self, event):
        if self.stage == "capture":
            self.stage = "interrupted"
        if self.events or self.session:
            self.save_check()
        super().closeEvent(event)
        if event.isAccepted():
            self.cue_timer.stop()
