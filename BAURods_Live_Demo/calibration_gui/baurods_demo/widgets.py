"""Presentation widgets. Painting is confined to display copies."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from .setup import check_mapping


def label(text, name="", wrap=False):
    item = QLabel(text)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


class CameraView(QWidget):
    def __init__(self, layout=None):
        super().__init__()
        self.rois = layout.rois if layout else ()
        self.image = QImage()
        self.overlay = True
        self.placeholder = "Camera preview"
        self.setMinimumSize(160, 145)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, array):
        if array is None:
            self.image = QImage()
        else:
            h, w = array.shape[:2]
            self.image = QImage(array.data, w, h, array.strides[0], QImage.Format.Format_BGR888).copy()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#080f17"))
        w, h = self.width(), self.height()
        if self.image.isNull():
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(9):
                p.setBrush(QColor("#416073" if i == 4 else "#283d4b"))
                p.drawEllipse(QPointF(w/2 + (i%3-1)*17, h/2-27 + (i//3-1)*17), 4.5, 4.5)
            p.setPen(QColor("#a9c0cb"))
            p.drawText(QRectF(0, h/2+15, w, 28), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            p.end()
            return
        scale = min(w / self.image.width(), h / self.image.height())
        p.translate((w - self.image.width() * scale)/2, (h - self.image.height() * scale)/2)
        p.scale(scale, scale)
        p.drawImage(0, 0, self.image)
        if self.overlay:
            font = QFont("Segoe UI")
            font.setBold(True)
            font.setPixelSize(17)
            p.setFont(font)
            for roi in self.rois:
                rect = QRectF(roi.x, roi.y, roi.width, roi.height)
                p.setPen(QPen(QColor("#0d2634"), 4))
                p.drawRect(rect)
                p.setPen(QPen(QColor("#86f5d8"), 1.8))
                p.drawRect(rect)
                badge = QRectF(roi.x, roi.y, 32, 21)
                p.fillRect(badge, QColor("#103d3b"))
                p.setPen(QColor("#e4fff7"))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"R{roi.roi_id}")
        p.end()


class OpticalStrip(QWidget):
    """Nine optical measurements on a common scale, independent of classifier output."""
    def __init__(self):
        super().__init__()
        self.values = ()
        self.setFixedHeight(43)
        self.setToolTip("ROI 1–9 in trained camera order. All nine measured optical values share this frame's scale.")

    def set_values(self, values):
        if self.values != values:
            self.values = values
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        width = self.width()/9
        scale = max(1., max(self.values, default=0.))
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        p.setFont(font)
        for i in range(9):
            x = i*width
            value = self.values[i] if self.values else 0
            p.fillRect(QRectF(x+2, 0, width-4, 22), QColor("#101e2a"))
            height = 22*value/scale
            p.fillRect(QRectF(x+2, 22-height, width-4, height), QColor("#36788a"))
            p.setPen(QColor("#eff5f6"))
            p.drawText(QRectF(x, 1, width, 20), Qt.AlignmentFlag.AlignCenter, f"{value:.1f}" if self.values else "—")
            p.setPen(QColor("#a8c1cb"))
            p.drawText(QRectF(x, 23, width, 19), Qt.AlignmentFlag.AlignCenter, f"R{i+1}")
        p.end()


class MappingDialog(QDialog):
    def __init__(self, parent, layout, commit):
        super().__init__(parent)
        self.setWindowTitle("Verify physical orientation")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(710, 480)
        self.commit, self.observations = commit, []
        root = QVBoxLayout(self)
        root.addWidget(label("Verify physical orientation", "sectionTitle"))
        root.addWidget(label("Stand on the pressing side of the array. At each marked position, press once, "
                             "identify the numbered ROI whose light changes in the camera, then release.", "muted", True))
        sides = QHBoxLayout()
        self.preview = CameraView(layout)
        sides.addWidget(self.preview, 1)
        panel = QVBoxLayout()
        self.prompt = label("", "sectionTitle", True)
        panel.addWidget(self.prompt)
        grid = QGridLayout()
        self.markers = []
        for i in range(9):
            box = label("·", "mappingCell")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.markers.append(box)
            grid.addWidget(box, i//3, i%3)
        panel.addLayout(grid)
        self.observed = QComboBox()
        self.observed.addItem("Select the observed ROI…", None)
        for i in range(1, 10):
            self.observed.addItem(f"R{i}", i)
        panel.addWidget(self.observed)
        self.confirm = QPushButton("Confirm this position")
        self.confirm.clicked.connect(self.accept_observation)
        panel.addWidget(self.confirm)
        self.undo = QPushButton("Undo last position")
        self.undo.clicked.connect(self.back)
        panel.addWidget(self.undo)
        self.notice = label("", "muted", True)
        panel.addWidget(self.notice)
        sides.addLayout(panel, 1)
        root.addLayout(sides, 1)
        self.optical_title = label("Optical response per ROI  ·  mean positive ΔV (digital levels)", "small")
        root.addWidget(self.optical_title)
        self.optics = OpticalStrip()
        root.addWidget(self.optics)
        self.fresh = False
        self.render_step()

    def render_step(self):
        n = len(self.observations)
        self.prompt.setText(f"Press row {n//3+1}, column {n%3+1}" if n < 9 else "All nine positions checked")
        self.observed.setVisible(n < 9)
        self.confirm.setText("Save verified orientation" if n == 9 else "Confirm this position")
        self.undo.setEnabled(n > 0)
        self.observed.setCurrentIndex(0)
        for i, marker in enumerate(self.markers):
            marker.setText(f"R{self.observations[i]}" if i < n else ("PRESS" if i == n else "·"))
            marker.setStyleSheet("background:#79ebcf;color:#082b25" if i == n else "")

    def back(self):
        if self.observations:
            self.observations.pop()
        self.notice.clear()
        self.render_step()

    def accept_observation(self):
        if not self.fresh:
            self.notice.setText("A fresh, calibrated live frame is required.")
            return
        if len(self.observations) == 9:
            try:
                cells = check_mapping(self.observations)
            except ValueError as exc:
                self.notice.setText(str(exc))
                return
            if self.commit(cells):
                self.accept()
            return
        value = self.observed.currentData()
        if value is None or value in self.observations:
            self.notice.setText("Choose a numbered ROI that has not already been assigned.")
            return
        self.observations.append(value)
        self.notice.setText("Release the taxel before moving to the next position.")
        self.render_step()
