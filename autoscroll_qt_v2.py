import sys
import math
import time
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame, QSlider, QDoubleSpinBox, 
                             QPushButton, QDialog, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPropertyAnimation, pyqtProperty, QPoint
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QPainterPath
from pynput import mouse

# --- 全局配置 ---
class GlobalConfig:
    dead_zone = 20.0
    sensitivity = 2.0      # 默认推荐值
    speed_factor = 2.0     
    active = False
    origin_pos = (0, 0)

cfg = GlobalConfig()
mouse_controller = mouse.Controller()

# --- iOS 风格弹窗 (使用说明) ---
class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 380) # 稍微宽一点以容纳文本

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 容器 Frame (白色圆角背景)
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.98);
                border-radius: 14px;
            }
        """)
        
        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(10)

        # 标题
        title = QLabel("参数使用说明")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #000; margin-bottom: 5px;")
        container_layout.addWidget(title)

        # 内容文本 (支持 HTML 格式)
        content = QLabel()
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        content.setStyleSheet("font-size: 13px; color: #333; line-height: 1.4;")
        content.setText("""
            <p><b>🚀 加速度曲线 (指数)</b><br>
            控制“手感”的关键。数值越大，鼠标离原点越远，加速越猛。
            <ul style='margin-left: -15px; color: #555;'>
                <li><b>1.0</b> = 线性 (死板)</li>
                <li><b>2.0</b> = 抛物线 (推荐)</li>
                <li><b>3.0+</b> = 极速 (轻轻一动就飞快)</li>
            </ul>
            </p>
            <p><b>⚡ 基础速度</b><br>
            整体滚动的速度倍率，用于全局微调快慢。</p>
            <p><b>🎯 中心死区</b><br>
            点击中键后，鼠标在此圆圈范围内移动不会触发滚动 (有效防止手抖误触)。</p>
        """)
        container_layout.addWidget(content)

        container_layout.addStretch()

        # 底部按钮 (iOS 风格蓝色按钮)
        btn_close = QPushButton("知道了")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 10px;
                padding: 10px;
                border: none;
            }
            QPushButton:hover { background-color: #0062CC; }
            QPushButton:pressed { background-color: #0051A8; }
        """)
        container_layout.addWidget(btn_close)

        layout.addWidget(container)

# --- 屏幕上的透明锚点图标 ---
class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(60, 60)
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(0, 0, 0, 180))
        p.setPen(Qt.NoPen)
        p.drawEllipse(5, 5, 50, 50)
        p.setPen(QPen(Qt.white, 2))
        cx, cy = 30, 30
        r = 15
        p.setBrush(Qt.white)
        p.drawEllipse(cx-2, cy-2, 4, 4)
        p.drawLine(cx, cy-r, cx, cy-r+4)
        p.drawLine(cx, cy+r, cx, cy+r-4)
        p.drawLine(cx-r, cy, cx-r+4, cy)
        p.drawLine(cx+r, cy, cx+r-4, cy)

# --- iOS 风格设置卡片 ---
class SettingCard(QFrame):
    def __init__(self, title, control_widget):
        super().__init__()
        self.setStyleSheet("""
            SettingCard {
                background-color: white;
                border-radius: 10px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #000; font-size: 14px; font-weight: 500;")
        layout.addWidget(lbl)
        layout.addStretch()
        layout.addWidget(control_widget)

# --- 逻辑桥接 ---
class LogicBridge(QObject):
    show_overlay = pyqtSignal(int, int)
    hide_overlay = pyqtSignal()

# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("全局平滑滚动 Pro")
        self.setFixedSize(380, 520) # 稍微加高一点
        self.bridge = LogicBridge()
        self.overlay = OverlayWidget()
        self.bridge.show_overlay.connect(self.on_show_overlay)
        self.bridge.hide_overlay.connect(self.on_hide_overlay)
        self.init_ui()
        self.start_threads()

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #F2F2F7; font-family: 'Segoe UI', sans-serif; }")
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 顶部标题
        header = QLabel("滚动设置")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #000; margin-bottom: 5px;")
        layout.addWidget(header)

        # 1. 灵敏度
        self.spin_sens = QDoubleSpinBox()
        self.spin_sens.setRange(1.0, 5.0)
        self.spin_sens.setSingleStep(0.1)
        self.spin_sens.setValue(cfg.sensitivity)
        self.spin_sens.valueChanged.connect(lambda v: setattr(cfg, 'sensitivity', v))
        self.spin_sens.setFixedWidth(60)
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(10, 50)
        self.slider_sens.setValue(int(cfg.sensitivity * 10))
        # 联动
        self.slider_sens.valueChanged.connect(lambda v: self.spin_sens.setValue(v/10))
        self.spin_sens.valueChanged.connect(lambda v: self.slider_sens.setValue(int(v*10)))
        
        sens_box = QWidget()
        sl = QHBoxLayout(sens_box)
        sl.setContentsMargins(0,0,0,0)
        sl.addWidget(self.slider_sens)
        sl.addWidget(self.spin_sens)
        layout.addWidget(SettingCard("加速度曲线", sens_box))

        # 2. 速度
        self.spin_spd = QDoubleSpinBox()
        self.spin_spd.setRange(0.1, 10.0)
        self.spin_spd.setSingleStep(0.1)
        self.spin_spd.setValue(cfg.speed_factor)
        self.spin_spd.valueChanged.connect(lambda v: setattr(cfg, 'speed_factor', v))
        self.spin_spd.setFixedWidth(60)
        self.slider_spd = QSlider(Qt.Horizontal)
        self.slider_spd.setRange(1, 100)
        self.slider_spd.setValue(int(cfg.speed_factor * 10))
        # 联动
        self.slider_spd.valueChanged.connect(lambda v: self.spin_spd.setValue(v/10))
        self.spin_spd.valueChanged.connect(lambda v: self.slider_spd.setValue(int(v*10)))

        spd_box = QWidget()
        sl2 = QHBoxLayout(spd_box)
        sl2.setContentsMargins(0,0,0,0)
        sl2.addWidget(self.slider_spd)
        sl2.addWidget(self.spin_spd)
        layout.addWidget(SettingCard("基础速度", spd_box))

        # 3. 死区
        self.spin_dead = QDoubleSpinBox()
        self.spin_dead.setRange(0, 100)
        self.spin_dead.setValue(cfg.dead_zone)
        self.spin_dead.valueChanged.connect(lambda v: setattr(cfg, 'dead_zone', v))
        self.spin_dead.setFixedWidth(60)
        layout.addWidget(SettingCard("中心死区 (px)", self.spin_dead))

        layout.addStretch()

        # 帮助按钮 (iOS 风格次级按钮)
        btn_help = QPushButton("使用说明")
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.clicked.connect(self.show_help_dialog)
        btn_help.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #007AFF;
                font-size: 16px;
                border-radius: 10px;
                padding: 12px;
                border: 1px solid #D1D1D6;
            }
            QPushButton:hover { background-color: #F2F2F7; }
            QPushButton:pressed { background-color: #E5E5EA; }
        """)
        layout.addWidget(btn_help)

        # 底部提示
        tip = QLabel("Admin Rights Recommended")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet("color: #C7C7CC; font-size: 10px; margin-top: 5px;")
        layout.addWidget(tip)

    def show_help_dialog(self):
        # 创建并显示模态对话框
        dlg = HelpDialog(self)
        dlg.exec_()

    def on_show_overlay(self, x, y):
        self.overlay.move(x - 30, y - 30)
        self.overlay.show()
    
    def on_hide_overlay(self):
        self.overlay.hide()

    def start_threads(self):
        self.listener = mouse.Listener(on_click=self.on_click)
        self.listener.start()
        self.scroller = threading.Thread(target=self.scroll_loop, daemon=True)
        self.scroller.start()

    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.middle:
            if pressed:
                cfg.active = not cfg.active
                if cfg.active:
                    cfg.origin_pos = (x, y)
                    self.bridge.show_overlay.emit(x, y)
                else:
                    self.bridge.hide_overlay.emit()
        elif pressed and (button == mouse.Button.left or button == mouse.Button.right):
            if cfg.active:
                cfg.active = False
                self.bridge.hide_overlay.emit()

    def scroll_loop(self):
        while True:
            if cfg.active:
                try:
                    curr_x, curr_y = mouse_controller.position
                    origin_x, origin_y = cfg.origin_pos
                    dy = curr_y - origin_y
                    dist = abs(dy)
                    if dist > cfg.dead_zone:
                        eff_dist = dist - cfg.dead_zone
                        direction = -1 if dy > 0 else 1
                        # 速度计算公式
                        speed = math.pow(eff_dist, cfg.sensitivity) * 0.00005 * cfg.speed_factor
                        mouse_controller.scroll(0, direction * speed)
                    time.sleep(0.01)
                except: pass
            else:
                time.sleep(0.05)

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
