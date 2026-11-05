import sys
import os
import time
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRectF
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QProgressBar, QGraphicsDropShadowEffect
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen, QFont

def get_resource_path(relative_path: str) -> str:
    """Gets absolute path to resource, working for dev and for PyInstaller bundle."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class LoadingSpinner(QWidget):
    """Smooth rotating purple arc spinner matching Streamer Calyx aesthetic."""
    def __init__(self, size=20, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.timer.start(16)  # ~60 FPS

    def _rotate(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        
        # Track circle
        track_pen = QPen(QColor(88, 28, 135, 80), 2.5)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)
        
        # Spinning arc
        arc_pen = QPen(QColor(192, 132, 252), 2.5)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, -int(self.angle * 16), -int(100 * 16))

class LoadingSplashScreen(QWidget):
    """
    High-DPI borderless splash screen with rounded corners, top-right status pill,
    spinner, bottom progress bar, and smooth fade-out.
    Enforces a minimum display time of 5 seconds.
    """
    def __init__(self, image_path=None, min_duration_sec=5.0, target_width=680, target_height=425):
        super().__init__()
        if not image_path:
            image_path = get_resource_path("splash-image.png")
        self.image_path = image_path
        self.min_duration_sec = min_duration_sec
        self.target_width = target_width
        self.target_height = target_height
        self.start_time = time.time()
        self._is_finishing = False
        self._fade_anim = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.target_width, self.target_height)

        # Pre-scale base pixmap
        if os.path.exists(self.image_path):
            orig = QPixmap(self.image_path)
            self.base_pixmap = orig.scaled(
                self.target_width, self.target_height,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            self.base_pixmap = QPixmap(self.target_width, self.target_height)
            self.base_pixmap.fill(QColor(20, 15, 30))

        # Root UI Overlay
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 8)

        # Top Bar: Status Pill in Top-Right
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self.status_pill = QWidget(self)
        self.status_pill.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 12, 28, 0.88);
                border: 1px solid rgba(168, 85, 247, 0.6);
                border-radius: 14px;
            }
        """)
        pill_lay = QHBoxLayout(self.status_pill)
        pill_lay.setContentsMargins(10, 4, 12, 4)
        pill_lay.setSpacing(8)

        self.spinner = LoadingSpinner(18, self.status_pill)
        pill_lay.addWidget(self.spinner)

        self.lbl_status = QLabel("Starting up...", self.status_pill)
        self.lbl_status.setStyleSheet("""
            color: #e9d5ff;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        pill_lay.addWidget(self.lbl_status)

        top_bar.addWidget(self.status_pill)
        root_lay.addLayout(top_bar)
        root_lay.addStretch()

        # Bottom Progress Bar
        bottom_box = QVBoxLayout()
        bottom_box.setSpacing(4)
        bottom_box.setContentsMargins(8, 0, 8, 4)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(10)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(20, 15, 35, 0.8);
                border: 1px solid rgba(126, 34, 206, 0.5);
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:0.5 #a855f7, stop:1 #38bdf8);
                border-radius: 2px;
            }
        """)
        bottom_box.addWidget(self.progress_bar)
        root_lay.addLayout(bottom_box)

        # Center on primary screen
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

    def set_status(self, text: str, progress_pct: int = None):
        self.lbl_status.setText(text)
        if progress_pct is not None:
            self.progress_bar.setValue(max(0, min(100, progress_pct)))
        QApplication.processEvents()

    def finish_loading(self, callback=None):
        """Called when app initialization is done. Waits for 5s min time then fades out."""
        if self._is_finishing:
            return
        self._is_finishing = True
        self.set_status("Ready!", 100)

        elapsed = time.time() - self.start_time
        remaining = max(0.0, self.min_duration_sec - elapsed)
        
        QTimer.singleShot(int(remaining * 1000), lambda: self._start_fade_out(callback))

    def _start_fade_out(self, callback=None):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(600)  # 600ms smooth fade
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _on_finished():
            self.close()
            if callback:
                callback()
            self.deleteLater()

        self._fade_anim.finished.connect(_on_finished)
        self._fade_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Clip rounded rect
        clip_path = QPainterPath()
        radius = 14.0
        clip_path.addRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), radius, radius)
        painter.setClipPath(clip_path)

        # Draw base image
        painter.drawPixmap(0, 0, self.base_pixmap)

        # Outer border stroke
        painter.setClipping(False)
        border_pen = QPen(QColor(168, 85, 247, 180), 2.0)
        painter.setPen(border_pen)
        painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), radius, radius)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = LoadingSplashScreen(min_duration_sec=5.0)
    splash.show()

    QTimer.singleShot(1000, lambda: splash.set_status("Loading configuration...", 25))
    QTimer.singleShot(2000, lambda: splash.set_status("Detecting display monitors...", 50))
    QTimer.singleShot(3000, lambda: splash.set_status("Registering hotkeys...", 75))
    QTimer.singleShot(3800, lambda: splash.finish_loading(lambda: app.quit()))

    sys.exit(app.exec())
