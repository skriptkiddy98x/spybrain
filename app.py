"""Native Windows interface for SpyBrain."""
import multiprocessing
multiprocessing.freeze_support()
import sys
import os
import json
import math
import shutil
import tempfile
import threading
import time
import base64
import datetime as dt
import gzip
from pathlib import Path
import osinthub as engine
import geolocate
import leaks

if __name__ == "__main__" and "--worker" in sys.argv:
    engine.worker_main()
    sys.exit(0)

if __name__ == "__main__" and "--cli" in sys.argv:
    sys.argv.remove("--cli")
    sys.exit(engine.main())

def smoke_trace(message):
    if "_smoke_log" in globals():
        _smoke_log.write(message+"\n")
        _smoke_log.flush()

if __name__ == "__main__" and "--smoke-test" in sys.argv:
    import faulthandler
    _smoke_path = Path(sys.argv[sys.argv.index("--smoke-test")+1])
    _smoke_path.mkdir(parents=True,exist_ok=True)
    _smoke_log = (_smoke_path/"startup-trace.log").open("w",encoding="utf-8")
    faulthandler.dump_traceback_later(20,repeat=True,file=_smoke_log)
    smoke_trace("Importing Qt")

from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QUrl, QSize, QPointF, QRectF, QRect,
    QPropertyAnimation, QEasingCurve, QAbstractAnimation, QSettings)
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontMetrics, QIcon, QDesktopServices,
    QPixmap, QPolygonF, QBrush, QConicalGradient, QRadialGradient, QPalette, QPainterPath, QImage, QLinearGradient)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QHBoxLayout, QVBoxLayout, QGridLayout, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPlainTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QStyledItemDelegate, QStyle, QGraphicsOpacityEffect, QDialog, QCheckBox, QScrollArea)

# Terminal palette: black, bone-white text and signal green. Amber marks warnings, red failures.
INK, PANEL, RAISED, HOVER = "#000000", "#070a08", "#121814", "#0b0f0c"
LINE, RULE = "#19201b", "#29332c"
BONE, ASH, DIM = "#e2ebe4", "#7d8c81", "#47534a"
SIGNAL, BRIGHT, WARN, ALERT = "#00ff41", "#7dff9a", "#ffa31a", "#ff5c5c"
DISPLAY, BODY, MONO = "Bahnschrift SemiBold Condensed", "Bahnschrift", "Consolas"
TOKENS = {"ink": INK, "panel": PANEL, "raised": RAISED, "hover": HOVER, "line": LINE, "rule": RULE,
    "bone": BONE, "ash": ASH, "dim": DIM, "signal": SIGNAL, "bright": BRIGHT, "warn": WARN, "alert": ALERT,
    "display": DISPLAY, "body": BODY, "mono": MONO}

def qss(text):
    for key in sorted(TOKENS, key=len, reverse=True):
        text = text.replace("@"+key, TOKENS[key])
    return text

STYLE = qss("""
QWidget { background:@ink; color:@bone; font-family:'@body'; font-size:14px; }
QMainWindow, QStackedWidget { background:@ink; }
QToolTip { background:@raised; color:@bone; border:1px solid @rule; padding:6px 8px; font-family:'@mono'; font-size:12px; }
QFrame#topbar { background:@ink; border-bottom:1px solid @line; }
QFrame#topbar QLabel { background:transparent; }
QLabel#wordmark { font-family:'@display'; font-size:22px; letter-spacing:3px; color:@bone; }
QLabel#version { font-family:'@mono'; font-size:11px; color:@dim; padding-top:6px; }
QLabel#clock { font-family:'@mono'; font-size:12px; color:@ash; letter-spacing:1px; }
QLabel#live { font-family:'@mono'; font-size:12px; color:@signal; letter-spacing:2px; }
QFrame#indicator { background:@signal; border:0; }
QPushButton#nav { background:transparent; border:0; color:@ash; font-family:'@display'; font-size:15px; letter-spacing:3px; padding:19px 14px; }
QPushButton#nav:hover, QPushButton#nav:checked { color:@bone; }
QPushButton#nav:focus { border-bottom:1px dashed @ash; }
QPushButton#nav:disabled { color:@dim; }
QLabel#micro { font-family:'@mono'; font-size:11px; color:@ash; letter-spacing:3px; }
QLabel#prompt { font-family:'@mono'; font-size:28px; color:@signal; padding-bottom:4px; }
QLabel#heading { font-family:'@display'; font-size:38px; letter-spacing:3px; color:@bone; }
QLabel#lede { color:@ash; font-size:14px; }
QLabel#hint { color:@ash; font-size:13px; }
QLabel#hint[tone="warn"] { color:@warn; }
QLabel#status { font-family:'@mono'; font-size:13px; color:@bone; }
QLabel#elapsed { font-family:'@mono'; font-size:13px; color:@ash; }
QLabel#empty { font-family:'@mono'; font-size:13px; color:@ash; }
QLabel#footer { font-family:'@mono'; font-size:11px; color:@dim; }
QLabel#caveat { font-family:'@mono'; font-size:11px; color:@ash; letter-spacing:2px; }
QLabel#section { font-family:'@display'; font-size:21px; letter-spacing:3px; color:@bone; }
QLabel#tools { font-family:'@mono'; font-size:12px; color:@ash; }
QLabel#body { color:@bone; font-size:14px; }
QFrame#rule { background:@line; border:0; }
QFrame#chartFrame { background:@panel; border:1px solid @line; }
QWidget#overlay, QWidget#overlay QWidget { background:transparent; }
QLineEdit { background:@panel; border:1px solid @rule; border-radius:0; padding:8px 12px; color:@bone; font-family:'@mono'; font-size:13px; selection-background-color:@signal; selection-color:@ink; }
QLineEdit:hover { border-color:@dim; }
QLineEdit:focus { border-color:@signal; }
QLineEdit:disabled { color:@dim; border-color:@line; }
QLineEdit#target { background:@ink; border:0; border-bottom:2px solid @rule; padding:10px 4px; font-size:21px; }
QLineEdit#target:focus { border-bottom-color:@signal; }
QLineEdit#target:disabled { color:@ash; border-bottom-color:@line; }
QComboBox { background:@panel; border:1px solid @rule; border-radius:0; padding:8px 12px; color:@bone; font-family:'@mono'; font-size:13px; min-width:170px; }
QComboBox:hover { border-color:@ash; }
QComboBox:focus { border-color:@signal; }
QComboBox:disabled { color:@dim; border-color:@line; }
QComboBox::drop-down { border:0; width:30px; }
QComboBox QAbstractItemView { background:@panel; border:1px solid @rule; color:@bone; selection-background-color:@signal; selection-color:@ink; outline:0; padding:4px; font-family:'@mono'; }
QPushButton { background:transparent; color:@bone; border:1px solid @rule; border-radius:0; padding:9px 16px; font-family:'@display'; font-size:15px; letter-spacing:2px; }
QPushButton:hover { border-color:@bone; }
QPushButton:pressed { background:@raised; }
QPushButton:focus { border-color:@signal; }
QPushButton:disabled { color:@dim; border-color:@line; }
QPushButton#primary { background:@signal; color:@ink; border:0; padding:11px 30px; font-size:16px; letter-spacing:4px; }
QPushButton#primary:hover, QPushButton#primary:focus { background:@bright; }
QPushButton#primary:disabled { background:@raised; color:@ash; }
QPushButton#stop { padding:6px 14px; font-size:13px; }
QPushButton#stop:enabled { color:@alert; border-color:@alert; }
QPushButton#stop:enabled:hover { background:#2a0d0d; }
QPushButton#tab { background:transparent; border:0; border-bottom:2px solid transparent; color:@ash; padding:6px 0; font-family:'@display'; font-size:16px; letter-spacing:3px; }
QPushButton#tab:hover { color:@bone; }
QPushButton#tab:checked { color:@bone; border-bottom-color:@signal; }
QPushButton#tab:focus:!checked { border-bottom:1px dashed @ash; }
QTableWidget { background:@ink; border:0; color:@bone; gridline-color:@line; selection-background-color:@raised; selection-color:@bone; outline:0; font-family:'@mono'; font-size:13px; }
QTableWidget::item { padding:0 10px; border-bottom:1px solid @line; }
QHeaderView { background:@ink; border:0; }
QHeaderView::section { background:@ink; color:@ash; border:0; border-bottom:1px solid @rule; padding:8px 10px; font-family:'@mono'; font-size:11px; letter-spacing:2px; }
QTableCornerButton::section { background:@ink; border:0; }
QPlainTextEdit { background:@ink; border:0; color:@ash; font-family:'@mono'; font-size:12px; selection-background-color:@signal; selection-color:@ink; }
QListWidget { background:@ink; border:0; outline:0; }
QScrollBar:vertical { background:@ink; width:8px; margin:0; }
QScrollBar::handle:vertical { background:@rule; min-height:30px; }
QScrollBar::handle:vertical:hover { background:@ash; }
QScrollBar:horizontal { background:@ink; height:8px; margin:0; }
QScrollBar::handle:horizontal { background:@rule; min-width:30px; }
QScrollBar::handle:horizontal:hover { background:@ash; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QLabel#photo { background:@panel; border:1px solid @line; color:@dim; font-family:'@mono'; font-size:11px; letter-spacing:2px; }
QLabel#photoName { font-family:'@mono'; font-size:12px; color:@bone; padding-top:2px; }
QLabel#engineName { font-family:'@display'; font-size:17px; letter-spacing:1px; color:@bone; }
QLabel#engineMeta { font-family:'@mono'; font-size:10px; letter-spacing:1px; color:@ash; }
QFrame#engineRow { border:0; border-bottom:1px solid @line; }
QFrame#engineRow QLabel, QFrame#engineRow QCheckBox { background:transparent; }
QCheckBox { spacing:0; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid @rule; background:@panel; }
QCheckBox::indicator:hover { border-color:@signal; }
QCheckBox::indicator:checked { background:@signal; border-color:@signal; }
QCheckBox::indicator:disabled { background:@ink; border-color:@line; }
QCheckBox::indicator:checked:disabled { background:@dim; border-color:@dim; }
QPushButton#small { padding:5px 10px; font-size:13px; }
QScrollArea { border:0; }
QDialog { background:@panel; }
QDialog QLabel { background:transparent; }
QListWidget#faces { background:@ink; }
QListWidget#faces::item { color:@ash; font-family:'@mono'; font-size:11px; padding:4px; border:1px solid transparent; }
QListWidget#faces::item:hover { border-color:@rule; }
QListWidget#faces::item:selected { border-color:@signal; color:@bone; background:@raised; }
QFrame#leakFrame { background:@panel; border:0; border-left:3px solid @rule; }
QFrame#leakFrame[tone="ok"] { border-left-color:@signal; }
QFrame#leakFrame[tone="warn"] { border-left-color:@warn; }
QFrame#leakFrame[tone="bad"] { border-left-color:@alert; }
QFrame#leakFrame QLabel { background:transparent; }
QLabel#bigNumber { font-family:'@display'; font-size:58px; letter-spacing:2px; color:@dim; }
QLabel#bigNumber[tone="ok"] { color:@signal; }
QLabel#bigNumber[tone="warn"] { color:@warn; }
QLabel#bigNumber[tone="bad"] { color:@alert; }
QLabel#verdict { font-family:'@display'; font-size:22px; letter-spacing:3px; color:@bone; }
QMessageBox { background:@panel; }
QMessageBox QLabel { color:@bone; background:transparent; }
""")

STATES = engine.STATUS_LABELS
TONES = {"ok":"ok", "complete":"ok", "error":"err", "failed":"err", "blocked":"err", "missing":"warn", "timeout":"warn", "cancelled":"warn", "partial":"warn"}
BORN = Qt.ItemDataRole.UserRole + 1
FLASH = 1.4
EMPTY_IDLE = "No findings yet. Enter a target above and run a scan."
EMPTY_LIVE = "No findings yet. Results appear here as each source finishes."
EMPTY_DONE = "No findings. Check each source in Run log: an empty result doesn't prove the data isn't out there."

def motion_enabled():
    """Follow the Windows 'Animation effects' setting."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        value = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0)  # SPI_GETCLIENTAREAANIMATION
        return bool(value.value)
    except Exception:
        return True

MOTION = motion_enabled()

def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget

def button(text, callback, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(callback)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget

def set_prop(widget, name, value):
    """Change a stylesheet property and re-apply the style."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)

def font(family, size, spacing=0.0):
    value = QFont(family)
    value.setPixelSize(size)
    if spacing:
        value.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return value

def clamp(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t

def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3

def ease_back(t):
    t, c = clamp(t), 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

def tint(color, opacity):
    value = QColor(color)
    value.setAlphaF(clamp(opacity))
    return value

def blend(a, b, t):
    a, b, t = QColor(a), QColor(b), clamp(t)
    return QColor(round(a.red()+(b.red()-a.red())*t), round(a.green()+(b.green()-a.green())*t), round(a.blue()+(b.blue()-a.blue())*t))

def rim(centre, point, radius):
    dx, dy = point.x()-centre.x(), point.y()-centre.y()
    length = math.hypot(dx, dy) or 1
    return QPointF(centre.x()+dx/length*radius, centre.y()+dy/length*radius)

def draw_reticle(p, c, r, color, width=1.5):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(color, width))
    p.drawEllipse(c, r, r)
    for dx, dy in ((1,0), (-1,0), (0,1), (0,-1)):
        p.drawLine(QPointF(c.x()+dx*r*0.45, c.y()+dy*r*0.45), QPointF(c.x()+dx*r*1.5, c.y()+dy*r*1.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(c, max(1.2, r*0.12), max(1.2, r*0.12))

def owl_pixmap(size, dim=False):
    """The SpyBrain logo, a green night-vision owl; the dim version marks empty states."""
    pix = QPixmap(size*2, size*2)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    source = QPixmap(str(engine.ASSETS / "assets" / "owl.png"))
    if not source.isNull():
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(0.3 if dim else 1.0)
        p.drawPixmap(QRectF(0, 0, size, size), source, QRectF(source.rect()))
        p.end()
    return pix

class OwlLoop:
    """The animated logo (made with Kling 3.0 on Higgsfield), stored as a JPEG sprite sheet."""
    def __init__(self):
        try:
            self.meta = json.loads((engine.ASSETS / "assets" / "owl-loop.json").read_text(encoding="utf-8"))
            self.sheet = QPixmap(str(engine.ASSETS / "assets" / "owl-loop.jpg"))
        except (OSError, ValueError):
            self.meta, self.sheet = None, QPixmap()
    def ready(self):
        return self.meta is not None and not self.sheet.isNull()
    def draw(self, p, target, now):
        meta = self.meta
        index = int(now*meta["fps"]) % meta["frames"] if MOTION else 0
        row, col = divmod(index, meta["cols"])
        size = meta["size"]
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.drawPixmap(target, self.sheet, QRectF(col*size, row*size, size, size))
        p.restore()

def draw_status(p, x, cy, tone):
    """Status glyphs: filled square done, triangle needs attention, cross failed, hollow square idle."""
    color = QColor({"ok": BONE, "warn": WARN, "err": ALERT, "run": SIGNAL}.get(tone, DIM))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if tone == "ok":
        p.fillRect(QRectF(x, cy-4, 8, 8), color)
    elif tone == "warn":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([QPointF(x+4, cy-5), QPointF(x+9, cy+4), QPointF(x-1, cy+4)]))
    elif tone == "err":
        p.setPen(QPen(color, 1.8))
        p.drawLine(QPointF(x, cy-4), QPointF(x+8, cy+4))
        p.drawLine(QPointF(x+8, cy-4), QPointF(x, cy+4))
    else:
        p.setPen(QPen(color, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x+0.5, cy-3.5, 7, 7))
    p.restore()
    return color

def chevron(color, up=False):
    pix = QPixmap(28, 28)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
    points = [(3.5,9), (7,5.5), (10.5,9)] if up else [(3.5,5.5), (7,9), (10.5,5.5)]
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
    p.end()
    return pix

def asset_style():
    """Stylesheet rules that need generated images (combo box and sort arrows)."""
    folder = Path(tempfile.gettempdir()) / "osinthub-ui"
    folder.mkdir(exist_ok=True)
    paths = {}
    for name, color, up in (("down", ASH, False), ("sort-down", SIGNAL, False), ("sort-up", SIGNAL, True)):
        paths[name] = folder / f"{name}.png"
        chevron(color, up).save(str(paths[name]))
    return ("QComboBox::down-arrow { image:url(%s); width:14px; height:14px; }\n"
            "QHeaderView::down-arrow { image:url(%s); width:12px; height:12px; }\n"
            "QHeaderView::up-arrow { image:url(%s); width:12px; height:12px; }\n"
            % (paths["down"].as_posix(), paths["sort-down"].as_posix(), paths["sort-up"].as_posix()))

def apply_theme(app):
    app.setStyle("Fusion")
    palette = app.palette()
    for role, color in ((QPalette.ColorRole.Window, INK), (QPalette.ColorRole.Base, INK), (QPalette.ColorRole.Text, BONE),
                        (QPalette.ColorRole.WindowText, BONE), (QPalette.ColorRole.Button, PANEL), (QPalette.ColorRole.ButtonText, BONE),
                        (QPalette.ColorRole.Highlight, SIGNAL), (QPalette.ColorRole.HighlightedText, INK), (QPalette.ColorRole.PlaceholderText, "#56635a")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE + asset_style())

def dark_title_bar(window):
    """Black Windows title bar so the frame matches the app."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        for attribute, value in ((20, 1), (35, 0x00000000), (36, 0x00e4ebe2)):  # dark mode, caption colour, caption text
            data = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    except Exception:
        pass

class Pulse(QWidget):
    """Status dot; it sends out rings while something is running."""
    COLORS = {"run": SIGNAL, "ok": BONE, "warn": WARN, "err": ALERT}
    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 14)
        self.tone = "idle"
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
    def set_tone(self, tone):
        self.tone = tone
        if tone == "run" and MOTION:
            self.timer.start(40)
        else:
            self.timer.stop()
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, color = QPointF(7, 7), QColor(self.COLORS.get(self.tone, DIM))
        if self.tone == "run" and MOTION:
            t = (time.monotonic()*1.2) % 1
            p.setPen(QPen(tint(color, 0.8*(1-t)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 2.5+4.2*t, 2.5+4.2*t)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(c, 3, 3)

class EvidenceTag(QWidget):
    """Findings count drawn as a green evidence marker; it bumps when the count changes."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(58, 30)
        self.value, self.bumped = 0, 0.0
        self.number_font = font(DISPLAY, 18)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.setAccessibleName("Number of findings")
    def set_value(self, value):
        if value != self.value:
            self.value, self.bumped = value, time.monotonic()
            if MOTION:
                self.timer.start(16)
        self.update()
    def tick(self):
        if time.monotonic()-self.bumped > 0.4:
            self.timer.stop()
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        scale = 1 + 0.2*(1-ease_out((time.monotonic()-self.bumped)/0.35)) if MOTION else 1
        p.translate(w/2, h/2)
        p.scale(scale, scale)
        p.translate(-w/2, -h/2)
        tent = QPolygonF([QPointF(9, 2), QPointF(w-9, 2), QPointF(w-2, h-2), QPointF(2, h-2)])
        filled = self.value > 0
        p.setPen(Qt.PenStyle.NoPen if filled else QPen(QColor(RULE), 1))
        p.setBrush(QColor(SIGNAL) if filled else QColor(INK))
        p.drawPolygon(tent)
        p.setPen(QColor(INK) if filled else QColor(ASH))
        p.setFont(self.number_font)
        p.drawText(QRectF(0, 1, w, h), Qt.AlignmentFlag.AlignCenter, "999+" if self.value > 999 else str(self.value))

class TopBar(QFrame):
    """Wordmark, page tabs with a sliding signal underline, live indicator and UTC clock."""
    def __init__(self, items, on_select):
        super().__init__()
        self.setObjectName("topbar")
        self.setFixedHeight(58)
        row = QHBoxLayout(self)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(0)
        mark = QLabel()
        mark.setPixmap(owl_pixmap(46))
        mark.setAccessibleName("SpyBrain logo")
        row.addWidget(mark)
        row.addSpacing(10)
        row.addWidget(label("SPYBRAIN", "wordmark"))
        row.addSpacing(8)
        row.addWidget(label(engine.VERSION, "version"))
        row.addSpacing(36)
        self.buttons, self.pages = [], [page for _, page in items]
        for title, page in items:
            item = button(title, lambda checked=False, i=page: on_select(i), "nav")
            item.setCheckable(True)
            item.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self.buttons.append(item)
            row.addWidget(item)
        row.addStretch()
        self.pulse = Pulse()
        self.live = label("SCANNING", "live")
        row.addWidget(self.pulse)
        row.addSpacing(6)
        row.addWidget(self.live)
        row.addSpacing(22)
        self.clock = label("", "clock")
        row.addWidget(self.clock)
        self.set_live(False)
        self.indicator = QFrame(self)
        self.indicator.setObjectName("indicator")
        self.slide = QPropertyAnimation(self.indicator, b"geometry", self)
        self.slide.setDuration(280)
        self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.current = 0
        self.tick()
    def tick(self):
        self.clock.setText(f"UTC {dt.datetime.now(dt.timezone.utc):%H:%M:%S}")
    def set_live(self, live):
        self.pulse.setVisible(live)
        self.live.setVisible(live)
        self.pulse.set_tone("run" if live else "idle")
    def slot(self, index):
        g = self.buttons[index].geometry()
        return QRect(g.x()+14, self.height()-2, max(0, g.width()-28), 2)
    def button_for(self, page):
        return self.buttons[self.pages.index(page)]
    def select(self, page):
        index = self.pages.index(page)
        for i, item in enumerate(self.buttons):
            item.setChecked(i == index)
        moved, self.current = index != self.current, index
        if moved and MOTION and self.isVisible():
            self.slide.stop()
            self.slide.setStartValue(self.indicator.geometry())
            self.slide.setEndValue(self.slot(index))
            self.slide.start()
        else:
            self.indicator.setGeometry(self.slot(index))
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.slide.stop()
        self.indicator.setGeometry(self.slot(self.current))
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.indicator.setGeometry(self.slot(self.current)))

class LinkChart(QWidget):
    """Signature view: the target in the centre, a thread to every source, findings pinned to their source."""
    GHOSTS = ("ACCOUNTS", "DNS", "PHONE", "PHOTO")
    CAP = 24
    ANGLES = {1: [0], 2: [180, 0], 3: [180, 328, 32], 4: [212, 328, 32, 148]}
    COLORS = {"pending": DIM, "running": SIGNAL, "ok": BONE, "partial": WARN, "timeout": WARN, "missing": DIM, "cancelled": DIM, "error": ALERT}
    WORDS = {"pending": "QUEUED", "running": "SCANNING", "ok": "DONE", "partial": "PARTIAL", "timeout": "TIMED OUT",
             "error": "SOURCE ERROR", "missing": "NOT INSTALLED", "cancelled": "STOPPED"}
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.setAccessibleName("Link chart of the target, its sources and their findings")
        self.phase, self.target, self.kind, self.result = "idle", "", "", ""
        self.nodes, self.backdrop_key, self.backdrop_pix = [], None, None
        self.epoch = self.locked = self.ended = time.monotonic()
        self.name_font, self.word_font = font(DISPLAY, 15, 1), font(MONO, 10, 1.5)
        self.title_font, self.sub_font = font(DISPLAY, 18, 1), font(MONO, 10, 2)
        self.owl, self.owl_loop = owl_pixmap(150), OwlLoop()
        self.sweep_angle, self.sweep_clock = 0.0, time.monotonic()
        import random
        dice = random.Random(7)
        self.contacts = [(dice.uniform(0, 360), dice.uniform(46, 560), dice.uniform(0.6, 1.0)) for _ in range(30)]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16 if MOTION else 500)
        self.top = 0

    # State changes, called by the window.
    def idle(self):
        self.phase, self.target, self.nodes, self.epoch = "idle", "", [], time.monotonic()
    def begin(self, target, kind):
        self.phase, self.target, self.kind, self.nodes = "live", target, kind, []
        self.locked = time.monotonic()
    def plan(self, tools, quick=False):
        start = max(time.monotonic(), self.locked+(0.05 if quick else 0.35))
        step = 0.06 if quick else 0.12
        self.nodes = [{"name": name, "status": "pending", "born": start+i*step, "since": start, "count": 0, "pins": []} for i, name in enumerate(tools)]
    def report(self, name, status, count=None):
        node = next((n for n in self.nodes if n["name"] == name), None)
        if node is None:
            return
        now = time.monotonic()
        node["status"], node["since"] = status, now
        if count is not None:
            start, have = max(now, node["born"]+0.5), len(node["pins"])
            node["pins"] += [start+k*0.035 for k in range(min(count, self.CAP)-have)]
            node["count"] = count
    def finish(self, status):
        self.phase, self.result, self.ended = "done", status, time.monotonic()

    # Painting.
    def now(self):
        return time.monotonic() + (0 if MOTION else 1e6)
    def points(self, count, w, h, c):
        rx, ry = min(w*0.33, 430), h*0.28
        angles = self.ANGLES.get(count, [180+i*360/max(count, 1) for i in range(count)])
        return [QPointF(c.x()+rx*math.cos(math.radians(a)), c.y()+ry*math.sin(math.radians(a))) for a in angles]
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now, w, h = self.now(), self.width(), self.height()
        c = QPointF(w/2, (h+self.top)/2-10)
        if self.backdrop_key != (w, h):
            self.backdrop_pix, self.backdrop_key = self.backdrop(w, h, c), (w, h)
        p.drawPixmap(0, 0, self.backdrop_pix)
        if MOTION:
            self.advance_sweep()
            self.sweep(p, c, now, w, h)
            self.radar_contacts(p, c)
            if self.phase == "live":
                self.sonar(p, c, now)
        points = self.points(4 if self.phase == "idle" else len(self.nodes), w, h, c)
        if self.phase == "idle":
            for index, (name, point) in enumerate(zip(self.GHOSTS, points)):
                self.ghost(p, c, point, name, index, now)
        else:
            for node, point in zip(self.nodes, points):
                self.source(p, c, point, node, now)
        self.centre(p, c, now)
        self.crop_marks(p, w, h)
    def crop_marks(self, p, w, h):
        """Viewfinder corners; green while a scan runs."""
        p.setPen(QPen(QColor(SIGNAL if self.phase == "live" else ASH), 2))
        r, arm = QRectF(1, 1, w-2, h-2), 14
        for x, y, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1), (r.right(), r.bottom(), -1, -1), (r.left(), r.bottom(), 1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x+dx*arm, y))
            p.drawLine(QPointF(x, y), QPointF(x, y+dy*arm))
    def backdrop(self, w, h, c):
        ratio = self.devicePixelRatioF()
        pix = QPixmap(max(1, int(w*ratio)), max(1, int(h*ratio)))
        pix.setDevicePixelRatio(ratio)
        pix.fill(QColor(PANEL))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        step = 24
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint(BONE, 0.09))
        x = c.x() % step
        while x < w:
            y = c.y() % step
            while y < h:
                p.drawRect(QRectF(x-0.6, y-0.6, 1.2, 1.2))
                y += step
            x += step
        p.setPen(QPen(tint(BONE, 0.05), 1))
        p.drawLine(QPointF(0, c.y()), QPointF(w, c.y()))
        p.drawLine(QPointF(c.x(), 0), QPointF(c.x(), h))
        ring = QPen(tint(BONE, 0.07), 1, Qt.PenStyle.CustomDashLine)
        ring.setDashPattern([1, 5])
        p.setPen(ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in range(96, int(math.hypot(w, h)/2)+96, 96):
            p.drawEllipse(c, r, r)
        # Bearing bezel around the target, like a radar scope. Only north is labelled:
        # sources sit east and west of the target, and its name sits south.
        bezel = self.bezel_radius(h, c)
        p.setPen(QPen(tint(SIGNAL, 0.16), 1))
        p.drawEllipse(c, bezel, bezel)
        p.setFont(font(MONO, 9, 1))
        for bearing in range(0, 360, 5):
            a = math.radians(bearing-90)
            inner = bezel-(9 if bearing % 30 == 0 else 4)
            p.setPen(QPen(tint(SIGNAL, 0.32 if bearing % 30 == 0 else 0.16), 1))
            p.drawLine(QPointF(c.x()+math.cos(a)*inner, c.y()+math.sin(a)*inner), QPointF(c.x()+math.cos(a)*bezel, c.y()+math.sin(a)*bezel))
            if bearing == 0:
                p.setPen(tint(SIGNAL, 0.45))
                q = QPointF(c.x()+math.cos(a)*(bezel-20), c.y()+math.sin(a)*(bezel-20))
                p.drawText(QRectF(q.x()-14, q.y()-7, 28, 14), Qt.AlignmentFlag.AlignCenter, f"{bearing:03d}")
        # Faint scan lines, like a CRT.
        p.setPen(QPen(tint(BONE, 0.022), 1))
        for y in range(0, h, 3):
            p.drawLine(QPointF(0, y+0.5), QPointF(w, y+0.5))
        p.end()
        return pix
    def bezel_radius(self, h, c):
        return max(60.0, min(h-c.y()-10, c.y()-self.top+18))
    def sweep_speed(self):
        return 110.0 if self.phase == "live" else 34.0
    def advance_sweep(self):
        now = time.monotonic()
        self.sweep_angle = (self.sweep_angle+(now-self.sweep_clock)*self.sweep_speed()) % 360
        self.sweep_clock = now
    def since_sweep(self, angle):
        """Seconds since the sweep last crossed a screen bearing (degrees, clockwise from east)."""
        return ((self.sweep_angle-angle) % 360)/self.sweep_speed()
    def radar_contacts(self, p, c):
        """Faint contacts flare when the sweep passes them, then fade like phosphor."""
        live = self.phase == "live"
        p.setPen(Qt.PenStyle.NoPen)
        for angle, distance, strength in self.contacts:
            glow = math.exp(-self.since_sweep(angle)/1.6)*strength*(0.75 if live else 0.4)
            if glow < 0.03:
                continue
            a = math.radians(angle)
            q = QPointF(c.x()+math.cos(a)*distance, c.y()+math.sin(a)*distance)
            halo = QRadialGradient(q, 7)
            halo.setColorAt(0, tint(SIGNAL, glow*0.6))
            halo.setColorAt(1, tint(SIGNAL, 0))
            p.setBrush(QBrush(halo))
            p.drawEllipse(q, 7, 7)
            p.setBrush(tint(BRIGHT, glow))
            p.drawEllipse(q, 1.6, 1.6)
    def sonar(self, p, c, now):
        """Rings ripple out from the target while sources are being queried."""
        p.setBrush(Qt.BrushStyle.NoBrush)
        for phase in (0.0, 0.5):
            t = ((now-self.locked)/1.8+phase) % 1.0
            radius = 40+t*self.width()*0.45
            p.setPen(QPen(tint(SIGNAL, 0.35*(1-t)), 1.2))
            p.drawEllipse(c, radius, radius)
    def sweep(self, p, c, now, w, h):
        angle = self.sweep_angle
        strength = 0.13 if self.phase == "live" else 0.06
        gradient = QConicalGradient(c, (360-angle) % 360)
        gradient.setColorAt(0.0, tint(SIGNAL, strength))
        gradient.setColorAt(0.06, tint(SIGNAL, strength*0.4))
        gradient.setColorAt(0.25, tint(SIGNAL, 0))
        gradient.setColorAt(1.0, tint(SIGNAL, 0))
        r = math.hypot(w, h)/2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(c, r, r)
        a = math.radians(angle)
        p.setPen(QPen(tint(SIGNAL, 0.45 if self.phase == "live" else 0.22), 1.2))
        p.drawLine(rim(c, QPointF(c.x()+math.cos(a), c.y()+math.sin(a)), 34), QPointF(c.x()+math.cos(a)*r, c.y()+math.sin(a)*r))
    def thread(self, p, start, end, color, dashed):
        pen = QPen(color, 1)
        if dashed:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([2, 4])
        p.setPen(pen)
        p.drawLine(start, end)
    def diamond(self, p, c, size, fill, outline):
        p.setPen(QPen(outline, 1.4))
        p.setBrush(fill if fill is not None else QColor(PANEL))
        p.drawPolygon(QPolygonF([QPointF(c.x(), c.y()-size), QPointF(c.x()+size, c.y()), QPointF(c.x(), c.y()+size), QPointF(c.x()-size, c.y())]))
    def caption(self, p, c, point, name, word, name_color, word_color):
        """Captions sit on the inner side of the node, above and below its thread."""
        inner_left = point.x() < c.x()
        for text, face, colour, y in ((name, self.name_font, name_color, point.y()-9), (word, self.word_font, word_color, point.y()+21)):
            if not text:
                continue
            p.setFont(face)
            p.setPen(colour)
            width = QFontMetrics(face).horizontalAdvance(text)
            p.drawText(QPointF(point.x()+16 if inner_left else point.x()-16-width, y), text)
    def ghost(self, p, c, point, name, index, now):
        grow = ease_out((now-self.epoch-0.3-index*0.14)/0.7)
        if grow <= 0:
            return
        glow = 0.55+0.2*math.sin(now*1.4+index*1.7) if MOTION else 0.6
        start = rim(c, point, 86)
        self.thread(p, start, start+(point-start)*grow, tint(DIM, glow+0.2), True)
        if grow > 0.85:
            self.diamond(p, point, 5, None, tint(ASH, glow))
            self.caption(p, c, point, name, "", tint(ASH, glow), QColor(ASH))
    def source(self, p, c, point, node, now):
        grow = ease_out((now-node["born"])/0.55)
        if grow <= 0:
            return
        status = node["status"]
        color = QColor(self.COLORS.get(status, ASH))
        start = rim(c, point, 40)
        self.thread(p, start, start+(point-start)*grow, tint(color, 0.75), status == "pending")
        if status == "running" and MOTION and grow >= 1:
            # Packets travelling out to the source while it is being queried.
            for offset in (0.0, 0.5):
                t = ((now-node["since"])*0.75+offset) % 1.0
                q = start+(point-start)*t
                halo = QRadialGradient(q, 9)
                halo.setColorAt(0, tint(SIGNAL, 0.5))
                halo.setColorAt(1, tint(SIGNAL, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(halo))
                p.drawEllipse(q, 9, 9)
                p.fillRect(QRectF(q.x()-1.5, q.y()-1.5, 3, 3), QColor(BRIGHT))
        if grow < 0.9:
            return
        if MOTION:
            # The source flashes as the sweep crosses it.
            passed = self.since_sweep(math.degrees(math.atan2(point.y()-c.y(), point.x()-c.x())) % 360)
            if passed < 0.5:
                p.setPen(QPen(tint(SIGNAL, 0.8*(1-passed/0.5)), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(point, 8+18*passed/0.5, 8+18*passed/0.5)
        self.pins(p, c, point, node, now)
        if status == "running" and MOTION:
            spin = now*240
            box = QRectF(point.x()-13, point.y()-13, 26, 26)
            p.setPen(QPen(tint(SIGNAL, 0.85), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(box, int(spin*16), 70*16)
            p.drawArc(box, int((spin+180)*16), 70*16)
        self.diamond(p, point, 6.5, color if status in ("ok", "partial") else None, color)
        if status == "error":
            p.setPen(QPen(color, 1.6))
            p.drawLine(QPointF(point.x()-3, point.y()-3), QPointF(point.x()+3, point.y()+3))
            p.drawLine(QPointF(point.x()+3, point.y()-3), QPointF(point.x()-3, point.y()+3))
        word = self.WORDS.get(status, status.upper())
        if status in ("ok", "partial"):
            word += f" · {node['count']} FOUND"
        elif status == "running" and MOTION:
            dots = int(now*3) % 4
            word += "."*dots + " "*(3-dots)
        self.caption(p, c, point, node["name"], word, QColor(BONE), color)
    def pins(self, p, c, point, node, now):
        """Findings fan out on the outer side of their source, newest ones glowing green."""
        outward = math.atan2(point.y()-c.y(), point.x()-c.x())
        for k, born in enumerate(node["pins"]):
            pop = ease_back((now-born)/0.35)
            if pop <= 0:
                continue
            ring, slot = divmod(k, 8)
            a = outward+math.radians(-60+slot*120/7)
            r = 30+ring*13
            q = QPointF(point.x()+math.cos(a)*r, point.y()+math.sin(a)*r*0.7)
            p.setPen(QPen(tint(BONE, 0.16), 1))
            p.drawLine(point, point+(q-point)*min(pop, 1.0))
            s = 2.6*pop
            p.fillRect(QRectF(q.x()-s, q.y()-s, s*2, s*2), blend(SIGNAL, BONE, (now-born)/0.9))
        extra = node["count"]-self.CAP
        if extra > 0 and node["pins"] and now > node["pins"][-1]:
            q = QPointF(point.x()+math.cos(outward)*80, point.y()+math.sin(outward)*80*0.7)
            p.setFont(self.word_font)
            p.setPen(QColor(ASH))
            p.drawText(QRectF(q.x()-30, q.y()-8, 60, 16), Qt.AlignmentFlag.AlignCenter, f"+{extra}")
    def watcher(self, p, c, now, opacity):
        """The owl logo waits in the centre until a target is set."""
        glow = QRadialGradient(c, 105)
        glow.setColorAt(0, tint(SIGNAL, (0.10+0.04*math.sin(now*1.6) if MOTION else 0.1)*opacity))
        glow.setColorAt(1, tint(SIGNAL, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, 105, 105)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tint(ASH, 0.35*opacity), 1))
        spin = now*14 if MOTION else 0
        box = QRectF(c.x()-78, c.y()-78, 156, 156)
        for k in range(3):
            p.drawArc(box, int((spin+k*120)*16), 70*16)
        p.setOpacity(opacity)
        if self.owl_loop.ready():
            self.owl_loop.draw(p, QRectF(c.x()-75, c.y()-80, 150, 150), now)
        else:
            p.drawPixmap(QPointF(c.x()-75, c.y()-80), self.owl)
        p.setOpacity(1)
    def centre(self, p, c, now):
        idle, live = self.phase == "idle", self.phase == "live"
        lock = 1.0 if idle else ease_out((now-self.locked)/0.5)
        if idle:
            tone = QColor(ASH)
        elif live:
            tone = QColor(SIGNAL)
        else:
            tone = QColor(ALERT if self.result == "failed" else ASH if self.result == "cancelled" else BONE)
        spin = now*(70 if live else 14) if MOTION else 0
        if idle or lock < 1:
            self.watcher(p, c, now, 1.0 if idle else 1-lock)
        if not idle:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(tint(tone, 0.45*lock), 1))
            box = QRectF(c.x()-30, c.y()-30, 60, 60)
            for k in range(3):
                p.drawArc(box, int((spin+k*120)*16), 70*16)
            draw_reticle(p, c, 15, tint(tone, lock))
            # Lock-on brackets close in when a scan starts.
            m, arm = 22+(1-lock)*46, 8
            p.setPen(QPen(tint(tone, 0.95), 1.6))
            for sx, sy in ((-1,-1), (1,-1), (1,1), (-1,1)):
                corner = QPointF(c.x()+sx*m, c.y()+sy*m)
                p.drawLine(corner, QPointF(corner.x()-sx*arm, corner.y()))
                p.drawLine(corner, QPointF(corner.x(), corner.y()-sy*arm))
        if self.phase == "done" and MOTION:
            t = (now-self.ended)/0.9
            if t < 1:
                p.setPen(QPen(tint(tone, 0.6*(1-t)), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                radius = 15+60*ease_out(t)
                p.drawEllipse(c, radius, radius)
        sub = "NO TARGET" if idle else f"TARGET · {engine.KINDS.get(self.kind, self.kind).upper()}"
        p.setFont(self.sub_font)
        p.setPen(QColor(ASH))
        p.drawText(QRectF(c.x()-200, c.y()+(80 if idle else 38), 400, 16), Qt.AlignmentFlag.AlignCenter, sub)
        if not idle:
            p.setFont(self.title_font)
            p.setPen(QColor(BONE))
            title = QFontMetrics(self.title_font).elidedText(self.target, Qt.TextElideMode.ElideMiddle, 300)
            p.drawText(QRectF(c.x()-170, c.y()+54, 340, 24), Qt.AlignmentFlag.AlignCenter, title)

class FindingsDelegate(QStyledItemDelegate):
    """New findings glow green for a moment; the selected row gets a signal bar."""
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        born = index.siblingAtColumn(0).data(BORN)
        if born and MOTION:
            age = time.monotonic()-born
            if age < 0:
                painter.fillRect(option.rect, QColor(INK))
            elif age < FLASH:
                painter.fillRect(option.rect, tint(SIGNAL, 0.13*(1-age/FLASH)**2))
                if age < 0.25:
                    painter.fillRect(QRectF(option.rect.left(), option.rect.bottom()-1, option.rect.width()*ease_out(age/0.25), 1), QColor(SIGNAL))
        if option.state & QStyle.StateFlag.State_Selected and index.column() == 0:
            painter.fillRect(QRectF(option.rect.left(), option.rect.top(), 3, option.rect.height()), QColor(SIGNAL))

HISTORY_COLUMNS = (("WHEN", 0, 150), ("TYPE", 165, 110), ("TARGET", 290, -270), ("FINDINGS", -250, 100), ("STATUS", -140, 140))
SOURCE_COLUMNS = (("STATUS", 0, 160), ("SOURCE", 175, 170), ("CHECKS", 360, -260), ("USED FOR", -240, 240))

def cells(columns, rect):
    out = []
    for _, x, width in columns:
        left = rect.left()+(x if x >= 0 else rect.width()+x)
        right = left+width if width >= 0 else rect.right()+width
        out.append(QRectF(left, rect.top(), max(0.0, right-left-12), rect.height()))
    return out

class LedgerHeader(QWidget):
    def __init__(self, columns):
        super().__init__()
        self.columns = columns
        self.setFixedHeight(32)
        self.caption_font = font(MONO, 11, 2)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self.caption_font)
        p.setPen(QColor(ASH))
        for (title, _, _), cell in zip(self.columns, cells(self.columns, QRectF(self.rect()).adjusted(16, 0, -16, 0))):
            p.drawText(cell, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QColor(RULE))
        p.drawLine(0, self.height()-1, self.width(), self.height()-1)

class LedgerDelegate(QStyledItemDelegate):
    """Draws History and Sources rows as aligned ledger lines."""
    COLORS = {"mono": ASH, "micro": ASH}
    def __init__(self, columns, parent):
        super().__init__(parent)
        self.columns = columns
        self.fonts = {"mono": font(MONO, 13), "count": font(MONO, 13), "micro": font(MONO, 11, 2), "display": font(DISPLAY, 19, 0.5),
                      "body": font(BODY, 14), "status": font(MONO, 12, 1.5)}
    def sizeHint(self, option, index):
        return QSize(0, 54)
    def paint(self, p, option, index):
        data = index.data(Qt.ItemDataRole.UserRole) or {}
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            p.fillRect(r, QColor(RAISED))
            p.fillRect(QRectF(r.left(), r.top(), 3, r.height()), QColor(SIGNAL))
        elif option.state & QStyle.StateFlag.State_MouseOver and "empty" not in data:
            p.fillRect(r, QColor(HOVER))
        p.setPen(QColor(LINE))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        if "empty" in data:
            p.setFont(self.fonts["mono"])
            p.setPen(QColor(ASH))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, data["empty"])
            p.restore()
            return
        for (text, style), cell in zip(data["cells"], cells(self.columns, r.adjusted(16, 0, -16, 0))):
            if style.startswith("status:"):
                color = draw_status(p, cell.left(), cell.center().y(), style.split(":")[1])
                p.setFont(self.fonts["status"])
                p.setPen(color)
                p.drawText(cell.adjusted(18, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text.upper())
                continue
            face = self.fonts[style]
            p.setFont(face)
            p.setPen(QColor(self.COLORS.get(style, BONE)))
            p.drawText(cell, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, QFontMetrics(face).elidedText(text, Qt.TextElideMode.ElideMiddle, int(cell.width())))
        p.restore()

class BreachTimeline(QWidget):
    """Breaches by year as stacked squares. Height is how many breaches that year; colour is what was
    exposed: red passwords, amber personal data, green only the address. Columns rise in year by year."""
    COLORS = {3: ALERT, 2: WARN, 1: SIGNAL, 0: ASH}
    ALPHA = {3: 0.95, 2: 0.9, 1: 0.6, 0: 0.55}
    NAMES = {3: "PASSWORDS", 2: "PERSONAL DATA", 1: "EMAIL ONLY", 0: "NOT LISTED"}
    picked = Signal(str)
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(178)
        self.setMouseTracking(True)
        self.setAccessibleName("Timeline of the breaches that expose this address")
        self.breaches, self.cells, self.state, self.message = [], [], "idle", ""
        self.born, self.hover, self.selected = 0.0, None, ""
        self.small_font, self.big_font = font(MONO, 10, 1), font(MONO, 12, 3)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33 if MOTION else 500)

    # State changes, called by the window.
    def reset(self):
        self.breaches, self.cells, self.state, self.message, self.hover, self.selected = [], [], "idle", "", None, ""
    def begin_check(self):
        self.reset()
        self.state, self.born = "checking", time.monotonic()
    def show_breaches(self, breaches):
        self.reset()
        self.breaches, self.born = list(breaches), time.monotonic()
        self.state = "found" if breaches else "clean"
    def show_error(self, message):
        self.reset()
        self.state, self.message, self.born = "error", message, time.monotonic()
    def highlight(self, name):
        self.selected = name

    def slots(self):
        """Year columns, oldest first; 0 stands for breaches with no usable date."""
        known = sorted({leaks.year_of(b) for b in self.breaches} - {0})
        last = max([dt.date.today().year] + known)
        first = min(known + [last-9])
        return ([0] if any(not leaks.year_of(b) for b in self.breaches) else []) + list(range(first, last+1))

    # Painting.
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        now = time.monotonic() + (0 if MOTION else 1e6)
        p.fillRect(self.rect(), QColor(PANEL))
        left, right, top, base = 18.0, w-18.0, 34.0, h-30.0
        self.cells = []
        p.setPen(QPen(tint(BONE, 0.22), 1))
        p.drawLine(QPointF(left, base+3), QPointF(right, base+3))
        if self.state == "found":
            self.paint_columns(p, now, left, right, top, base)
            self.paint_legend(p, w)
        else:
            self.paint_message(p, now, left, right, top, base, h)
        p.setPen(QPen(QColor(SIGNAL if self.state in ("checking", "found") else ASH), 2))
        r, arm = QRectF(1, 1, w-2, h-2), 14
        for x, y, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1), (r.right(), r.bottom(), -1, -1), (r.left(), r.bottom(), 1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x+dx*arm, y))
            p.drawLine(QPointF(x, y), QPointF(x, y+dy*arm))
    def paint_columns(self, p, now, left, right, top, base):
        slots = self.slots()
        stacks = {slot: [] for slot in slots}
        for breach in self.breaches:
            stacks[leaks.year_of(breach)].append(breach)
        for stack in stacks.values():
            stack.sort(key=lambda b: (-leaks.severity(b), -(b.get("records") or 0)))
        most = max(len(stack) for stack in stacks.values())
        colw = (right-left)/len(slots)
        size = max(2.0, min(14.0, (base-top)/most-1.0))
        step = size+1.0
        wide = min(colw*0.72, max(size, 24.0))
        every = 1 if colw >= 34 else 2 if colw >= 20 else 5
        p.setFont(self.small_font)
        for k, slot in enumerate(slots):
            cx = left+colw*(k+0.5)
            if slot == 0 or (slots[-1]-slot) % every == 0:
                p.setPen(tint(ASH, 0.8))
                p.drawText(QRectF(cx-22, base+7, 44, 14), Qt.AlignmentFlag.AlignCenter, "?" if slot == 0 else str(slot))
            for i, breach in enumerate(stacks[slot]):
                t = ease_out((now-self.born-k*0.045-i*0.012)/0.3)
                if t <= 0:
                    continue
                severity = leaks.severity(breach)
                rect = QRectF(cx-wide/2, base-(i+1)*step+(1-t)*14, wide, size)
                self.cells.append((rect, breach))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(tint(self.COLORS[severity], self.ALPHA[severity]*t))
                p.drawRect(rect)
                if breach is self.hover or breach["name"] == self.selected:
                    p.setPen(QPen(QColor(BONE), 2 if breach["name"] == self.selected else 1.2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5))
        lead = (now-self.born)/0.045
        if MOTION and 0 <= lead < len(slots)+4:
            x = left+colw*lead
            p.setPen(QPen(tint(SIGNAL, 0.6*(1-lead/(len(slots)+4))), 1))
            p.drawLine(QPointF(x, top-6), QPointF(x, base+3))
        shown = self.hover or next((b for b in self.breaches if b["name"] == self.selected), None)
        p.setFont(self.small_font)
        if shown:
            parts = (shown["name"].upper(), shown["date"], f"{shown['records']:,} records" if shown.get("records") else "")
            p.setPen(QColor(BONE))
            p.drawText(QPointF(left, 20), " · ".join(part for part in parts if part))
        else:
            p.setPen(tint(ASH, 0.75))
            p.drawText(QPointF(left, 20), "HOVER A BLOCK FOR DETAILS · CLICK TO FIND IT IN THE LIST")
    def paint_legend(self, p, w):
        p.setFont(self.small_font)
        metrics = QFontMetrics(self.small_font)
        x = w-18.0
        present = {leaks.severity(b) for b in self.breaches}
        for severity in (s for s in (0, 1, 2, 3) if s in present):
            name = self.NAMES[severity]
            x -= metrics.horizontalAdvance(name)
            p.setPen(tint(ASH, 0.9))
            p.drawText(QPointF(x, 20), name)
            x -= 14
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tint(self.COLORS[severity], self.ALPHA[severity]))
            p.drawRect(QRectF(x, 12, 8, 8))
            x -= 18
    def paint_message(self, p, now, left, right, top, base, h):
        area = QRectF(left, top, right-left, base-top)
        p.setFont(self.big_font)
        if self.state == "checking":
            if MOTION:
                x = left+((now-self.born)*0.45 % 1.0)*(right-left)
                glow = QLinearGradient(QPointF(x-150, 0), QPointF(x, 0))
                glow.setColorAt(0, tint(SIGNAL, 0))
                glow.setColorAt(1, tint(SIGNAL, 0.22))
                p.save()
                p.setClipRect(QRectF(left, 0, right-left, h))
                p.fillRect(QRectF(x-150, top-8, 150, base-top+11), QBrush(glow))
                p.setPen(QPen(tint(SIGNAL, 0.7), 1))
                p.drawLine(QPointF(x, top-8), QPointF(x, base+3))
                p.restore()
            p.setPen(tint(SIGNAL, 0.55+0.3*math.sin(now*3) if MOTION else 0.7))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "CHECKING BREACH DATABASES")
        elif self.state == "clean":
            p.setPen(QColor(SIGNAL))
            p.drawText(QRectF(area.left(), area.top(), area.width(), area.height()/2+8), Qt.AlignmentFlag.AlignCenter, "NO BREACHES FOUND")
            p.setFont(self.small_font)
            p.setPen(QColor(ASH))
            p.drawText(QRectF(area.left(), area.center().y()+10, area.width(), 20), Qt.AlignmentFlag.AlignCenter, "In the sources checked. That isn't a guarantee.")
        elif self.state == "error":
            p.setFont(self.small_font)
            p.setPen(QColor(WARN))
            p.drawText(area.adjusted(40, 0, -40, 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
        else:
            p.setPen(QColor(DIM))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "RUN A CHECK TO SEE WHEN THIS ADDRESS WAS EXPOSED")

    # Interaction.
    def cell_at(self, point):
        for rect, breach in reversed(self.cells):
            if rect.adjusted(-1, -1, 1, 1).contains(point):
                return breach
        return None
    def mouseMoveEvent(self, event):
        self.hover = self.cell_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover else Qt.CursorShape.ArrowCursor)
    def leaveEvent(self, event):
        self.hover = None
    def mousePressEvent(self, event):
        breach = self.cell_at(event.position())
        if breach:
            self.selected = breach["name"]
            self.picked.emit(self.selected)

SOURCE_INFO = {
    "sherlock": ("Sherlock", "Accounts on social and community sites", "USERNAME · EMAIL"),
    "maigret": ("Maigret", "Accounts, public IDs and tags", "USERNAME · EMAIL"),
    "theHarvester": ("theHarvester", "Hosts, IP addresses and emails a domain exposes publicly", "DOMAIN · EMAIL"),
    "PhoneInfoga": ("PhoneInfoga", "Public links for a phone number", "PHONE"),
    "DNS": ("DNS", "A, AAAA, MX, NS, TXT and CAA records", "DOMAIN · EMAIL"),
    "EXIF": ("EXIF", "Photo metadata, GPS and SHA-256, read on this computer", "PHOTO METADATA"),
    "libphonenumber": ("libphonenumber", "Numbering plan, region and number format", "PHONE"),
    "GeoCLIP": ("GeoCLIP", "Estimates where a photo was taken, on this computer", "PHOTO LOCATION"),
    "Gemini": ("Gemini", "Estimates photo location with Google's vision model (your key)", "PHOTO LOCATION"),
    "Claude": ("Claude", "Estimates photo location with Anthropic's vision model (your key)", "PHOTO LOCATION"),
    "Google Vision": ("Google Vision", "Recognises landmarks with exact coordinates (your key)", "PHOTO LOCATION"),
    "Web matches": ("Web matches", "Pages where the photo or an edited copy appears (Google Vision key)", "PHOTO WEB"),
    "Face search": ("Face search", "Same face on public pages; age-checked, purpose required (FaceCheck.ID key)", "PHOTO FACES"),
    "Leaks": ("Leaks", "Breaches that expose an email: XposedOrNot, plus Have I Been Pwned with your key", "EMAIL · LEAKS PAGE"),
}

GUIDE = [
    ("USERNAME", "Sherlock · Maigret", "Sherlock and Maigret look for the same name on public sites. Each hit is a candidate: someone else may use the same name. A name with a dot can be detected as a domain; set the type to Username."),
    ("DOMAIN", "DNS · theHarvester", "DNS records (A, AAAA, MX, NS, TXT, CAA) plus the hosts, IP addresses and emails that theHarvester finds in public sources."),
    ("EMAIL", "Leaks · Sherlock · Maigret · DNS · theHarvester", "The whole address is checked in known data breaches. The name before @ is searched as a username, and a company domain is checked too. This doesn't confirm that the mailbox exists or who owns it."),
    ("PHONE", "libphonenumber · PhoneInfoga", "libphonenumber reads the numbering plan and PhoneInfoga adds public links. Numbers without a country code are treated as Slovak. This doesn't identify the owner or a live location."),
    ("PHOTO METADATA", "EXIF", "Scan page: dimensions, SHA-256, EXIF and any GPS coordinates stored in the file are read on this computer; the photo is never uploaded. JPEG, PNG, TIFF, WebP and BMP are supported."),
    ("PHOTO LOCATION", "GeoCLIP · Gemini · Claude · Google Vision", "Photo page: estimates where a photo was taken. GeoCLIP runs on this computer; Gemini, Claude and Google Vision (landmarks with exact coordinates) use your own API key and receive the photo without EXIF. Expect the right region, rarely the exact spot."),
    ("WEB & FACES", "Google Vision · FaceCheck.ID", "Web matches lists pages where the photo or an edited copy appears. Face search looks for the same face on public pages: it needs a stated purpose and is blocked for children and teenagers by an age check on this computer. A matching face is a lead, not an identification."),
    ("LEAKS", "XposedOrNot · Have I Been Pwned · Pwned Passwords", "Leaks page: shows which known breaches expose an email address, when, and what kind of data they leaked. A password is checked without leaving this computer: only a 5-character hash prefix is sent. Leaked passwords and records are never shown or saved. No result doesn't mean an address is safe."),
    ("STOP & SAVE", "HTML · JSON · CSV", "Stop ends the running tools and keeps finished results; a DNS query may finish a few seconds later. Every scan is saved as HTML, JSON and CSV, and Export saves a copy where you choose."),
]

def guide_rows():
    """The guide, with the photo rows matching the engines this version offers."""
    if set(geolocate.ENABLED_ENGINES) - {"geoclip"}:
        return GUIDE
    local = ("PHOTO LOCATION", "GeoCLIP", "Photo page: estimates where a photo was taken by comparing it with 100,000 places worldwide. It runs on this computer, "
             "needs no key and no internet after a one-time model download, and never uploads the photo. Expect the right region, rarely the exact spot.")
    rows = []
    for row in GUIDE:
        if row[0] == "PHOTO LOCATION":
            rows.append(local)
        elif row[0] != "WEB & FACES":
            rows.append(row)
    return rows

def photo_groups():
    """Which kinds of photo results this version can produce: LOCATION, WEB, FACES."""
    return {geolocate.ENGINES[name]["group"] for name in geolocate.ENABLED_ENGINES}

class WorldMap(QWidget):
    """Dot-matrix world map. Probes ping while engines work, pins drop in, the view zooms to them
    and a crosshair locks onto the best estimate. EXIF GPS, if present, is linked to each estimate."""
    SHAPES = {"GeoCLIP": "diamond", "Gemini": "circle", "Claude": "square", "Google Vision": "triangle"}
    WORLD = QRectF(-180, -90, 360, 180)
    DOT = 5
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.setMouseTracking(True)
        self.setAccessibleName("World map of the estimated photo locations")
        self.land, self.mask = self.load_land()
        self.pins, self.truth, self.cursor = [], None, None
        self.view_from = self.view_to = QRectF(self.WORLD)
        self.moved, self.locked = 0.0, 0.0
        self.scanning, self.scan_started = False, 0.0
        self.base_key, self.base_pix = None, None
        self.label_font, self.small_font, self.big_font = font(DISPLAY, 13, 1), font(MONO, 10, 1), font(MONO, 11, 2)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33 if MOTION else 500)
    @staticmethod
    def load_land():
        import numpy as np
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        try:
            with gzip.open(engine.ASSETS / "assets" / "geo" / "land.json.gz", "rt", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return path, np.zeros((720, 1440), bool)
        scale = data["scale"]
        for ring in data["rings"]:
            path.addPolygon(QPolygonF([QPointF(ring[i]/scale, -ring[i+1]/scale) for i in range(0, len(ring), 2)]))
            path.closeSubpath()
        # Land mask at 0.25 degree per pixel, used to place the dot matrix.
        image = QImage(1440, 720, QImage.Format.Format_Grayscale8)
        image.fill(0)
        p = QPainter(image)
        p.translate(720, 360)
        p.scale(4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(path)
        p.end()
        stride = image.bytesPerLine()
        raw = np.frombuffer(image.constBits(), np.uint8, count=stride*720).reshape(720, stride)[:, :1440]
        return path, raw > 127

    # State changes, called by the window.
    def clear(self):
        self.pins, self.truth = [], None
        self.zoom_to(QRectF(self.WORLD))
    def add(self, engine_name, spots):
        now = time.monotonic()
        for rank, spot in enumerate(spots):
            self.pins.append({"engine": engine_name, "rank": rank, "lat": spot["lat"], "lon": spot["lon"],
                              "place": spot.get("place", ""), "born": now+rank*0.12})
    def set_scanning(self, scanning):
        self.scanning, self.scan_started = scanning, time.monotonic()
    def best(self):
        tops = [p for p in self.pins if p["rank"] == 0]
        return tops[0] if tops else None
    def fit(self):
        points = [(p["lon"], -p["lat"]) for p in self.pins]
        if self.truth:
            points.append((self.truth["lon"], -self.truth["lat"]))
        if not points:
            return self.zoom_to(QRectF(self.WORLD))
        xs, ys = [x for x, _ in points], [y for _, y in points]
        rect = QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys))
        pad = max(rect.width(), rect.height())*0.35+8
        rect = rect.adjusted(-pad, -pad, pad, pad)
        aspect = max(0.5, self.width()/max(1, self.height()))
        if rect.width()/rect.height() < aspect:
            grow = rect.height()*aspect-rect.width()
            rect = rect.adjusted(-grow/2, 0, grow/2, 0)
        else:
            grow = rect.width()/aspect-rect.height()
            rect = rect.adjusted(0, -grow/2, 0, grow/2)
        if rect.width() > 360 or rect.height() > 180:
            rect = QRectF(self.WORLD)
        rect.moveLeft(min(max(rect.left(), -180), 180-rect.width()))
        rect.moveTop(min(max(rect.top(), -90), 90-rect.height()))
        self.zoom_to(rect)
        self.locked = time.monotonic()+0.6
    def zoom_to(self, rect):
        self.view_from, self.view_to, self.moved = self.current_view(), rect, time.monotonic()

    # Painting.
    def current_view(self):
        t = ease_out((time.monotonic()-self.moved)/0.9) if MOTION else 1.0
        a, b = self.view_from, self.view_to
        return QRectF(a.x()+(b.x()-a.x())*t, a.y()+(b.y()-a.y())*t, a.width()+(b.width()-a.width())*t, a.height()+(b.height()-a.height())*t)
    def mapping(self, view, w, h):
        s = min(w/view.width(), h/view.height())
        return s, (w-view.width()*s)/2-view.x()*s, (h-view.height()*s)/2-view.y()*s
    def base(self, view, w, h):
        import numpy as np
        key = (w, h, round(view.x(), 3), round(view.y(), 3), round(view.width(), 3), round(view.height(), 3))
        if key == self.base_key:
            return self.base_pix
        ratio = self.devicePixelRatioF()
        pix = QPixmap(max(1, int(w*ratio)), max(1, int(h*ratio)))
        pix.setDevicePixelRatio(ratio)
        pix.fill(QColor(INK))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s, ox, oy = self.mapping(view, w, h)
        p.fillRect(QRectF(-180*s+ox, -90*s+oy, 360*s, 180*s), QColor(PANEL))
        # Dot matrix: one dot every DOT px, bright on land, faint on sea.
        xs = np.arange(self.DOT/2, w, self.DOT)
        ys = np.arange(self.DOT/2, h, self.DOT)
        gx, gy = np.meshgrid(xs, ys)
        lon, lat = (gx-ox)/s, -(gy-oy)/s
        inside = (np.abs(lon) <= 180) & (np.abs(lat) <= 90)
        col = np.clip(((lon+180)*4).astype(int), 0, 1439)
        row = np.clip(((90-lat)*4).astype(int), 0, 719)
        land = inside & self.mask[row, col]
        sea = inside & ~land
        for selection, color, size in ((sea, tint(BONE, 0.05), 1.0), (land, tint(SIGNAL, 0.34), 1.8)):
            pen = QPen(color, size)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(QPolygonF([QPointF(x, y) for x, y in zip(gx[selection].tolist(), gy[selection].tolist())]))
        p.save()
        p.translate(ox, oy)
        p.scale(s, s)
        outline = QPen(tint(SIGNAL, 0.16), 0)
        outline.setCosmetic(True)
        p.setPen(outline)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self.land)
        p.restore()
        step = 30 if view.width() > 120 else 10 if view.width() > 40 else 5 if view.width() > 15 else 1
        p.setFont(self.small_font)
        for lon_line in range(-180, 181, step):
            x = lon_line*s+ox
            p.setPen(QPen(tint(BONE, 0.05), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, max(0, -90*s+oy)), QPointF(x, min(h, 90*s+oy)))
            p.setPen(tint(ASH, 0.55))
            p.drawText(QPointF(x+3, h-6), f"{abs(lon_line)}°{'E' if lon_line > 0 else 'W' if lon_line < 0 else ''}")
        for lat_line in range(-90, 91, step):
            y = -lat_line*s+oy
            p.setPen(QPen(tint(BONE, 0.05), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(max(0, -180*s+ox), y), QPointF(min(w, 180*s+ox), y))
            p.setPen(tint(ASH, 0.55))
            p.drawText(QPointF(4, y-3), f"{abs(lat_line)}°{'N' if lat_line > 0 else 'S' if lat_line < 0 else ''}")
        p.end()
        self.base_key, self.base_pix = key, pix
        return pix
    def mouseMoveEvent(self, event):
        self.cursor = event.position()
    def leaveEvent(self, event):
        self.cursor = None
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now, w, h = time.monotonic()+(0 if MOTION else 1e6), self.width(), self.height()
        view = self.current_view()
        p.drawPixmap(0, 0, self.base(view, w, h))
        s, ox, oy = self.mapping(view, w, h)
        screen = lambda lat, lon: QPointF(lon*s+ox, -lat*s+oy)
        if MOTION:
            self.scanlines(p, now, w, h)
        if self.scanning and MOTION:
            self.probes(p, now, w, h, s, ox, oy)
        if self.truth:
            self.truth_links(p, screen)
        for pin in sorted(self.pins, key=lambda pin: -pin["rank"]):
            self.pin(p, pin, screen, now)
        self.lock_on(p, screen, now, w, h)
        self.legend(p, h)
        if not self.pins and not self.scanning:
            p.setFont(self.big_font)
            p.setPen(tint(ASH, 0.55+0.25*math.sin(now*2.2) if MOTION else 0.6))
            p.drawText(QRectF(0, h/2-10, w, 20), Qt.AlignmentFlag.AlignCenter, "NO ESTIMATES YET")
        if self.cursor is not None:
            lon, lat = (self.cursor.x()-ox)/s, -(self.cursor.y()-oy)/s
            if abs(lat) <= 90 and abs(lon) <= 180:
                p.setFont(self.small_font)
                p.setPen(QColor(ASH))
                p.drawText(QRectF(0, 6, w-12, 16), Qt.AlignmentFlag.AlignRight,
                           f"{abs(lat):.4f}° {'N' if lat >= 0 else 'S'}   {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}")
        p.setPen(QPen(QColor(SIGNAL if self.scanning else ASH), 2))
        r, arm = QRectF(1, 1, w-2, h-2), 14
        for x, y, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1), (r.right(), r.bottom(), -1, -1), (r.left(), r.bottom(), 1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x+dx*arm, y))
            p.drawLine(QPointF(x, y), QPointF(x, y+dy*arm))
    def scanlines(self, p, now, w, h):
        """A faint band rolls down the screen, like a monitor refreshing."""
        y = (now*40) % (h+120)-60
        band = QLinearGradient(QPointF(0, y-40), QPointF(0, y))
        band.setColorAt(0, tint(SIGNAL, 0))
        band.setColorAt(1, tint(SIGNAL, 0.05 if not self.scanning else 0.08))
        p.fillRect(QRectF(0, y-40, w, 40), QBrush(band))
    def probes(self, p, now, w, h, s, ox, oy):
        """While engines work: a vertical beam sweeps and probes ping random places on land."""
        x = ((now-self.scan_started)*0.32 % 1.0)*(w+160)-80
        beam = QLinearGradient(QPointF(x-120, 0), QPointF(x, 0))
        beam.setColorAt(0, tint(SIGNAL, 0))
        beam.setColorAt(1, tint(SIGNAL, 0.18))
        p.fillRect(QRectF(x-120, 0, 120, h), QBrush(beam))
        p.setPen(QPen(tint(SIGNAL, 0.7), 1))
        p.drawLine(QPointF(x, 0), QPointF(x, h))
        p.setBrush(Qt.BrushStyle.NoBrush)
        slot = int(now*5)
        for k in range(10):
            seed = (slot-k)*7919+k*104729
            lon, lat = (seed*37 % 3600)/10-180, (seed*53 % 1400)/10-70
            if not self.mask[int((90-lat)*4) % 720, int((lon+180)*4) % 1440]:
                continue
            age = (now*5-(slot-k))/5
            q = QPointF(lon*s+ox, -lat*s+oy)
            p.setPen(QPen(tint(SIGNAL, 0.8*(1-age/2)), 1))
            p.drawEllipse(q, 2+10*age, 2+10*age)
            p.fillRect(QRectF(q.x()-1, q.y()-1, 2, 2), tint(BRIGHT, 1-age/2))
    def truth_links(self, p, screen):
        """EXIF GPS is the ground truth: link it to each engine's best estimate with the distance."""
        t = screen(self.truth["lat"], self.truth["lon"])
        dashed = QPen(tint(BONE, 0.55), 1, Qt.PenStyle.CustomDashLine)
        dashed.setDashPattern([3, 3])
        dashed.setDashOffset(-(time.monotonic()*8) % 6 if MOTION else 0)
        p.setFont(self.small_font)
        for pin in self.pins:
            if pin["rank"] != 0:
                continue
            q = screen(pin["lat"], pin["lon"])
            p.setPen(dashed)
            p.drawLine(t, q)
            km = geolocate.distance_km((self.truth["lat"], self.truth["lon"]), (pin["lat"], pin["lon"]))
            p.setPen(QColor(BONE))
            p.drawText(QPointF((t.x()+q.x())/2+6, (t.y()+q.y())/2-4), f"{km:,.0f} km" if km >= 1 else f"{km*1000:.0f} m")
        p.setPen(QPen(QColor(BONE), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(t, 8, 8)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            p.drawLine(QPointF(t.x()+dx*4, t.y()+dy*4), QPointF(t.x()+dx*13, t.y()+dy*13))
        p.drawText(QPointF(t.x()+12, t.y()+16), "EXIF GPS")
    def pin(self, p, pin, screen, now):
        age = now-pin["born"]
        if age < 0:
            return
        drop = 1-ease_back(age/0.45)
        q = screen(pin["lat"], pin["lon"])
        q = QPointF(q.x(), q.y()-28*drop)
        top = pin["rank"] == 0
        color = QColor(SIGNAL) if top else tint(SIGNAL, 0.5)
        if top and MOTION:
            for phase in (0.0, 0.5):
                ring = ((age/2.4)+phase) % 1.0
                p.setPen(QPen(tint(SIGNAL, 0.6*(1-ring)), 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(q, 6+22*ring, 6+22*ring)
        self.marker(p, q, self.SHAPES.get(pin["engine"], "circle"), 6 if top else 3.6, color)
        if top and age > 0.3:
            p.setFont(self.label_font)
            p.setPen(QColor(BONE))
            p.drawText(QPointF(q.x()+26, q.y()-4), pin["engine"].upper())
            p.setFont(self.small_font)
            p.setPen(QColor(ASH))
            p.drawText(QPointF(q.x()+26, q.y()+10), QFontMetrics(self.small_font).elidedText(pin["place"], Qt.TextElideMode.ElideRight, 220))
    def lock_on(self, p, screen, now, w, h):
        """Crosshair lines slide in from the edges and lock onto the best estimate."""
        best = self.best()
        if not best or now < self.locked:
            return
        t = ease_out((now-self.locked)/0.8)
        q = screen(best["lat"], best["lon"])
        p.setPen(QPen(tint(SIGNAL, 0.45), 1))
        p.drawLine(QPointF(q.x()*t, q.y()), QPointF(q.x()-14, q.y()))
        p.drawLine(QPointF(w-(w-q.x())*t, q.y()), QPointF(q.x()+14, q.y()))
        p.drawLine(QPointF(q.x(), q.y()*t), QPointF(q.x(), q.y()-14))
        p.drawLine(QPointF(q.x(), h-(h-q.y())*t), QPointF(q.x(), q.y()+14))
        if t >= 1:
            size = 16+3*math.sin(now*3) if MOTION else 16
            p.setPen(QPen(QColor(SIGNAL), 1.6))
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                corner = QPointF(q.x()+sx*size, q.y()+sy*size)
                p.drawLine(corner, QPointF(corner.x()-sx*6, corner.y()))
                p.drawLine(corner, QPointF(corner.x(), corner.y()-sy*6))
            text = f"LOCK  {abs(best['lat']):.4f}°{'N' if best['lat'] >= 0 else 'S'}  {abs(best['lon']):.4f}°{'E' if best['lon'] >= 0 else 'W'}"
            p.setFont(self.small_font)
            width = QFontMetrics(self.small_font).horizontalAdvance(text)+16
            box = QRectF(min(max(8, q.x()-width/2), w-width-8), max(8, q.y()-46), width, 20)
            p.fillRect(box, tint(INK, 0.8))
            p.setPen(QPen(tint(SIGNAL, 0.8), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(box)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
    def marker(self, p, q, shape, size, color):
        p.setPen(QPen(QColor(INK), 1.2))
        p.setBrush(color)
        if shape == "diamond":
            p.drawPolygon(QPolygonF([QPointF(q.x(), q.y()-size*1.25), QPointF(q.x()+size*1.25, q.y()), QPointF(q.x(), q.y()+size*1.25), QPointF(q.x()-size*1.25, q.y())]))
        elif shape == "square":
            p.drawRect(QRectF(q.x()-size, q.y()-size, size*2, size*2))
        elif shape == "triangle":
            p.drawPolygon(QPolygonF([QPointF(q.x(), q.y()-size*1.3), QPointF(q.x()+size*1.2, q.y()+size), QPointF(q.x()-size*1.2, q.y()+size)]))
        else:
            p.drawEllipse(q, size, size)
    def legend(self, p, h):
        engines = list(dict.fromkeys(pin["engine"] for pin in self.pins))
        x, y = 14, h-30
        p.setFont(self.small_font)
        for name in engines:
            self.marker(p, QPointF(x+5, y), self.SHAPES.get(name, "circle"), 4, QColor(SIGNAL))
            p.setPen(QColor(ASH))
            p.drawText(QPointF(x+15, y+4), name.upper())
            x += 30+QFontMetrics(self.small_font).horizontalAdvance(name.upper())

class Task(QThread):
    """Runs a slow call (listing models) off the interface thread."""
    done = Signal(object)
    failed = Signal(str)
    def __init__(self, function):
        super().__init__()
        self.function = function
    def run(self):
        try:
            self.done.emit(self.function())
        except geolocate.EngineError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

class EngineRow(QFrame):
    """One photo engine: a checkbox, where it runs, its state and, for online engines, its key."""
    def __init__(self, name, meta, on_key):
        super().__init__()
        self.setObjectName("engineRow")
        self.name, self.meta = name, meta
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
        row.setSpacing(10)
        self.check = QCheckBox()
        self.check.setAccessibleName("Use "+meta["title"])
        self.check.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.check, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(meta["title"], "engineName"))
        self.state = label("", "engineMeta", True)
        text.addWidget(self.state)
        row.addLayout(text, 1)
        if meta["service"]:
            self.key = button("SET KEY", lambda: on_key(meta["service"]), "small")
            row.addWidget(self.key, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setToolTip(meta["about"])
    def show_status(self, ready, text):
        self.state.setText(f"{self.meta['where']} · {text.upper()}")
        self.check.setEnabled(ready)
        if not ready:
            self.check.setChecked(False)

class KeyDialog(QDialog):
    """Save an API key (encrypted with Windows DPAPI) and the service's options."""
    def __init__(self, parent, service, model=None, demo=None):
        super().__init__(parent)
        meta = geolocate.SERVICES[service]
        users = [e["title"] for e in geolocate.ENGINES.values() if e["service"] == service] or [meta.get("used_by", "this tool")]
        self.service, self.task, self.meta = service, None, meta
        self.setWindowTitle(meta["title"]+" API key")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(10)
        layout.addWidget(label(meta["title"].upper()+" API KEY", "section"))
        layout.addWidget(label("Used by: "+", ".join(users)+".", "body", True))
        layout.addWidget(label(meta["privacy"]+" The key is stored encrypted for this Windows account only.", "hint", True))
        layout.addSpacing(6)
        layout.addWidget(label("KEY", "micro"))
        saved = bool(geolocate.load_key(service))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Key saved. Leave empty to keep it." if saved else "Paste your API key")
        self.key.setAccessibleName(meta["title"]+" API key")
        row = QHBoxLayout()
        row.addWidget(self.key, 1)
        row.addWidget(button("GET A KEY  ↗", lambda: QDesktopServices.openUrl(QUrl(meta["key_url"])), "small"))
        layout.addLayout(row)
        self.extra = None
        if meta.get("extra"):
            layout.addWidget(label(meta["extra"]["label"], "micro"))
            self.extra = QLineEdit(geolocate.load_key(meta["extra"]["name"]))
            self.extra.setPlaceholderText(meta["extra"]["placeholder"])
            self.extra.setAccessibleName(meta["title"]+" "+meta["extra"]["label"].lower())
            layout.addWidget(self.extra)
            layout.addWidget(label(meta["extra"]["hint"], "hint", True))
        self.model = None
        if model is not None:
            layout.addWidget(label("MODEL", "micro"))
            self.model = QComboBox()
            self.model.setEditable(True)
            self.model.addItem(model)
            self.model.setAccessibleName(meta["title"]+" model")
            row = QHBoxLayout()
            row.addWidget(self.model, 1)
            row.addWidget(button("LOAD MODELS", self.load_models, "small"))
            layout.addLayout(row)
        self.demo = None
        if demo is not None:
            self.demo = QCheckBox("  Test mode: free, searches only 100,000 faces (results aren't meaningful)")
            self.demo.setChecked(demo)
            layout.addWidget(self.demo)
        self.status = label("", "hint", True)
        layout.addWidget(self.status)
        layout.addSpacing(8)
        actions = QHBoxLayout()
        if saved:
            actions.addWidget(button("REMOVE KEY", self.remove))
        actions.addStretch()
        actions.addWidget(button("CANCEL", self.reject))
        actions.addWidget(button("SAVE", self.save, "primary"))
        layout.addLayout(actions)
    def chosen_model(self):
        return (self.model.currentText().strip() if self.model else "") or geolocate.DEFAULT_MODELS.get(self.service, "")
    def chosen_demo(self):
        return bool(self.demo and self.demo.isChecked())
    def load_models(self):
        key = self.key.text().strip() or geolocate.load_key(self.service)
        if not key:
            self.status.setText("Paste a key first.")
            return
        self.status.setText("Loading models…")
        workspace = self.extra.text() if self.extra is not None else None
        lister = geolocate.gemini_models if self.service == "gemini" else (lambda k: geolocate.claude_models(k, workspace))
        self.task = Task(lambda: lister(key))
        self.task.done.connect(self.models_loaded)
        self.task.failed.connect(self.status.setText)
        self.task.start()
    def models_loaded(self, names):
        current = self.chosen_model()
        self.model.clear()
        self.model.addItems(names or [current])
        self.model.setCurrentText(current if current in names else (names[0] if names else current))
        self.status.setText(f"{len(names)} models available to this key.")
    def save(self):
        text = self.key.text().strip()
        problem = geolocate.key_problem(self.service, text) if text else ""
        if problem and QMessageBox.question(self, "Check the key", problem+"\n\nSave it anyway?") != QMessageBox.StandardButton.Yes:
            self.key.setFocus()
            return
        try:
            if text:
                geolocate.save_key(self.service, text)
            if self.extra is not None:
                geolocate.save_key(self.meta["extra"]["name"], self.extra.text())
        except OSError as error:
            self.status.setText(str(error))
            return
        self.accept()
    def remove(self):
        geolocate.save_key(self.service, "")
        if self.extra is not None:
            geolocate.save_key(self.meta["extra"]["name"], "")
        self.accept()
    def done(self, result):
        if self.task and self.task.isRunning():
            self.task.wait(30000)
        super().done(result)

class ScanWorker(QThread):
    event = Signal(dict)
    report = Signal(dict)
    failed = Signal(str)
    def __init__(self, target, kind, fast, options=None):
        super().__init__()
        self.target, self.kind, self.fast, self.options = target, kind, fast, options
        self.cancel = threading.Event()
    def run(self):
        try:
            self.report.emit(engine.scan(self.target, self.kind, self.fast, self.event.emit, self.cancel, options=self.options))
        except Exception as error:
            self.failed.emit(str(error))

SCAN_PAGE, HISTORY_PAGE, SOURCES_PAGE, GUIDE_PAGE, LOCATE_PAGE, LEAKS_PAGE = range(6)

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpyBrain")
        icon = engine.ASSETS / "assets" / "hub.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1280, 900)
        self.setMinimumSize(1040, 780)
        self.worker = None
        self.locate_worker = None
        self.locate_total = 0
        self.leak_task, self.leak_cancel, self.leak_mode, self.leak_target = None, threading.Event(), "email", ""
        self.settings = QSettings("SpyBrain", "SpyBrain")
        self.report = None
        self.partial_results = []
        self.rows = []
        self.row_born = {}
        self.history_data = []
        self.started_clock = 0
        self.close_pending = False
        self.done_count = 0
        self.total = 0
        self.flash_until = 0.0
        self.micro_font, self.link_font = font(MONO, 11, 1.5), font(MONO, 13)
        self.link_font.setUnderline(True)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        self.topbar = TopBar((("SCAN", SCAN_PAGE), ("PHOTO", LOCATE_PAGE), ("LEAKS", LEAKS_PAGE), ("HISTORY", HISTORY_PAGE), ("SOURCES", SOURCES_PAGE), ("GUIDE", GUIDE_PAGE)), self.navigate)
        outer.addWidget(self.topbar)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.build_scan()
        self.build_history()
        self.build_sources()
        self.build_guide()
        self.build_locate()
        self.build_leaks()
        self.navigate(SCAN_PAGE)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.topbar.tick)
        self.clock.start(1000)
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.flash_tick)

    def page(self, title, lede):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28,26,28,18)
        layout.setSpacing(0)
        layout.addWidget(label(title,"heading"))
        layout.addSpacing(4)
        layout.addWidget(label(lede,"lede",True))
        layout.addSpacing(22)
        self.pages.addWidget(page)
        return layout

    def rule(self):
        line = QFrame()
        line.setObjectName("rule")
        line.setFixedHeight(1)
        return line

    def build_scan(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28,22,28,12)
        layout.setSpacing(0)
        layout.addWidget(label("TARGET","micro"))
        layout.addSpacing(4)
        entry = QHBoxLayout()
        entry.setSpacing(10)
        entry.addWidget(label("›","prompt"))
        self.target = QLineEdit()
        self.target.setObjectName("target")
        self.target.setPlaceholderText("username, domain, email, phone number or photo")
        self.target.setClearButtonEnabled(True)
        self.target.returnPressed.connect(self.start_scan)
        self.target.setAccessibleName("Scan target")
        entry.addWidget(self.target,1)
        entry.addSpacing(8)
        self.browse = button("CHOOSE PHOTO",self.choose_image)
        entry.addWidget(self.browse)
        layout.addLayout(entry)
        layout.addSpacing(14)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.kind = QComboBox()
        self.kind.addItem("Auto-detect type",None)
        for value, title in engine.KINDS.items():
            if value != "location":
                self.kind.addItem(title,value)
        self.kind.setAccessibleName("Target type")
        controls.addWidget(self.kind)
        self.mode = QComboBox()
        self.mode.addItem("Quick scan",True)
        self.mode.addItem("Deep scan",False)
        self.mode.setAccessibleName("Scan depth")
        self.mode.setToolTip("Quick: selected sites plus Maigret's top 100.\nDeep: every Sherlock site plus Maigret's top 500. Can take several minutes.")
        controls.addWidget(self.mode)
        controls.addSpacing(10)
        self.hint = label("For lawful, authorized investigations only. Protect the personal data you collect.","hint",True)
        controls.addWidget(self.hint,1)
        self.start = button("RUN SCAN",self.start_scan,"primary")
        self.start.setMinimumWidth(190)
        controls.addWidget(self.start)
        layout.addLayout(controls)
        layout.addSpacing(18)
        self.frame = QFrame()
        self.frame.setObjectName("chartFrame")
        self.frame.setFixedHeight(256)
        fl = QGridLayout(self.frame)
        fl.setContentsMargins(0,0,0,0)
        self.chart = LinkChart()
        self.chart.top = 40
        fl.addWidget(self.chart,0,0)
        overlay = QWidget()
        overlay.setObjectName("overlay")
        head = QHBoxLayout(overlay)
        head.setContentsMargins(18,10,14,0)
        head.setSpacing(10)
        self.pulse = Pulse()
        self.state = label("Ready","status")
        self.elapsed = label("","elapsed")
        self.stop = button("STOP",self.cancel_scan,"stop")
        self.stop.setEnabled(False)
        head.addWidget(self.pulse)
        head.addWidget(self.state,1)
        head.addWidget(self.elapsed)
        head.addSpacing(6)
        head.addWidget(self.stop)
        fl.addWidget(overlay,0,0,Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.frame)
        layout.addSpacing(16)
        bar = QHBoxLayout()
        bar.setSpacing(14)
        self.count = EvidenceTag()
        bar.addWidget(self.count)
        self.tab_buttons = []
        for index, title in enumerate(("FINDINGS", "RUN LOG")):
            tab = button(title, lambda checked=False, i=index: self.show_tab(i), "tab")
            tab.setCheckable(True)
            tab.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self.tab_buttons.append(tab)
            bar.addWidget(tab)
            bar.addSpacing(8)
        bar.addStretch()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by type, item, value or source")
        self.filter.setAccessibleName("Filter findings")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(300)
        self.filter.textChanged.connect(self.apply_filter)
        bar.addWidget(self.filter)
        self.export = button("EXPORT",self.export_report)
        self.open_report_button = button("OPEN REPORT ↗",self.open_report)
        self.export.setEnabled(False)
        self.open_report_button.setEnabled(False)
        bar.addWidget(self.export)
        bar.addWidget(self.open_report_button)
        layout.addLayout(bar)
        layout.addSpacing(8)
        self.table = QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["TYPE", "ITEM", "VALUE / LINK", "SOURCE"])
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0,130)
        self.table.setColumnWidth(1,210)
        self.table.setColumnWidth(3,180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegate(FindingsDelegate(self.table))
        self.table.cellDoubleClicked.connect(self.open_row)
        empty_panel = QWidget()
        el = QVBoxLayout(empty_panel)
        el.addStretch()
        mark = QLabel()
        mark.setPixmap(owl_pixmap(76, dim=True))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(mark)
        el.addSpacing(10)
        self.empty = label(EMPTY_IDLE,"empty",True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.empty)
        el.addStretch()
        self.results = QStackedWidget()
        self.results.addWidget(self.table)
        self.results.addWidget(empty_panel)
        self.results.setCurrentIndex(1)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(6000)
        self.logs.setPlaceholderText("Each source writes its progress and diagnostics here.")
        self.tabs = QStackedWidget()
        self.tabs.addWidget(self.results)
        self.tabs.addWidget(self.logs)
        layout.addWidget(self.tabs,1)
        layout.addSpacing(8)
        footer = QHBoxLayout()
        footer.addWidget(label("Double-click a link to open it  ·  Ctrl+C copies the selected cell","footer"),1)
        footer.addWidget(label("AUTHORIZED INVESTIGATIONS ONLY · MATCHES ARE LEADS, NOT PROOF","caveat"))
        layout.addLayout(footer)
        self.pages.addWidget(page)
        self.show_tab(0)

    def build_history(self):
        layout = self.page("HISTORY", "Scans saved on this computer. Double-click one to view its findings.")
        layout.addWidget(LedgerHeader(HISTORY_COLUMNS))
        self.history_list = QListWidget()
        self.history_list.setItemDelegate(LedgerDelegate(HISTORY_COLUMNS, self.history_list))
        self.history_list.setMouseTracking(True)
        self.history_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.history_list.itemDoubleClicked.connect(lambda _: self.load_selected_history())
        layout.addWidget(self.history_list,1)
        layout.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(button("VIEW FINDINGS",self.load_selected_history,"primary"))
        row.addWidget(button("REFRESH",self.refresh_history))
        row.addStretch()
        row.addWidget(button("OPEN REPORTS FOLDER ↗",self.open_folder))
        layout.addLayout(row)
        layout.addSpacing(10)
        layout.addWidget(label("Reports from version 1 aren't listed. They stay in the original reports folder.","hint",True))

    def build_sources(self):
        layout = self.page("SOURCES", "Network sources can rate-limit or go offline. If one fails, the rest of the scan continues.")
        layout.addWidget(LedgerHeader(SOURCE_COLUMNS))
        self.source_list = QListWidget()
        self.source_list.setItemDelegate(LedgerDelegate(SOURCE_COLUMNS, self.source_list))
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.source_list.setMouseTracking(True)
        layout.addWidget(self.source_list,1)
        layout.addSpacing(14)
        row = QHBoxLayout()
        row.addWidget(button("CHECK AGAIN",self.refresh_sources))
        row.addStretch()
        layout.addLayout(row)
        layout.addSpacing(10)
        layout.addWidget(label("Quick scan limits the number of sites. Deep scan is more thorough and can take several minutes.","hint",True))

    def build_guide(self):
        layout = self.page("GUIDE", "What each tool checks, and what it can't tell you.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(0)
        rows = guide_rows()
        for index, (title, tools, text) in enumerate(rows):
            row = index*2
            grid.addWidget(self.rule(), row, 0, 1, 3)
            widgets = (label(title,"section"), label(text,"body",True), label(tools,"tools",True))
            for column, widget in enumerate(widgets):
                widget.setContentsMargins(0,14,0,14)
                grid.addWidget(widget, row+1, column, Qt.AlignmentFlag.AlignTop)
            widgets[2].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.rule(), len(rows)*2, 0, 1, 3)
        grid.setColumnMinimumWidth(0, 190)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(2, 250)
        layout.addLayout(grid)
        layout.addSpacing(16)
        layout.addWidget(label("SpyBrain is for journalists, investigators and threat-intelligence teams. Use it only for lawful, authorized work and protect the personal data you collect.","hint",True))
        layout.addStretch()

    def navigate(self,index):
        changed = index != self.pages.currentIndex()
        self.pages.setCurrentIndex(index)
        self.topbar.select(index)
        if changed and MOTION:
            self.fade_in(self.pages.widget(index))
        if index==HISTORY_PAGE:
            self.refresh_history()
        elif index==SOURCES_PAGE:
            self.refresh_sources()
        elif index==LOCATE_PAGE:
            self.refresh_engines()
        elif index==LEAKS_PAGE:
            self.refresh_leaks()

    def fade_in(self,page):
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(220)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def show_tab(self,index):
        self.tabs.setCurrentIndex(index)
        for i, tab in enumerate(self.tab_buttons):
            tab.setChecked(i==index)
        self.filter.setVisible(index==0)

    def choose_image(self):
        path,_ = QFileDialog.getOpenFileName(self,"Choose photo","","Photos (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp);;All files (*)")
        if path:
            self.target.setText(path)
            self.kind.setCurrentIndex(self.kind.findData("image"))

    def set_state(self,text,tone="idle"):
        self.state.setText(text)
        self.pulse.set_tone(tone)

    def start_scan(self):
        if self.worker or self.locate_worker:
            return
        try:
            target,kind = engine.validate(self.target.text(),self.kind.currentData())
            engine.jobs_for(target,kind)
        except (ValueError,OSError) as error:
            self.hint.setText(str(error))
            set_prop(self.hint,"tone","warn")
            self.target.setFocus()
            return
        set_prop(self.hint,"tone","")
        self.hint.setText("Email scans check the address in known breaches and search the name before @. A match doesn't link the account to this address." if kind=="email" else "Findings can include false matches. Verify each one by hand.")
        self.target.setText(target)
        self.report = None
        self.partial_results = []
        self.rows = []
        self.row_born = {}
        self.logs.clear()
        self.filter.clear()
        self.populate([])
        self.show_tab(0)
        self.chart.begin(target,kind)
        self.set_busy(True)
        self.started_clock = time.monotonic()
        self.done_count = 0
        self.worker = ScanWorker(target,kind,self.mode.currentData())
        self.worker.event.connect(self.on_event)
        self.worker.report.connect(self.on_report)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.worker_finished)
        self.empty.setText(EMPTY_LIVE)
        self.worker.start()

    def set_busy(self,busy):
        for control in (self.start,self.target,self.kind,self.mode,self.browse):
            control.setEnabled(not busy)
        self.locate_button.setEnabled(not busy)
        self.update_nav(busy)
        self.stop.setEnabled(busy)
        self.export.setEnabled(not busy and bool(self.report))
        self.open_report_button.setEnabled(not busy and bool(self.report))
        self.start.setText("SCANNING" if busy else "RUN SCAN")
        if busy:
            self.set_state("Starting sources…","run")

    def update_nav(self, busy=False):
        busy = busy or bool(self.worker or self.locate_worker)
        self.topbar.button_for(HISTORY_PAGE).setEnabled(not busy)
        self.topbar.set_live(busy)

    def cancel_scan(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self.set_state("Stopping. Finished results will be saved…","warn")

    def on_event(self,event):
        state = event["state"]
        if state=="plan":
            self.total = event["total"]
            self.chart.plan(event["tools"])
            self.logs.appendPlainText("Sources: "+", ".join(event["tools"]))
        elif state=="running":
            self.chart.report(event["tool"],"running")
            self.logs.appendPlainText("▶ "+event["tool"]+" · started")
            self.set_state("Checking public sources…","run")
        elif state=="done":
            data = event["result"]
            name = event["tool"]
            self.done_count += 1
            self.chart.report(name,data["status"],len(engine.flatten([data])))
            self.partial_results.append(data)
            self.populate(engine.flatten(self.partial_results))
            self.logs.appendPlainText("\n■ "+name+" · "+STATES.get(data["status"],data["status"])+"\n"+data.get("log", ""))
            self.set_state(f"Sources finished: {self.done_count} / {self.total}","run")

    def tick(self):
        if self.locate_worker and self.geoclip_pending:
            if not geolocate.geoclip_downloaded():
                got = geolocate.geoclip_download_progress()
                if got:
                    self.set_locate_state(f"Downloading the GeoCLIP model · {got/1e6:.0f} of {geolocate.CLIP_BYTES/1e6:.0f} MB · first use only", "run")
            elif self.geoclip_prepares and not geolocate.places_cache().exists():
                self.set_locate_state("Preparing GeoCLIP · first use only, this can take a few minutes", "run")
        if self.worker:
            seconds = int(time.monotonic()-self.started_clock)
            self.elapsed.setText(f"{seconds//60:02d}:{seconds%60:02d}")

    def on_report(self,report):
        self.report = report
        self.populate(engine.flatten(report["results"]))
        status = report["status"]
        self.chart.finish(status)
        count = len(self.rows)
        self.set_state(STATES.get(status,status)+f" · {count} finding"+("" if count==1 else "s"),TONES.get(status,"idle"))
        self.elapsed.setText(f"{report['duration']:.1f} s")
        self.logs.appendPlainText("\nReport saved: "+report["files"]["html"])
        if status in ("failed","partial"):
            self.hint.setText("Some sources failed. Open Run log for details.")
            set_prop(self.hint,"tone","warn")
        if not self.rows:
            self.empty.setText(EMPTY_DONE)

    def on_failure(self,message):
        self.chart.finish("failed")
        self.set_state("Scan couldn't finish","err")
        self.logs.appendPlainText("ERROR: "+message)
        self.hint.setText(message)
        set_prop(self.hint,"tone","warn")

    def worker_finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.set_busy(False)
        if self.close_pending:
            self.close()

    def populate(self,rows):
        self.rows = rows
        now, fresh = time.monotonic(), 0
        new = sum((r["category"],r["label"],r["value"]) not in self.row_born for r in rows)
        stagger = min(0.035, 0.7/max(new, 1))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for index,row in enumerate(rows):
            key = (row["category"],row["label"],row["value"])
            if key not in self.row_born:
                self.row_born[key] = now+fresh*stagger if self.worker else 0.0
                fresh += bool(self.worker)
            for col,name in enumerate(("category","label","value","source")):
                item = QTableWidgetItem(row[name].upper() if col==0 else row[name])
                item.setToolTip(row[name])
                if col==0:
                    item.setData(BORN,self.row_born[key])
                    item.setFont(self.micro_font)
                    item.setForeground(QColor(ASH))
                elif col==2:
                    item.setData(Qt.ItemDataRole.UserRole,row.get("url", ""))
                    if engine.safe_url(row.get("url","")):
                        item.setForeground(QColor(SIGNAL))
                        item.setFont(self.link_font)
                elif col==3:
                    item.setForeground(QColor(ASH))
                self.table.setItem(index,col,item)
        self.table.setSortingEnabled(True)
        self.count.set_value(len(rows))
        self.results.setCurrentIndex(0 if rows else 1)
        if not rows:
            self.empty.setText(EMPTY_LIVE if self.worker else EMPTY_IDLE)
        if fresh and MOTION:
            self.flash_until = now+fresh*stagger+FLASH
            self.flash_timer.start(33)
        self.apply_filter()

    def flash_tick(self):
        for table in (self.table, self.locate_table, self.web_table, self.leak_table):
            table.viewport().update()
        if time.monotonic() > self.flash_until:
            self.flash_timer.stop()

    def apply_filter(self):
        query = self.filter.text().casefold()
        for row in range(self.table.rowCount()):
            text = " ".join(self.table.item(row,c).text() for c in range(4))
            self.table.setRowHidden(row,bool(query and query not in text.casefold()))

    def open_row(self,row,col):
        item = self.table.item(row,2)
        url = item.data(Qt.ItemDataRole.UserRole) if item else ""
        if engine.safe_url(url):
            QDesktopServices.openUrl(QUrl(url))

    def open_report(self):
        if self.report:
            path = Path(self.report["files"]["html"])
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            else:
                QMessageBox.warning(self,"Report not found","The report file was moved or deleted.")

    def export_report(self):
        if not self.report:
            return
        source = Path(self.report["files"]["html"])
        path,selected = QFileDialog.getSaveFileName(self,"Export report",source.name,"HTML report (*.html);;JSON data (*.json);;CSV table (*.csv)")
        if not path:
            return
        ext = "json" if "JSON" in selected else "csv" if "CSV" in selected else "html"
        destination = Path(path)
        if destination.suffix.lower() != "."+ext:
            destination = Path(str(destination)+"."+ext)
        try:
            original = Path(self.report["files"][ext])
            if original.resolve()!=destination.resolve():
                shutil.copy2(original,destination)
            set_prop(self.hint,"tone","")
            self.hint.setText("Exported to "+str(destination))
        except OSError as error:
            QMessageBox.warning(self,"Export failed",str(error))

    def refresh_history(self):
        self.history_data = engine.history()
        self.history_list.clear()
        for report in self.history_data:
            status = report["status"]
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, {"cells": [
                (report["started"].replace("T"," ")[:16], "mono"),
                (engine.KINDS[report["kind"]].upper(), "micro"),
                (Path(report["target"]).name if report["kind"] in ("image", "location") else report["target"], "display"),
                (str(len(engine.flatten(report["results"]))), "count"),
                (STATES.get(status,status), "status:"+TONES.get(status,"idle"))]})
            item.setToolTip(report["target"])
            self.history_list.addItem(item)
        if not self.history_data:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, {"empty": "No saved scans yet. Run your first scan on the Scan page."})
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.addItem(item)

    def load_selected_history(self):
        index = self.history_list.currentRow()
        if self.worker or self.locate_worker or not 0<=index<len(self.history_data):
            return
        if self.history_data[index]["kind"] == "location":
            self.show_location(self.history_data[index])
            self.navigate(LOCATE_PAGE)
            return
        self.report = self.history_data[index]
        self.target.setText(self.report["target"])
        self.kind.setCurrentIndex(self.kind.findData(self.report["kind"]))
        self.mode.setCurrentIndex(0 if self.report.get("mode")=="fast" else 1)
        self.filter.clear()
        self.logs.clear()
        self.row_born = {}
        for result in self.report["results"]:
            self.logs.appendPlainText("■ "+result["tool"]+" · "+STATES.get(result["status"],result["status"])+"\n"+result.get("log",""))
        self.chart.begin(self.report["target"],self.report["kind"])
        self.chart.plan([r["tool"] for r in self.report["results"]],quick=True)
        for result in self.report["results"]:
            self.chart.report(result["tool"],result["status"],len(engine.flatten([result])))
        self.on_report(self.report)
        set_prop(self.hint,"tone","")
        self.hint.setText("Showing a saved scan. Run scan starts a new check.")
        self.set_busy(False)
        self.show_tab(0)
        self.navigate(SCAN_PAGE)

    def build_locate(self):
        groups = photo_groups()
        phrases = [text for group, text in (("LOCATION", "where a photo was taken"), ("WEB", "where it appears online"), ("FACES", "who else shows the same face")) if group in groups]
        lede = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1])+" and "+phrases[-1]
        layout = self.page("PHOTO", lede[0].upper()+lede[1:]+". For lawful, authorized investigations only.")
        body = QHBoxLayout()
        body.setSpacing(24)
        side = QWidget()
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 10, 0)
        column.setSpacing(0)
        column.addWidget(label("PHOTO", "micro"))
        column.addSpacing(6)
        self.photo_view = QLabel("NO PHOTO")
        self.photo_view.setObjectName("photo")
        self.photo_view.setFixedSize(290, 180)
        self.photo_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.photo_view)
        column.addSpacing(8)
        self.photo_name = label("", "photoName")
        column.addWidget(self.photo_name)
        self.photo_gps = label("Choose a photo. If it already stores GPS coordinates, they're marked on the map for comparison.", "hint", True)
        column.addWidget(self.photo_gps)
        column.addSpacing(10)
        self.locate_browse = button("CHOOSE PHOTO", self.choose_locate_photo)
        column.addWidget(self.locate_browse)
        self.engine_rows = {}
        for group, title in (("LOCATION", "WHERE WAS IT TAKEN"), ("WEB", "WHERE IS IT ONLINE"), ("FACES", "WHO ELSE SHOWS THIS FACE")):
            members = [(name, meta) for name, meta in geolocate.ENGINES.items() if meta["group"] == group and name in geolocate.ENABLED_ENGINES]
            if not members:
                continue
            column.addSpacing(18)
            column.addWidget(label(title, "micro"))
            for name, meta in members:
                self.engine_rows[name] = EngineRow(name, meta, self.edit_key)
                column.addWidget(self.engine_rows[name])
        self.purpose = QLineEdit(side)
        self.purpose.setPlaceholderText("Purpose of the face search (required)")
        self.purpose.setAccessibleName("Purpose of the face search")
        if "faces" in geolocate.ENABLED_ENGINES:
            column.addSpacing(8)
            column.addWidget(self.purpose)
            column.addSpacing(6)
            column.addWidget(label("Face search never runs on children or teenagers: an age check on this computer blocks it. The purpose is saved with the results.", "hint", True))
        else:
            self.purpose.hide()
        column.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The engine list scrolls; the action and its status stay in view below it.
        panel = QWidget()
        panel.setFixedWidth(330)
        left = QVBoxLayout(panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(scroll, 1)
        action = QVBoxLayout()
        action.setContentsMargins(0, 12, 10, 0)
        action.setSpacing(10)
        # Keep the button flush with the list whether or not its scroll bar shows.
        scroll.verticalScrollBar().rangeChanged.connect(lambda low, high: action.setContentsMargins(0, 12, 18 if high > 0 else 10, 0))
        self.locate_button = button("ANALYZE PHOTO", self.start_locate, "primary")
        action.addWidget(self.locate_button)
        status = QHBoxLayout()
        status.setSpacing(8)
        self.locate_pulse = Pulse()
        self.locate_state = label("Ready", "status", True)
        status.addWidget(self.locate_pulse, 0, Qt.AlignmentFlag.AlignTop)
        status.addWidget(self.locate_state, 1)
        action.addLayout(status)
        left.addLayout(action)
        body.addWidget(panel)
        right = QVBoxLayout()
        right.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(22)
        self.result_tabs = []
        for index, (title, group) in enumerate((("MAP", "LOCATION"), ("WEB MATCHES", "WEB"), ("FACES", "FACES"))):
            tab = button(title, lambda checked=False, i=index: self.show_result_tab(i), "tab")
            tab.setCheckable(True)
            tab.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            tab.setVisible(group in groups)
            self.result_tabs.append(tab)
            bar.addWidget(tab)
        bar.addStretch()
        right.addLayout(bar)
        self.result_stack = QStackedWidget()
        # Map tab.
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.setSpacing(8)
        self.world = WorldMap()
        pl.addWidget(self.world, 5)
        self.locate_table = self.results_table(["ENGINE", "#", "PLACE", "COORDINATES", "CONFIDENCE"], ((0, 110), (1, 40), (3, 210), (4, 110)), 2)
        self.locate_table.cellDoubleClicked.connect(lambda row, col: self.open_cell(self.locate_table, row, 3))
        pl.addWidget(self.locate_table, 3)
        self.clues = label("", "hint", True)
        pl.addWidget(self.clues)
        self.engine_problems = label("", "hint", True)
        set_prop(self.engine_problems, "tone", "warn")
        pl.addWidget(self.engine_problems)
        pl.addWidget(label("Estimates, not proof: usually the right region, rarely the exact spot. Double-click coordinates to open the map.", "footer"))
        self.result_stack.addWidget(page)
        # Web matches tab.
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.setSpacing(8)
        self.web_summary = label("Turn on Web matches and analyze a photo to see where it appears online.", "hint", True)
        pl.addWidget(self.web_summary)
        self.web_table = self.results_table(["MATCH", "PAGE OR IMAGE", "ADDRESS"], ((0, 170), (2, 360)), 1)
        self.web_table.cellDoubleClicked.connect(lambda row, col: self.open_cell(self.web_table, row, 2))
        pl.addWidget(self.web_table, 1)
        pl.addWidget(label("Double-click a row to open it. Full matches are the same image; partial matches are crops or edits.", "footer"))
        self.result_stack.addWidget(page)
        # Faces tab.
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.setSpacing(8)
        self.face_summary = label("Turn on Face search, state the purpose and analyze a photo of one adult face.", "hint", True)
        pl.addWidget(self.face_summary)
        self.face_list = QListWidget()
        self.face_list.setObjectName("faces")
        self.face_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.face_list.setIconSize(QSize(112, 112))
        self.face_list.setGridSize(QSize(150, 168))
        self.face_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.face_list.setMovement(QListWidget.Movement.Static)
        self.face_list.setWordWrap(True)
        self.face_list.itemDoubleClicked.connect(lambda item: self.open_url(item.data(Qt.ItemDataRole.UserRole)))
        pl.addWidget(self.face_list, 1)
        pl.addWidget(label("A matching face is a lead, not an identification. Double-click a face to open the page.", "footer"))
        self.result_stack.addWidget(page)
        right.addWidget(self.result_stack, 1)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)
        self.locate_photo, self.locate_report, self.clue_lines, self.geoclip_pending, self.geoclip_prepares, self.locate_done = "", None, [], False, False, 0
        self.result_counts = [0, 0, 0]
        self.show_result_tab(0)
        self.refresh_engines(initial=True)

    def results_table(self, headers, widths, stretch):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(32)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        for column, width in widths:
            table.setColumnWidth(column, width)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setItemDelegate(FindingsDelegate(table))
        return table

    def show_result_tab(self, index):
        self.result_stack.setCurrentIndex(index)
        for i, tab in enumerate(self.result_tabs):
            tab.setChecked(i == index)

    def update_result_counts(self):
        groups = photo_groups()
        for tab, title, count, group in zip(self.result_tabs, ("MAP", "WEB MATCHES", "FACES"), self.result_counts, ("LOCATION", "WEB", "FACES")):
            tab.setText(f"{title}  {count}" if count else title)
            # A saved analysis from a version with more engines still shows its web or face results.
            tab.setVisible(group in groups or count > 0)

    def refresh_engines(self, initial=False):
        status = geolocate.engine_status()
        demo = self.settings.value("facecheck/demo", True, type=bool)
        for name, row in self.engine_rows.items():
            ready, text = status[name]
            if name == "faces" and ready and demo:
                text += " · test mode"
            was = row.check.isEnabled()
            row.show_status(ready, text)
            # Face search is never ticked automatically.
            if ready and name != "faces" and (initial or not was):
                row.check.setChecked(True)

    def model_for(self, service):
        return str(self.settings.value(f"models/{service}", geolocate.DEFAULT_MODELS[service]))

    def edit_key(self, service):
        model = self.model_for(service) if service in geolocate.DEFAULT_MODELS else None
        demo = self.settings.value("facecheck/demo", True, type=bool) if service == "facecheck" else None
        dialog = KeyDialog(self, service, model, demo)
        if dialog.exec():
            if model is not None:
                self.settings.setValue(f"models/{service}", dialog.chosen_model())
            if demo is not None:
                self.settings.setValue("facecheck/demo", dialog.chosen_demo())
        self.refresh_engines()
        self.refresh_leaks()

    def set_locate_state(self, text, tone="idle"):
        self.locate_state.setText(text)
        self.locate_pulse.set_tone(tone)

    def choose_locate_photo(self):
        path,_ = QFileDialog.getOpenFileName(self,"Choose photo","","Photos (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp);;All files (*)")
        if path:
            self.set_locate_photo(path)

    def clear_photo_results(self):
        self.locate_table.setRowCount(0)
        self.web_table.setRowCount(0)
        self.face_list.clear()
        self.clue_lines = []
        self.clues.setText("")
        self.problem_lines = []
        self.engine_problems.setText("")
        self.web_summary.setText("Turn on Web matches and analyze a photo to see where it appears online.")
        self.face_summary.setText("Turn on Face search, state the purpose and analyze a photo of one adult face.")
        set_prop(self.face_summary, "tone", "")
        self.result_counts = [0, 0, 0]
        self.update_result_counts()

    def set_locate_photo(self, path):
        self.locate_photo = path
        picture = QPixmap(path)
        if picture.isNull():
            self.photo_view.setPixmap(QPixmap())
            self.photo_view.setText("NO PREVIEW")
        else:
            self.photo_view.setPixmap(picture.scaled(QSize(290, 180), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.photo_name.setText(QFontMetrics(self.photo_name.font()).elidedText(Path(path).name, Qt.TextElideMode.ElideMiddle, 290))
        gps = engine.photo_gps(path)
        self.world.clear()
        self.world.truth = gps
        self.world.fit()
        if gps:
            self.photo_gps.setText(f"This photo already stores GPS: {gps['lat']:.5f}, {gps['lon']:.5f}. It's marked on the map so you can compare the estimates.")
        else:
            self.photo_gps.setText("No GPS in the photo's metadata. The engines estimate from what the photo shows.")
        self.clear_photo_results()
        self.set_locate_state("Ready")

    def start_locate(self):
        if self.worker or self.locate_worker:
            return
        if not self.locate_photo:
            self.set_locate_state("Choose a photo first.", "warn")
            return
        engines = [name for name, row in self.engine_rows.items() if row.check.isChecked()]
        if not engines:
            self.set_locate_state("Pick at least one engine. GeoCLIP needs no key.", "warn")
            return
        purpose = self.purpose.text().strip()
        if "faces" in engines:
            if len(purpose) < 8:
                self.set_locate_state("Face search needs a purpose, for example: verifying the identity of a source for case 12.", "warn")
                self.purpose.setFocus()
                return
            if not self.settings.value("consent/faces", False, type=bool):
                answer = QMessageBox.question(self, "Face search",
                    "Face search sends this photo to FaceCheck.ID and looks for the same face on public pages. Faces are biometric data.\n\n"
                    "Use it only for lawful, authorized investigations. It's blocked for children and teenagers, and every search is saved with its purpose. Continue?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
                self.settings.setValue("consent/faces", True)
        online = sorted({geolocate.SERVICES[geolocate.ENGINES[name]["service"]]["title"] for name in engines if geolocate.ENGINES[name]["online"]})
        if online and not self.settings.value("consent/online", False, type=bool):
            answer = QMessageBox.question(self, "Send the photo online?",
                f"{', '.join(online)} will receive this photo, without its EXIF metadata.\n\nUse only photos you're authorized to analyze. Continue?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.settings.setValue("consent/online", True)
        options = {"engines": engines, "models": {service: self.model_for(service) for service in ("gemini", "claude")},
                   "purpose": purpose if "faces" in engines else "", "demo": self.settings.value("facecheck/demo", True, type=bool)}
        self.clear_photo_results()
        self.world.pins = []
        self.world.set_scanning(True)
        self.geoclip_pending, self.geoclip_prepares, self.locate_done = "geoclip" in engines or "faces" in engines, "geoclip" in engines, 0
        self.locate_worker = ScanWorker(self.locate_photo, "location", True, options)
        self.locate_worker.event.connect(self.on_locate_event)
        self.locate_worker.report.connect(self.on_locate_report)
        self.locate_worker.failed.connect(self.on_locate_failure)
        self.locate_worker.finished.connect(self.locate_finished)
        self.set_locate_busy(True)
        self.locate_worker.start()

    def set_locate_busy(self, busy):
        for control in [self.locate_browse, self.purpose] + list(self.engine_rows.values()):
            control.setEnabled(not busy)
        self.locate_button.setEnabled(not busy)
        self.locate_button.setText("ANALYZING" if busy else "ANALYZE PHOTO")
        self.start.setEnabled(not busy)
        self.update_nav(busy)
        if busy:
            self.set_locate_state("Starting engines…", "run")

    def on_locate_event(self, event):
        state = event["state"]
        if state == "plan":
            self.locate_total = event["total"]
            self.set_locate_state("Analyzing with "+", ".join(event["tools"])+"…", "run")
        elif state == "done":
            data, tool = event["result"], event["tool"]
            self.locate_done += 1
            if tool in ("GeoCLIP", "Face search"):
                self.geoclip_pending = False
            self.show_engine_result(data)
            self.set_locate_state(f"Engines finished: {self.locate_done} / {self.locate_total}", "run")

    def engine_group(self, tool):
        return next((meta["group"] for meta in geolocate.ENGINES.values() if meta["title"] == tool), "LOCATION")

    def problem(self, data):
        message = (data.get("log") or STATES.get(data["status"], data["status"])).strip().splitlines()[-1]
        word = "Needs key" if data["status"] == "missing" and data["tool"] != "GeoCLIP" else STATES.get(data["status"], data["status"])
        return word, message

    def add_row(self, table, cells, link_column=None, url="", rank=0):
        index = table.rowCount()
        table.insertRow(index)
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            if column == 0:
                item.setForeground(QColor(ASH))
                item.setFont(self.micro_font)
                if MOTION:
                    item.setData(BORN, time.monotonic()+rank*0.05)
            if column == link_column and url:
                item.setData(Qt.ItemDataRole.UserRole, url)
                item.setForeground(QColor(SIGNAL))
                item.setFont(self.link_font)
            table.setItem(index, column, item)

    def show_engine_result(self, data):
        tool, group = data["tool"], self.engine_group(data["tool"])
        if group == "LOCATION":
            spots = data.get("locations") or []
            if spots:
                self.world.add(tool, spots)
                for rank, spot in enumerate(spots):
                    self.add_row(self.locate_table, [tool, str(rank+1), spot.get("place", ""), f"{spot['lat']:.5f}, {spot['lon']:.5f}", f"{spot.get('confidence', 0):.1%}"],
                                 3, spot.get("map", ""), rank)
                self.result_counts[0] += len(spots)
            else:
                word, message = self.problem(data)
                index = self.locate_table.rowCount()
                self.add_row(self.locate_table, [tool, "", word+" · "+message, "", ""])
                self.locate_table.item(index, 2).setForeground(QColor(ALERT if data["status"] in ("error", "failed", "blocked") else WARN))
                # The table cell cuts long text; the full explanation goes below it.
                self.problem_lines.append(f"{tool.upper()}   {word} · {message}")
                self.engine_problems.setText("\n".join(self.problem_lines))
            if data.get("clues"):
                self.clue_lines.append(tool.upper()+"   "+"  ·  ".join(data["clues"]))
                self.clues.setText("\n".join(self.clue_lines))
        elif group == "WEB":
            matches = data.get("matches") or []
            for rank, match in enumerate(matches):
                self.add_row(self.web_table, [match.get("kind", ""), match.get("title", ""), match["url"]], 2, match["url"], min(rank, 20))
            self.result_counts[1] += len(matches)
            if matches or data["status"] == "ok":
                parts = [f"{len(matches)} matches"]
                if data.get("labels"):
                    parts.append("best guess: "+", ".join(data["labels"]))
                if data.get("entities"):
                    parts.append("entities: "+", ".join(data["entities"][:8]))
                self.web_summary.setText(" · ".join(parts))
            else:
                word, message = self.problem(data)
                self.web_summary.setText(word+" · "+message)
        else:
            faces = data.get("faces") or []
            for face in faces:
                picture = QPixmap()
                if face.get("thumb"):
                    picture.loadFromData(base64.b64decode(face["thumb"]))
                item = QListWidgetItem(QIcon(picture) if not picture.isNull() else QIcon(), f"{face.get('score', 0)} %\n{face.get('site', '')}")
                item.setData(Qt.ItemDataRole.UserRole, face["url"])
                item.setToolTip(face["url"])
                self.face_list.addItem(item)
            self.result_counts[2] += len(faces)
            if data["status"] == "ok":
                note = " Test mode: results aren't meaningful." if data.get("demo") else ""
                self.face_summary.setText(f"{len(faces)} pages with a similar face. Purpose: {data.get('purpose', '')}.{note}")
                set_prop(self.face_summary, "tone", "")
            else:
                word, message = self.problem(data)
                self.face_summary.setText(word+" · "+message)
                set_prop(self.face_summary, "tone", "warn")
        self.update_result_counts()
        if MOTION:
            self.flash_until = time.monotonic()+FLASH+0.6
            self.flash_timer.start(33)

    def on_locate_report(self, report):
        self.locate_report = report
        self.world.set_scanning(False)
        self.world.fit()
        total = sum(self.result_counts)
        self.set_locate_state(STATES.get(report["status"], report["status"])+f" · {total} result"+("" if total == 1 else "s")+f" · {report['duration']:.0f} s",
                              TONES.get(report["status"], "idle"))
        if not self.result_counts[0]:
            self.show_result_tab(1 if self.result_counts[1] else 2 if self.result_counts[2] else 0)

    def on_locate_failure(self, message):
        self.world.set_scanning(False)
        self.set_locate_state("Couldn't analyze the photo: "+message, "err")

    def locate_finished(self):
        worker = self.locate_worker
        self.locate_worker = None
        worker.deleteLater()
        self.set_locate_busy(False)
        self.refresh_engines()
        if self.close_pending:
            self.close()

    def open_url(self, url):
        if engine.safe_url(url or ""):
            QDesktopServices.openUrl(QUrl(url))

    def open_cell(self, table, row, column):
        item = table.item(row, column)
        self.open_url(item.data(Qt.ItemDataRole.UserRole) if item else "")

    def show_location(self, report):
        if Path(report["target"]).is_file():
            self.set_locate_photo(report["target"])
        else:
            self.locate_photo = ""
            self.photo_view.setPixmap(QPixmap())
            self.photo_view.setText("PHOTO MOVED OR DELETED")
            self.photo_name.setText(Path(report["target"]).name)
            self.world.clear()
            self.clear_photo_results()
        self.world.pins = []
        self.purpose.setText(report.get("purpose", ""))
        for data in report["results"]:
            self.show_engine_result(data)
        self.world.fit()
        self.locate_report = report
        self.set_locate_state("Saved analysis from "+report["started"].replace("T", " ")[:16])

    # ---- Leaks page.
    LEAK_HINT = "Searches XposedOrNot, and Have I Been Pwned too if you add a key. Only the address is sent."

    def build_leaks(self):
        layout = self.page("LEAKS", "Check whether an email address or a password appears in known data breaches. It shows where and what was exposed, never the leaked passwords.")
        bar = QHBoxLayout()
        bar.setSpacing(22)
        self.leak_tabs = []
        for index, title in enumerate(("EMAIL", "PASSWORD")):
            tab = button(title, lambda checked=False, i=index: self.show_leak_tab(i), "tab")
            tab.setCheckable(True)
            tab.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self.leak_tabs.append(tab)
            bar.addWidget(tab)
        bar.addStretch()
        layout.addLayout(bar)
        layout.addSpacing(12)
        self.leak_stack = QStackedWidget()
        self.leak_stack.addWidget(self.build_leak_email())
        self.leak_stack.addWidget(self.build_leak_password())
        layout.addWidget(self.leak_stack, 1)
        layout.addSpacing(8)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.leak_pulse = Pulse()
        self.leak_state = label("Ready", "status", True)
        footer.addWidget(self.leak_pulse, 0, Qt.AlignmentFlag.AlignVCenter)
        footer.addWidget(self.leak_state, 1)
        footer.addWidget(label("LEAKED DATA IS NEVER SHOWN OR SAVED · NO RESULT IS NOT PROOF OF SAFETY", "caveat"))
        layout.addLayout(footer)
        self.show_leak_tab(0)

    def leak_frame_row(self, number, verdict, detail):
        """The result banner: a big number, what it means and a line of detail."""
        frame = QFrame()
        frame.setObjectName("leakFrame")
        frame.setMinimumHeight(96)
        frame.setMaximumHeight(132)
        row = QHBoxLayout(frame)
        row.setContentsMargins(22, 12, 18, 12)
        row.setSpacing(22)
        row.addWidget(number)
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addStretch()
        text.addWidget(verdict)
        text.addWidget(detail)
        text.addStretch()
        row.addLayout(text, 1)
        return frame, row

    def build_leak_email(self):
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(label("EMAIL ADDRESS", "micro"))
        pl.addSpacing(4)
        entry = QHBoxLayout()
        entry.setSpacing(10)
        entry.addWidget(label("›", "prompt"))
        self.leak_email = QLineEdit()
        self.leak_email.setObjectName("target")
        self.leak_email.setPlaceholderText("name@example.com")
        self.leak_email.setClearButtonEnabled(True)
        self.leak_email.setAccessibleName("Email address to check")
        self.leak_email.returnPressed.connect(self.start_leak_email)
        entry.addWidget(self.leak_email, 1)
        entry.addSpacing(8)
        self.leak_email_button = button("CHECK EMAIL", self.start_leak_email, "primary")
        self.leak_email_button.setMinimumWidth(190)
        entry.addWidget(self.leak_email_button)
        pl.addLayout(entry)
        pl.addSpacing(8)
        self.leak_hint = label(self.LEAK_HINT, "hint", True)
        pl.addWidget(self.leak_hint)
        pl.addSpacing(14)
        self.leak_count = label("—", "bigNumber")
        self.leak_count.setMinimumWidth(110)
        self.leak_verdict = label("NO CHECK YET", "verdict")
        self.leak_detail = label("Enter an address to see which breaches expose it and what they leaked.", "hint", True)
        self.leak_frame, row = self.leak_frame_row(self.leak_count, self.leak_verdict, self.leak_detail)
        self.leak_scan_button = button("SCAN THIS EMAIL  ↗", self.scan_leak_email, "small")
        self.leak_scan_button.setToolTip("Run a full scan of this address on the Scan page: breaches, accounts and domain. The scan is saved to History.")
        self.leak_scan_button.setEnabled(False)
        row.addWidget(self.leak_scan_button, 0, Qt.AlignmentFlag.AlignVCenter)
        pl.addWidget(self.leak_frame)
        pl.addSpacing(12)
        self.leak_timeline = BreachTimeline()
        pl.addWidget(self.leak_timeline)
        pl.addSpacing(10)
        self.leak_table = self.results_table(["EXPOSED", "BREACH", "DATE", "DATA", "RECORDS", "SOURCE"], ((0, 130), (1, 200), (2, 100), (4, 110), (5, 200)), 3)
        self.leak_table.itemSelectionChanged.connect(self.leak_row_selected)
        self.leak_timeline.picked.connect(self.select_leak_row)
        pl.addWidget(self.leak_table, 1)
        pl.addSpacing(8)
        sources = QHBoxLayout()
        sources.setSpacing(12)
        sources.addWidget(label("SOURCES", "micro"))
        self.leak_sources = label("", "hint", True)
        sources.addWidget(self.leak_sources, 1)
        sources.addWidget(button("SET HIBP KEY", lambda: self.edit_key(leaks.SERVICE), "small"))
        pl.addLayout(sources)
        return page

    def build_leak_password(self):
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(label("PASSWORD", "micro"))
        pl.addSpacing(4)
        entry = QHBoxLayout()
        entry.setSpacing(10)
        entry.addWidget(label("›", "prompt"))
        self.leak_password = QLineEdit()
        self.leak_password.setObjectName("target")
        self.leak_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.leak_password.setPlaceholderText("type or paste a password")
        self.leak_password.setAccessibleName("Password to check")
        self.leak_password.returnPressed.connect(self.start_leak_password)
        entry.addWidget(self.leak_password, 1)
        self.leak_show = button("SHOW", self.toggle_leak_password, "small")
        entry.addWidget(self.leak_show)
        entry.addSpacing(8)
        self.leak_password_button = button("CHECK PASSWORD", self.start_leak_password, "primary")
        self.leak_password_button.setMinimumWidth(190)
        entry.addWidget(self.leak_password_button)
        pl.addLayout(entry)
        pl.addSpacing(8)
        pl.addWidget(label("Private: the password never leaves this computer. SpyBrain sends only the first 5 characters of its SHA-1 hash to Pwned Passwords and compares the rest here. Nothing is saved, and the box is cleared after the check.", "hint", True))
        pl.addSpacing(22)
        self.pw_count = label("—", "bigNumber")
        self.pw_verdict = label("NO CHECK YET", "verdict")
        self.pw_detail = label("Type a password to see whether it appears in known breaches. Attackers try leaked passwords first.", "hint", True)
        self.pw_frame, _ = self.leak_frame_row(self.pw_count, self.pw_verdict, self.pw_detail)
        pl.addWidget(self.pw_frame)
        pl.addStretch()
        return page

    def show_leak_tab(self, index):
        self.leak_stack.setCurrentIndex(index)
        for i, tab in enumerate(self.leak_tabs):
            tab.setChecked(i == index)
        (self.leak_email, self.leak_password)[index].setFocus()

    def refresh_leaks(self):
        saved = bool(geolocate.load_key(leaks.SERVICE))
        self.leak_sources.setText("XposedOrNot (free, about 25 checks an hour) + Have I Been Pwned (your key is saved)." if saved
                                  else "XposedOrNot (free, about 25 checks an hour). Add a Have I Been Pwned key for a second source.")

    def set_leak_state(self, text, tone="idle"):
        self.leak_state.setText(text)
        self.leak_pulse.set_tone(tone)

    def set_leak_busy(self, busy, mode="email"):
        for control in (self.leak_email, self.leak_email_button, self.leak_password, self.leak_password_button, self.leak_show):
            control.setEnabled(not busy)
        self.leak_email_button.setText("CHECKING" if busy and mode == "email" else "CHECK EMAIL")
        self.leak_password_button.setText("CHECKING" if busy and mode == "password" else "CHECK PASSWORD")
        if busy:
            self.leak_scan_button.setEnabled(False)

    def toggle_leak_password(self):
        hidden = self.leak_password.echoMode() == QLineEdit.EchoMode.Password
        self.leak_password.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.leak_show.setText("HIDE" if hidden else "SHOW")

    def start_leak_task(self, mode, function, cancel=None):
        self.leak_mode, self.leak_cancel = mode, cancel or threading.Event()
        self.set_leak_busy(True, mode)
        self.leak_task = Task(function)
        self.leak_task.done.connect(self.leak_done)
        self.leak_task.failed.connect(self.leak_failed)
        self.leak_task.finished.connect(self.leak_task_finished)
        self.leak_task.start()

    def start_leak_email(self):
        if self.leak_task:
            return
        try:
            email, _ = engine.validate(self.leak_email.text(), "email")
        except ValueError as error:
            self.leak_hint.setText(str(error))
            set_prop(self.leak_hint, "tone", "warn")
            self.leak_email.setFocus()
            return
        set_prop(self.leak_hint, "tone", "")
        self.leak_hint.setText(self.LEAK_HINT)
        self.leak_email.setText(email)
        self.leak_target = email
        key = geolocate.load_key(leaks.SERVICE)
        self.clear_leak_email()
        self.leak_timeline.begin_check()
        self.set_leak_state("Checking breach databases…", "run")
        cancel = threading.Event()
        context = engine.ScanContext(cancel=cancel)
        self.start_leak_task("email", lambda: leaks.check_email(email, key, context.check), cancel)

    def start_leak_password(self):
        if self.leak_task:
            return
        password = self.leak_password.text()
        if not password:
            self.set_leak_state("Type or paste a password first.", "warn")
            self.leak_password.setFocus()
            return
        self.leak_password.clear()
        self.show_leak_banner(self.pw_frame, self.pw_count, self.pw_verdict, self.pw_detail, "…", "CHECKING", "Looking the password hash up. Nothing but its first 5 characters is sent.", "")
        self.set_leak_state("Checking the password hash…", "run")
        self.start_leak_task("password", lambda: leaks.password_pwned(password))

    def show_leak_banner(self, frame, number, verdict, detail, count, words, text, tone):
        number.setText(count)
        verdict.setText(words)
        detail.setText(text)
        for widget in (frame, number):
            set_prop(widget, "tone", tone)

    def clear_leak_email(self):
        self.leak_table.setRowCount(0)
        self.leak_scan_button.setEnabled(False)
        self.show_leak_banner(self.leak_frame, self.leak_count, self.leak_verdict, self.leak_detail, "…", "CHECKING",
                              "Asking the breach databases about this address.", "")

    def leak_done(self, result):
        if self.leak_mode == "email":
            self.leak_email_done(result)
        else:
            self.leak_password_done(result)

    def leak_email_done(self, outcome):
        breaches, sources = outcome["breaches"], outcome["sources"]
        self.leak_timeline.show_breaches(breaches)
        self.fill_leak_table(breaches)
        years = [y for y in (leaks.year_of(b) for b in breaches) if y]
        passwords = [b for b in breaches if leaks.severity(b) == 3]
        personal = [b for b in breaches if leaks.severity(b) == 2]
        plain = sum(1 for b in passwords if b.get("password_risk") == "plain text")
        if not breaches:
            tone, words = "ok", "NO BREACHES FOUND"
            text = f"Nothing in {' and '.join(sources)}. That isn't a guarantee: breaches that were never made public aren't listed."
        else:
            tone = "bad" if passwords else "warn"
            words = ("BREACH" if len(breaches) == 1 else "BREACHES") + (f" SINCE {min(years)}" if years else "")
            facts = []
            if passwords:
                facts.append(f"Passwords were exposed in {len(passwords)} {'breach' if len(passwords) == 1 else 'breaches'}" + (f", {plain} of them stored in plain text" if plain else ""))
            if personal:
                facts.append(("Personal data, but no passwords, in " if passwords else "Personal data was exposed in ") + str(len(personal)))
            unknown = sum(1 for b in breaches if leaks.severity(b) == 0)
            if unknown:
                facts.append(f"{unknown} listed without details")
            text = (". ".join(facts) + "." if facts else "Only the address and usernames were exposed.") + f" Checked: {', '.join(sources)}."
        if outcome.get("cached"):
            text += " Shown from memory: this address was checked less than an hour ago."
        if outcome["errors"]:
            text += " " + " ".join(outcome["errors"])
        self.show_leak_banner(self.leak_frame, self.leak_count, self.leak_verdict, self.leak_detail, str(len(breaches)), words, text, tone)
        self.leak_scan_button.setEnabled(True)
        self.set_leak_state(("No breaches found" if not breaches else f"{len(breaches)} {'breach' if len(breaches) == 1 else 'breaches'} found")
                            + (" · shown from memory" if outcome.get("cached") else ""), "warn" if outcome["errors"] else "ok")
        if MOTION:
            self.flash_until = time.monotonic()+FLASH+0.6
            self.flash_timer.start(33)

    def leak_password_done(self, count):
        if count:
            common = "This is one of the most common passwords. " if count >= 100000 else ""
            self.show_leak_banner(self.pw_frame, self.pw_count, self.pw_verdict, self.pw_detail, f"{count:,}", "TIMES IN KNOWN BREACHES",
                                  common + "Attackers try leaked passwords first. Don't use it anywhere, and change it on every account that still does.", "bad")
            self.set_leak_state("This password is in known breaches.", "err")
        else:
            self.show_leak_banner(self.pw_frame, self.pw_count, self.pw_verdict, self.pw_detail, "0", "NOT FOUND IN KNOWN BREACHES",
                                  "A good sign, not a guarantee. Use a password manager to create a long, unique password for every account.", "ok")
            self.set_leak_state("This password isn't in known breaches.", "ok")

    def leak_failed(self, message):
        self.set_leak_state(message, "warn" if "limit" in message.lower() else "err")
        if self.leak_mode == "email":
            self.leak_timeline.show_error(message)
            self.show_leak_banner(self.leak_frame, self.leak_count, self.leak_verdict, self.leak_detail, "—", "CHECK FAILED", message, "warn")
        else:
            self.show_leak_banner(self.pw_frame, self.pw_count, self.pw_verdict, self.pw_detail, "—", "CHECK FAILED", message, "warn")

    def leak_task_finished(self):
        task = self.leak_task
        self.leak_task = None
        task.deleteLater()
        self.set_leak_busy(False)
        if self.close_pending:
            self.close()

    def fill_leak_table(self, breaches):
        self.leak_table.setRowCount(0)
        for rank, breach in enumerate(breaches):
            severity = leaks.severity(breach)
            data = ", ".join(breach["data"]) or "Not listed"
            if breach.get("password_risk"):
                data += f" · passwords stored as {breach['password_risk']}"
            source = breach["source"] + (" · " + ", ".join(breach["flags"]) if breach.get("flags") else "")
            self.add_row(self.leak_table, [BreachTimeline.NAMES[severity], breach["name"], breach.get("date", ""), data,
                                           f"{breach['records']:,}" if breach.get("records") else "", source], None, "", min(rank, 25))
            row = self.leak_table.rowCount()-1
            self.leak_table.item(row, 0).setForeground(QColor(BreachTimeline.COLORS[severity]))
            name = self.leak_table.item(row, 1)
            name.setForeground(QColor(BONE))
            if breach.get("domain"):
                name.setToolTip(f"{breach['name']} · {breach['domain']}")

    def select_leak_row(self, name):
        for row in range(self.leak_table.rowCount()):
            item = self.leak_table.item(row, 1)
            if item and item.text() == name:
                self.leak_table.selectRow(row)
                self.leak_table.scrollToItem(item)
                return

    def leak_row_selected(self):
        rows = self.leak_table.selectionModel().selectedRows()
        item = self.leak_table.item(rows[0].row(), 1) if rows else None
        self.leak_timeline.highlight(item.text() if item else "")

    def scan_leak_email(self):
        if self.worker or self.locate_worker:
            self.set_leak_state("A scan is running. Wait for it to finish.", "warn")
            return
        self.target.setText(self.leak_target)
        self.kind.setCurrentIndex(self.kind.findData("email"))
        self.navigate(SCAN_PAGE)
        self.target.setFocus()

    def refresh_sources(self):
        self.source_list.clear()
        located = geolocate.engine_status()
        engine_ids = {meta["title"]: name for name, meta in geolocate.ENGINES.items()}
        for name,available in engine.tool_status().items():
            if name in engine_ids and engine_ids[name] not in geolocate.ENABLED_ENGINES:
                continue
            title, checks, used = SOURCE_INFO[name]
            word, tone = ("Ready", "ok") if available else ("Not installed", "err")
            if name in engine_ids:
                available, detail = located[engine_ids[name]]
                word, tone = ("Ready", "ok") if available else (("Needs key", "warn") if detail == "Needs a key" else ("Not installed", "err"))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, {"cells": [
                (word, "status:"+tone),
                (title, "display"), (checks, "body"), (used, "micro")]})
            self.source_list.addItem(item)

    def open_folder(self):
        engine.REPORTS.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(engine.REPORTS)))

    def closeEvent(self,event):
        if self.worker or self.locate_worker or self.leak_task:
            self.close_pending = True
            self.cancel_scan()
            self.leak_cancel.set()
            if self.locate_worker:
                self.locate_worker.cancel.set()
            event.ignore()
        else:
            event.accept()

def main():
    smoke_trace("Creating QApplication")
    app = QApplication(sys.argv)
    smoke_trace("QApplication created")
    app.setApplicationName("SpyBrain")
    app.setOrganizationName("SpyBrain")
    apply_theme(app)
    window = Window()
    smoke_trace("Window created")
    window.show()
    window.target.setFocus()
    dark_title_bar(window)
    if "--smoke-test" not in sys.argv and not window.settings.value("notice/lawful", False, type=bool):
        notice = QMessageBox(window)
        notice.setWindowTitle("Lawful investigations only")
        notice.setText("SpyBrain is a tool for journalists, investigators and threat-intelligence teams.")
        notice.setInformativeText("Use it only for lawful, authorized investigations, and protect the personal data you collect. "
                                  "Face search is blocked for children and teenagers. Results are leads, not proof.")
        notice.addButton("I UNDERSTAND", QMessageBox.ButtonRole.AcceptRole)
        notice.exec()
        window.settings.setValue("notice/lawful", True)
    if "--smoke-test" in sys.argv:
        # A real frozen GUI startup without leaving a test window open.
        def smoke():
            smoke_trace("Smoke timer fired")
            destination = Path(sys.argv[sys.argv.index("--smoke-test")+1])
            destination.mkdir(parents=True,exist_ok=True)
            def finish():
                if window.worker:
                    QTimer.singleShot(100,finish)
                    return
                smoke_trace("Scan finished; saving screenshot")
                window.grab().save(str(destination / "interface.png"))
                (destination / "startup.json").write_text(json.dumps({"version":engine.VERSION,"tools":engine.tool_status(),"window":window.isVisible(),"scan_status":window.report["status"] if window.report else None,"rows":len(window.rows)},indent=2),encoding="utf-8")
                window.close()
                smoke_trace("Window closed")
            if "--smoke-target" in sys.argv:
                window.target.setText(sys.argv[sys.argv.index("--smoke-target")+1])
                window.start_scan()
            finish()
        QTimer.singleShot(1000,smoke)
    return app.exec()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        engine.DATA_ROOT.mkdir(parents=True,exist_ok=True)
        (engine.DATA_ROOT/"startup-error.log").write_text(traceback.format_exc(),encoding="utf-8")
        raise
