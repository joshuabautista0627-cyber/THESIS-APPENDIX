"""Drag, resize or redraw optical ROIs on a frozen camera preview."""
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QPushButton, QSpinBox, QVBoxLayout)

from .optical_rois import optical_layout
from .widgets import CameraView, label


class RoiCanvas(CameraView):
    changed = Signal()
    selected_changed = Signal(int)

    def __init__(self, layout):
        super().__init__(layout)
        self.rois = list(layout.rois)
        self.selected = 0
        self.drawing = False
        self.drag = None
        self.setMinimumSize(360, 480)
        self.setMouseTracking(True)

    def transform(self):
        scale = min(self.width()/480, self.height()/640)
        return scale, (self.width()-480*scale)/2, (self.height()-640*scale)/2

    def point(self, position, *, clamp=False):
        scale, x, y = self.transform()
        px, py = (position.x()-x)/scale, (position.y()-y)/scale
        if not clamp and not (0 <= px <= 480 and 0 <= py <= 640):
            return None
        return QPointF(min(480, max(0, px)), min(640, max(0, py)))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.point(event.position())
        if point is None:
            return
        r = self.rois[self.selected]
        if self.drawing:
            self.drag = ("draw", point, r)
        else:
            corners = [(r.x, r.y), (r.x+r.width, r.y), (r.x, r.y+r.height), (r.x+r.width, r.y+r.height)]
            corner = next((i for i, (x, y) in enumerate(corners)
                           if abs(point.x()-x) < 10/self.transform()[0] and abs(point.y()-y) < 10/self.transform()[0]), None)
            if corner is not None:
                self.drag = ("draw", QPointF(*corners[3-corner]), r)
            else:
                hit = next((i for i, roi in enumerate(self.rois)
                            if QRectF(roi.x, roi.y, roi.width, roi.height).contains(point)), None)
                if hit is None:
                    return
                self.selected = hit
                self.selected_changed.emit(hit)
                self.drag = ("move", point, self.rois[hit])
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag is None:
            return
        point = self.point(event.position(), clamp=True)
        action, start, old = self.drag
        if action == "move":
            new = replace(old, x=int(np.clip(round(old.x+point.x()-start.x()), 0, 480-old.width)),
                          y=int(np.clip(round(old.y+point.y()-start.y()), 0, 640-old.height)))
        else:
            x, y = round(min(start.x(), point.x())), round(min(start.y(), point.y()))
            width, height = max(8, round(abs(point.x()-start.x()))), max(8, round(abs(point.y()-start.y())))
            new = replace(old, x=min(x, 480-width), y=min(y, 640-height), width=width, height=height)
        self.rois[self.selected] = new
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag is not None:
            self.mouseMoveEvent(event)
        self.drag = None

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        scale, x, y = self.transform()
        p.translate(x, y)
        p.scale(scale, scale)
        r = self.rois[self.selected]
        p.setPen(QPen(QColor("#ffd58a"), 2/scale))
        p.drawRect(QRectF(r.x, r.y, r.width, r.height))
        for cx, cy in ((r.x, r.y), (r.x+r.width, r.y), (r.x, r.y+r.height), (r.x+r.width, r.y+r.height)):
            p.fillRect(QRectF(cx-4/scale, cy-4/scale, 8/scale, 8/scale), QColor("#ffd58a"))
        p.end()


class RoiEditor(QDialog):
    def __init__(self, parent, layout, defaults, image, commit):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowTitle("BAURods · Adjust detection ROIs")
        self.resize(830, 740)
        self.defaults, self.commit, self.original = defaults, commit, image.copy()
        root = QVBoxLayout(self)
        root.addWidget(label("Adjust detection ROIs", "sectionTitle"))
        root.addWidget(label("Select a rod, drag its rectangle or resize a corner. Keep each tip inside its own ROI. "
                             "Saving requires a new unloaded baseline.", "muted", True))
        row = QHBoxLayout()
        self.canvas = RoiCanvas(layout)
        self.canvas.set_image(image)
        row.addWidget(self.canvas, 1)
        panel = QVBoxLayout()
        form = QFormLayout()
        self.selected = QComboBox()
        self.selected.addItems([f"R{i}" for i in range(1, 10)])
        self.selected.currentIndexChanged.connect(self.select)
        form.addRow("Rod", self.selected)
        self.fields = {}
        for key in ("x", "y", "width", "height"):
            spin = QSpinBox()
            spin.setRange(8 if key in {"width", "height"} else 0, 480 if key in {"x", "width"} else 640)
            spin.setAccessibleName(f"ROI {key}")
            spin.valueChanged.connect(self.numbers_changed)
            self.fields[key] = spin
            form.addRow(key.capitalize(), spin)
        panel.addLayout(form)
        self.draw = QPushButton("Redraw selected ROI")
        self.draw.setCheckable(True)
        self.draw.toggled.connect(lambda checked: setattr(self.canvas, "drawing", checked))
        panel.addWidget(self.draw)
        reset = QPushButton("Reset selected ROI")
        reset.clicked.connect(self.reset_selected)
        panel.addWidget(reset)
        restore = QPushButton("Restore all defaults")
        restore.clicked.connect(self.restore_defaults)
        panel.addWidget(restore)
        panel.addWidget(label("Preview brightness", "muted"))
        self.brightness = QComboBox()
        for gain in (1, 4, 8, 16, 32):
            self.brightness.addItem(f"{gain}×", gain)
        self.brightness.setToolTip("Preview only. Detection and recording use the original pixels.")
        self.brightness.currentIndexChanged.connect(self.preview_brightness)
        panel.addWidget(self.brightness)
        panel.addStretch()
        panel.addWidget(label("Optical modes use these regions. The trained-model reference keeps its original regions.", "muted", True))
        row.addLayout(panel)
        root.addLayout(row, 1)
        self.notice = label("", "muted", True)
        root.addWidget(self.notice)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.canvas.changed.connect(self.sync)
        self.canvas.selected_changed.connect(self.selected.setCurrentIndex)
        self.sync()

    def select(self, index):
        self.canvas.selected = index
        self.sync()

    def sync(self):
        roi = self.canvas.rois[self.canvas.selected]
        for key, spin in self.fields.items():
            spin.blockSignals(True)
            spin.setValue(getattr(roi, key))
            spin.blockSignals(False)
        try:
            optical_layout(self.values(), self.defaults)
            self.notice.setText("Nine non-overlapping ROIs · Save, Start, then capture an unloaded baseline.")
            valid = True
        except ValueError as exc:
            self.notice.setText(str(exc))
            valid = False
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(valid)
        self.canvas.update()

    def values(self):
        return [dict(roi_id=r.roi_id, x=r.x, y=r.y, width=r.width, height=r.height) for r in self.canvas.rois]

    def numbers_changed(self):
        r = self.canvas.rois[self.canvas.selected]
        values = {key: spin.value() for key, spin in self.fields.items()}
        self.canvas.rois[self.canvas.selected] = replace(r, **values)
        self.sync()

    def reset_selected(self):
        self.canvas.rois[self.canvas.selected] = self.defaults.rois[self.canvas.selected]
        self.sync()

    def restore_defaults(self):
        self.canvas.rois = list(self.defaults.rois)
        self.sync()

    def preview_brightness(self):
        self.canvas.set_image(np.clip(self.original.astype(float)*self.brightness.currentData(), 0, 255).astype(np.uint8))

    def save(self):
        try:
            optical_layout(self.values(), self.defaults)
            if self.commit(self.values()):
                self.accept()
        except (ValueError, OSError) as exc:
            self.notice.setText(str(exc))
