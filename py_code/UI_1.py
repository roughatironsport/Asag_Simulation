#!/usr/bin/env python
"""
YardDesigner – Marshalling Yard Layout Tool

Description:
This program provides a graphical interface for designing and simulating a marshalling yard layout.
Users can place, move, rotate, and delete tracks and a central control unit on a grid-based canvas.
The application automatically calculates Manhattan distances between the entry track, the central unit,
and all storage tracks. These distances will be exported for use in a SimPy-based simulation.

Features:
- Interactive placement of entry track, storage tracks, and central control unit
- Drag-and-drop movement of elements
- Rotation of elements using Shift + Click
- Deletion of elements using right-click
- Automatic calculation and display of distances
- Distance selection
- Visualization of distances with dashed lines and labels
- Export of distance data as a dictionary for simulation purposes
- Help dialog with usage instructions

Controls:
- Left-click: Place or drag elements
- Shift + Left-click: Rotate elements
- Right-click: Delete elements
- OK button: Calculate distances, export data, and close the window
- HELP button: Show usage instructions

Requirements:
- Python 3.x
- PyQt5
"""


import sys
import json
import os
import math
from PyQt5.QtWidgets import (
    QApplication, QWidget, QMessageBox, QInputDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import QRect, QPoint, Qt, QSize

# Absoluter Pfad zur JSON-Datei
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
JSON_PATH = os.path.join(PROJECT_DIR, "json_files", "simulation_data.json")

GRID_SIZE = 10  # Rastergröße in Pixeln
simulation_distances = {}


class Track:
    def __init__(self, x, y, is_entry=False):
        self.rect = QRect(x, y, 800, 10)
        self.is_entry = is_entry
        if self.is_entry:
            self.rect = QRect(x, y, 200, 10)
        self.rotation = 0  # 0°, 90°, 180°, 270°

    def snap_to_grid(self):
        x = round(self.rect.x() / GRID_SIZE) * GRID_SIZE
        y = round(self.rect.y() / GRID_SIZE) * GRID_SIZE
        self.rect.moveTo(x, y)

    def rotate(self):
        w, h = self.rect.width(), self.rect.height()
        self.rect.setSize(QSize(h, w))
        self.rotation = (self.rotation + 90) % 360

    def draw(self, painter: QPainter, label_text: str = ""):
        # Gleis zeichnen
        color = QColor("red") if self.is_entry else QColor("blue")
        painter.setBrush(color)
        painter.setPen(QPen())
        painter.drawRect(self.rect)

        # Ein- und Ausgangspunkte
        entry = self.get_entry_point()
        exit = self.get_exit_point()

        painter.setBrush(QColor("green"))
        painter.drawEllipse(entry, 9, 9)

        painter.setBrush(QColor("black"))
        painter.drawEllipse(exit, 9, 9)

        # Beschriftung am Eingangspunkt
        if label_text:
            painter.setPen(QPen(Qt.black))
            painter.drawText(entry + QPoint(6, -6), label_text)

    def get_entry_point(self):
        cx, cy = self.rect.center().x(), self.rect.center().y()
        if self.rotation == 0:
            return QPoint(self.rect.left(), cy)
        elif self.rotation == 90:
            return QPoint(cx, self.rect.top())
        elif self.rotation == 180:
            return QPoint(self.rect.right(), cy)
        elif self.rotation == 270:
            return QPoint(cx, self.rect.bottom())

    def get_exit_point(self):
        cx, cy = self.rect.center().x(), self.rect.center().y()
        if self.rotation == 0:
            return QPoint(self.rect.right(), cy)
        elif self.rotation == 90:
            return QPoint(cx, self.rect.bottom())
        elif self.rotation == 180:
            return QPoint(self.rect.left(), cy)
        elif self.rotation == 270:
            return QPoint(cx, self.rect.top())


class Central(Track):
    def __init__(self, x, y):
        super().__init__(x, y, is_entry=False)
        self.rect = QRect(x, y, 20, 20)

    def draw(self, painter: QPainter, label_text: str = "Zentrale"):
        painter.setBrush(QColor("orange"))
        painter.setPen(QPen())
        painter.drawRect(self.rect)

        entry = self.get_entry_point()

        painter.setBrush(QColor("black"))
        painter.drawEllipse(entry, 6, 6)

        painter.setPen(QPen(Qt.black))
        painter.drawText(entry + QPoint(6, -6), label_text)


class DistanceMetricDialog(QDialog):
    def __init__(self, current_metric, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Distanzmetrik wählen")
        self.setModal(True)

        # Entferne das Fragezeichen im Fensterrahmen
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.selected_metric = current_metric

        layout = QVBoxLayout()

        label = QLabel("Wähle eine Distanzmetrik:")
        layout.addWidget(label)

        self.combo = QComboBox()
        self.combo.addItems(["MANHATTAN", "EUKLIDISCH"])
        self.combo.setCurrentText(current_metric.upper())
        layout.addWidget(self.combo)

        button_layout = QHBoxLayout()

        help_button = QPushButton("?")
        help_button.clicked.connect(self.show_help)
        button_layout.addWidget(help_button)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Abbrechen")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def show_help(self):
        QMessageBox.information(
            self,
            "Distanzmetriken",
            "🧮 **Euklidische Metrik**:\n"
            "- Misst die direkte Luftlinie zwischen zwei Punkten.\n"
            "- Formel: √((x₂ - x₁)² + (y₂ - y₁)²)\n\n"
            "🏙️ **Manhattan-Metrik**:\n"
            "- Misst die Distanz entlang von Achsen (wie in einem Straßengitter).\n"
            "- Formel: |x₂ - x₁| + |y₂ - y₁|\n\n"
            "💡 Verwenden Sie die Metrik, die am besten zum Layout des Bahnhofs passt."
        )

    def get_selected_metric(self):
        return self.combo.currentText().lower()


class YardDesigner(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rangierbahnhof Designer")
        self.setGeometry(100, 100, 1400, 900)
        self.tracks = []
        self.central = None
        self.dragging = None
        self.offset = QPoint()
        self.distance_lines_track = []  # Liste von (start, end, dist)
        self.distance_lines_central = []
        self.distance_metric = "manhattan"
        self.initUI()

    def initUI(self):
        self.ok_button = QPushButton("OK", self)
        self.ok_button.move(10, 10)
        self.ok_button.clicked.connect(self.on_ok_clicked)
        self.ok_button.setEnabled(False)

        self.del_button = QPushButton("DEL", self)
        self.del_button.move(10, 50)
        self.del_button.clicked.connect(self.del_all)

        self.help_button = QPushButton("HELP", self)
        self.help_button.move(10, 90)
        self.help_button.clicked.connect(self.show_help)

        self.dist_button = QPushButton("MANHATTAN", self)
        self.dist_button.move(10, 130)
        self.dist_button.clicked.connect(self.choose_distance_metric)

        self.info_label = QLabel("Keine Zentrale vorhanden.", self)
        self.info_label.move(150, 0)
        self.info_label.resize(600, 60)

    def check_ok_button_enabled(self):
        has_central = self.central is not None
        has_entry = any(t.is_entry for t in self.tracks)
        has_storage = any(not t.is_entry for t in self.tracks)
        self.ok_button.setEnabled(has_central and has_entry and has_storage)

    def on_ok_clicked(self):
        self.calculate_distances()

        # Datei laden
        with open(JSON_PATH, "r") as f:
            data = json.load(f)

        # simulation_distances hinzufügen
        data["simulation_distances"] = simulation_distances

        # Datei überschreiben
        try:
            with open(JSON_PATH, "w") as f:
                json.dump(data, f)
            print(f"Simulation Distances erfolgreich geschrieben.")
            print(json.dumps(data, indent=4))
        except Exception as e:
            print("Fehler beim Schreiben von Simulation Distances:", e)

        self.close()

    def del_all(self):
        self.central = None
        self.tracks = []
        self.update()
        self.calculate_distances()
        self.check_ok_button_enabled()

    def choose_distance_metric(self):
        dialog = DistanceMetricDialog(self.distance_metric, self)
        if dialog.exec_() == QDialog.Accepted:
            self.distance_metric = dialog.get_selected_metric()
            self.dist_button.setText(self.distance_metric.upper())
            self.calculate_distances()

    def show_help(self):
        QMessageBox.information(
            self,
            "Hilfe",
            "Anleitung:\n\n"
            "- Linksklick: Gleis oder Zentrale platzieren\n"
            "- Linksklick gedrückt halten: Verschieben des Objektes\n"
            "- Shift + Linksklick: Objekt drehen\n"
            "- Rechtsklick: Objekt löschen\n"
            "- OK: Distanzen speichern (nur aktiv, wenn Zentrale, Eingang \n "
            "  und ein Abstellgleis vorhanden sind)\n"
            "- DEL: Lösche alle Objekte auf der Oberfläche\n"
            "- Auswahl zwischen versch. Distanz-Metriken: \n"
            "  (MANHATTAN / EUKLIDISCH) möglich"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.central and self.central.rect.contains(event.pos()):
                if event.modifiers() & Qt.ShiftModifier:
                    self.central.rotate()
                    self.central.snap_to_grid()
                    self.update()
                    self.calculate_distances()
                    return
                else:
                    self.dragging = self.central
                    self.offset = event.pos() - self.central.rect.topLeft()
                    return
            for track in reversed(self.tracks):
                if track.rect.contains(event.pos()):
                    if event.modifiers() & Qt.ShiftModifier:
                        track.rotate()
                        track.snap_to_grid()
                        self.update()
                        self.calculate_distances()
                        return
                    else:
                        self.dragging = track
                        self.offset = event.pos() - track.rect.topLeft()
                        return
        elif event.button() == Qt.RightButton:
            if self.central and self.central.rect.contains(event.pos()):
                self.central = None
                self.update()
                self.calculate_distances()
                self.check_ok_button_enabled()
                return
            for track in reversed(self.tracks):
                if track.rect.contains(event.pos()):
                    self.tracks.remove(track)
                    self.update()
                    self.calculate_distances()
                    self.check_ok_button_enabled()
                    return

        if event.button() == Qt.LeftButton:
            if not any(t.rect.contains(event.pos()) for t in self.tracks):
                if self.central is None:
                    self.central = Central(event.x(), event.y())
                    self.central.snap_to_grid()
                else:
                    is_entry = len([t for t in self.tracks if t.is_entry]) == 0
                    new_track = Track(event.x(), event.y(), is_entry)
                    new_track.snap_to_grid()
                    self.tracks.append(new_track)
                self.update()
                self.calculate_distances()
                self.check_ok_button_enabled()

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_pos = event.pos() - self.offset
            x = round(new_pos.x() / GRID_SIZE) * GRID_SIZE
            y = round(new_pos.y() / GRID_SIZE) * GRID_SIZE
            self.dragging.rect.moveTo(x, y)
            self.calculate_distances()
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging = None
        self.calculate_distances()
        self.update()

    def paintEvent(self, event):

        def draw_dashed_lines(distance_lines, qcolor):
            painter.setPen(QPen(QColor(qcolor), 1, Qt.DashLine))
            for start, end, dist in distance_lines:
                painter.drawLine(start, end)
                mid_x = (start.x() + end.x()) // 2
                mid_y = (start.y() + end.y()) // 2
                painter.drawText(mid_x + 5, mid_y - 5, f"{dist}")

        painter = QPainter(self)
        font = QFont("Arial", 10)
        painter.setFont(font)

        # Raster zeichnen
        pen = QPen(QColor(220, 220, 220))
        painter.setPen(pen)
        for x in range(0, self.width(), GRID_SIZE):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), GRID_SIZE):
            painter.drawLine(0, y, self.width(), y)

        if self.central:
            self.central.draw(painter)

        # Gleise zeichnen
        abstellgleis_counter = 1
        for track in self.tracks:
            if track.is_entry:
                track.draw(painter, "Eingangsgleis")
            else:
                label = f"Abstellgleis #{abstellgleis_counter}"
                track.draw(painter, label)
                abstellgleis_counter += 1

        # Legende unten rechts
        legend_x = self.width() - 200
        legend_y = self.height() - 110
        line_height = 25
        symbol_size = 12
        text_offset = 8

        legend_items = [
            (QColor("red"), "Eingangsgleis", "rect"),
            (QColor("blue"), "Abstellgleis", "rect"),
            (QColor("green"), "Eingangspunkt", "ellipse"),
            (QColor("black"), "Ausgangspunkt", "ellipse"),
        ]

        painter.setPen(QPen(Qt.black))

        for i, (color, label, shape) in enumerate(legend_items):
            y = legend_y + i * line_height
            painter.setBrush(color)
            if shape == "rect":
                painter.drawRect(legend_x, y, symbol_size, symbol_size)
            else:
                painter.drawEllipse(legend_x, y, symbol_size, symbol_size)
            painter.drawText(legend_x + symbol_size + text_offset, y + symbol_size - 2, label)

        draw_dashed_lines(self.distance_lines_track, "darkgreen")
        draw_dashed_lines(self.distance_lines_central, "darkred")

    def calc_dist(self, entry_out, target_in):

        def manhattan_dist(e_out, t_in):
            dx_track = abs(t_in.x() - e_out.x())
            dy_track = abs(t_in.y() - e_out.y())
            dis = dx_track + dy_track
            return dis

        def euklidische_dist(e_out, t_in):
            dx = t_in.x() - e_out.x()
            dy = t_in.y() - e_out.y()
            dis = math.sqrt(dx ** 2 + dy ** 2)
            return dis

        if self.distance_metric == "manhattan":
            dist = manhattan_dist(entry_out, target_in)
        else:
            dist = euklidische_dist(entry_out, target_in)
        return dist

    def calculate_distances(self):

        self.distance_lines_track = []  # vorherige Linien löschen
        self.distance_lines_central = []

        if not self.central:
            self.info_label.setText("Keine Zentrale vorhanden.")
            return

        entry_tracks = [t for t in self.tracks if t.is_entry]
        if not entry_tracks:
            self.info_label.setText("Kein Eingangsgleis vorhanden.")
            return

        entry = entry_tracks[0]
        entry_out = entry.get_exit_point()
        entry_central = self.central.get_entry_point()

        distances_tracks = []
        distances_central = []

        for track in self.tracks:
            if not track.is_entry:
                target_in = track.get_entry_point()
                dist = self.calc_dist(entry_out, target_in)
                distances_tracks.append(dist)
                self.distance_lines_track.append((entry_out, target_in, dist))
                dist = self.calc_dist(entry_central, target_in)
                distances_central.append(dist)
                self.distance_lines_central.append((entry_central, target_in, dist))

        if not distances_tracks:
            self.info_label.setText("Kein Ausgangsgleis vorhanden.")
            return

        self.info_label.setText(
            f"Distanzen Gleise: {distances_tracks}\nDistanzen Zentrale: {distances_central}"
        )
        self.update()

        global simulation_distances
        simulation_distances = {
            "gleise": distances_tracks,
            "zentrale": distances_central
        }

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YardDesigner()
    window.show()
    sys.exit(app.exec_())
