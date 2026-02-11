import sys
import os
import math
import time
import threading
import ctypes
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame, QSlider, QDoubleSpinBox, 
                             QPushButton, QDialog, QGraphicsDropShadowEffect, QGridLayout, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QIcon
from pynput import mouse

# --- 资源定位 ---
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- 全局配置 ---
class GlobalConfig:
    dead_zone = 20.0
    sensitivity = 2.0
    speed_factor = 2.0
    overlay_size = 60.0
    enable_horizontal = True  # [新增] 横向滚动开关
    active = False
    origin_pos = (0, 0)

cfg = GlobalConfig()
mouse_controller = mouse.Controller()

# --- 逻辑信号桥接 ---
class LogicBridge(QObject):
    show_overlay = pyqtSignal(int, int)
    hide_overlay = pyqtSignal()
    update_direction = pyqtSignal(str) # 支持 'up', 'down', 'left', 'right', 'neutral'
    update_size = pyqtSignal(int)
    preview_size = pyqtSignal()

# --- 全向透明悬浮图标 ---
class ResizableOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.base_size = 60.0
        self.update_geometry(int(cfg.overlay_size))
        self.direction = 'neutral'
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.hide)

    def update_geometry(self, size):
        self.setFixedSize(size, size)
        self.update()

    def set_direction(self, direction):
        if self.direction != direction:
            self.direction = direction
            self.update()
            
    def show_preview(self):
        screen = QApplication.primaryScreen().geometry()
        cx, cy = screen.center().x(), screen.center().y()
        self.set_direction('neutral')
        self.move(int(cx - self.width()/2), int(cy - self.height()/2))
        self.show()
        self.preview_timer.start(800)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        scale_factor = self.width() / self.base_size
        p.scale(scale_factor, scale_factor)

        # 样式：深灰填充 + 白色描边
        fill_color = QColor(50, 50, 50) 
        stroke_color = QColor(255, 255, 255, 220)
        p.setBrush(fill_color)
        p.setPen(QPen(stroke_color, 2))
        p.drawEllipse(-4, -4, 8, 8)
        
        def draw_arrow(painter, angle, is_active):
            painter.save()
            painter.rotate(angle)
            painter.translate(0, -12) 
            path = QPainterPath()
            if is_active:
                # 激活状态：大实心箭头
                path.moveTo(0, -7)
                path.lineTo(-9, 7)
                path.lineTo(9, 7)
                painter.setBrush(QColor(0, 0, 0)) # 纯黑填充
                painter.setPen(QPen(Qt.white, 2)) # 亮白描边
            else:
                # 未激活状态：小箭头
                path.moveTo(0, -4)
                path.lineTo(-5, 3)
                path.lineTo(5, 3)
                # 使用默认画笔
            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()

        # 根据方向点亮箭头
        # 0=上, 180=下, 270=左, 90=右
        if self.direction == 'neutral':
            draw_arrow(p, 0, False); draw_arrow(p, 180, False)
            draw_arrow(p, 270, False); draw_arrow(p, 90, False)
        elif self.direction == 'up':
            draw_arrow(p, 0, True)
        elif self.direction == 'down':
            draw_arrow(p, 180, True)
        elif self.direction == 'left':
            draw_arrow(p, 270, True)
        elif self.direction == 'right':
            draw_arrow(p, 90, True)

# --- 帮助弹窗 ---
class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 380)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.98); border-radius: 14px; }")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20); shadow.setColor(QColor(0, 0, 0, 60)); shadow.setOffset(0, 5)
        container.setGraphicsEffect(shadow)
        cl = QVBoxLayout(container); cl.setContentsMargins(25, 25, 25, 25); cl.setSpacing(15)
        title = QLabel("参数说明")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #000;")
        cl.addWidget(title)
        content = QLabel()
        content.setWordWrap(True); content.setTextFormat(Qt.RichText)
        content.setStyleSheet("font-size: 13px; color: #444; line-height: 1.5;")
        content.setText("""
            <p><b>🚀 加速度 (指数)</b><br>控制加速手感。1.0 平稳 -> 3.0 极速。</p>
            <p><b>⚡ 基础速度</b><br>全局滚动的快慢倍率。</p>
            <p><b>🎯 误触死区</b><br>防止手抖误触的静止范围。</p>
            <p><b>↔️ 横向滚动</b><br>开启后可左右拖动(如Excel)。</p>
        """)
        cl.addWidget(content); cl.addStretch()
        btn = QPushButton("明白")
        btn.setCursor(Qt.PointingHandCursor); btn.clicked.connect(self.accept)
        btn.setStyleSheet("QPushButton { background-color: #007AFF; color: white; font-size: 15px; font-weight: 600; border-radius: 8px; padding: 8px; border: none; }")
        cl.addWidget(btn)
        layout.addWidget(container)

# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        if os.path.exists(resource_path("logo.ico")):
            self.setWindowIcon(QIcon(resource_path("logo.ico")))
        
        self.setWindowTitle("Smooth Scroll XY")
        self.setFixedSize(400, 540) # 增加高度容纳新选项
        self.bridge = LogicBridge()
        self.overlay = ResizableOverlay()
        
        self.bridge.show_overlay.connect(self.on_show_overlay)
        self.bridge.hide_overlay.connect(self.on_hide_overlay)
        self.bridge.update_direction.connect(self.overlay.set_direction)
        self.bridge.update_size.connect(self.overlay.update_geometry)
        self.bridge.preview_size.connect(self.overlay.show_preview)
        
        self.init_ui()
        self.start_threads()

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #F2F2F7; font-family: 'Segoe UI', sans-serif; }")
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 30, 20, 20)
        
        header = QLabel("滚动配置")
        header.setStyleSheet("font-size: 26px; font-weight: 800; color: #1C1C1E; margin-left: 5px;")
        main_layout.addWidget(header)

        settings_panel = QFrame()
        settings_panel.setStyleSheet("""
            QFrame { background-color: white; border-radius: 12px; }
            QLabel { color: #000; font-size: 14px; font-weight: 500; }
            QCheckBox { font-size: 14px; font-weight: 500; color: #000; spacing: 10px; }
            QCheckBox::indicator { width: 22px; height: 22px; border-radius: 4px; border: 1px solid #C7C7CC; background: white; }
            QCheckBox::indicator:checked { background-color: #007AFF; border-color: #007AFF; image: url(none); }
        """)
        
        grid = QGridLayout(settings_panel)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setVerticalSpacing(25)
        grid.setHorizontalSpacing(15)
        
        def add_row(row_idx, label_text, val, min_v, max_v, callback, slider_max=100, is_int=False):
            lbl = QLabel(label_text)
            grid.addWidget(lbl, row_idx, 0)
            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v); spin.setValue(val); spin.setSingleStep(1.0 if is_int else 0.1); spin.setFixedWidth(55)
            if is_int: spin.setDecimals(0)
            spin.setStyleSheet("QDoubleSpinBox { border: 1px solid #E5E5EA; border-radius: 6px; padding: 2px; background: #F2F2F7; }")
            spin.valueChanged.connect(callback)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(min_v * 10) if not is_int else int(min_v), int(max_v * 10) if not is_int else int(max_v))
            slider.setValue(int(val * 10) if not is_int else int(val))
            slider.setStyleSheet("""
                QSlider::groove:horizontal { height: 4px; background: #E5E5EA; border-radius: 2px; }
                QSlider::handle:horizontal { background: #FFFFFF; border: 1px solid #D1D1D6; width: 22px; height: 22px; margin: -9px 0; border-radius: 11px; }
            """)
            if is_int:
                slider.valueChanged.connect(lambda v: spin.setValue(v))
                spin.valueChanged.connect(lambda v: slider.setValue(int(v)))
            else:
                slider.valueChanged.connect(lambda v: spin.setValue(v/10))
                spin.valueChanged.connect(lambda v: slider.setValue(int(v*10)))
            grid.addWidget(slider, row_idx, 1)
            grid.addWidget(spin, row_idx, 2)

        add_row(0, "加速度曲线", cfg.sensitivity, 1.0, 5.0, lambda v: setattr(cfg, 'sensitivity', v), 50)
        add_row(1, "基础速度", cfg.speed_factor, 0.1, 10.0, lambda v: setattr(cfg, 'speed_factor', v), 100)
        add_row(2, "中心死区", cfg.dead_zone, 0.0, 100.0, lambda v: setattr(cfg, 'dead_zone', v), 100)
        
        # UI 大小
        def update_size(val):
            cfg.overlay_size = val
            self.bridge.update_size.emit(int(val))
            self.bridge.preview_size.emit()
        add_row(3, "UI 大小", cfg.overlay_size, 30, 150, update_size, is_int=True)

        # [新增] 横向滚动开关
        chk_horiz = QCheckBox("启用横向滚动")
        chk_horiz.setChecked(cfg.enable_horizontal)
        chk_horiz.toggled.connect(lambda v: setattr(cfg, 'enable_horizontal', v))
        # 放在第4行，跨3列
        grid.addWidget(chk_horiz, 4, 0, 1, 3)

        main_layout.addWidget(settings_panel)
        main_layout.addStretch()

        btn_help = QPushButton("使用说明")
        btn_help.setCursor(Qt.PointingHandCursor); btn_help.clicked.connect(lambda: HelpDialog(self).exec_())
        btn_help.setStyleSheet("""
            QPushButton { 
                background-color: white; color: #007AFF; font-size: 16px; font-weight: 600;
                border-radius: 12px; padding: 14px; border: 1px solid #D1D1D6; 
            }
            QPushButton:hover { background-color: #F2F2F7; }
        """)
        main_layout.addWidget(btn_help)

        footer_link = QLabel()
        footer_link.setAlignment(Qt.AlignCenter)
        footer_link.setOpenExternalLinks(True)
        footer_link.setText("<a href='https://github.com/AouTzxc/Global-mouse' style='color: #8E8E93; text-decoration: none; font-weight: bold; font-family: Segoe UI;'>By: 阿呆</a>")
        main_layout.addWidget(footer_link)

    def on_show_overlay(self, x, y):
        self.overlay.set_direction('neutral')
        offset = cfg.overlay_size / 2
        self.overlay.move(int(x - offset), int(y - offset))
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
        last_dir = 'neutral'
        while True:
            if cfg.active:
                try:
                    curr_x, curr_y = mouse_controller.position
                    origin_x, origin_y = cfg.origin_pos
                    
                    # 1. 计算两个轴的距离
                    dx = curr_x - origin_x
                    dy = curr_y - origin_y
                    
                    # 2. 如果没开启横向，强制 dx 为 0
                    if not cfg.enable_horizontal:
                        dx = 0

                    # 3. 计算直线距离 (欧几里得距离)
                    # 只有当鼠标离开死区圆圈时才滚动
                    dist = math.hypot(dx, dy)
                    
                    # --- 方向判断逻辑 (用于 UI 反馈) ---
                    current_dir = 'neutral'
                    if dist > cfg.dead_zone:
                        # 判断是主要往横向动，还是纵向动
                        if abs(dx) > abs(dy):
                            current_dir = 'right' if dx > 0 else 'left'
                        else:
                            current_dir = 'down' if dy > 0 else 'up'
                    
                    if current_dir != last_dir:
                        self.bridge.update_direction.emit(current_dir)
                        last_dir = current_dir

                    # --- 滚动执行逻辑 ---
                    if dist > cfg.dead_zone:
                        eff_dist = dist - cfg.dead_zone
                        
                        # 4. 计算总速度标量 (基于距离的非线性加速)
                        # speed_scalar 是一个正数，代表滚动的猛烈程度
                        speed_scalar = math.pow(eff_dist, cfg.sensitivity) * 0.00005 * cfg.speed_factor
                        
                        # 5. 将速度标量分解回 X 和 Y 分量
                        # 使用单位向量 (dx/dist, dy/dist)
                        # 注意：Scroll 函数中：
                        # Y轴: 负数向下滚 (Windows通常逻辑: 滚轮向下滚，内容向下走 -> 值通常是负的)
                        # X轴: 正数向右滚
                        
                        # 这里我们需要反向：鼠标往下拉(dy>0)，我们希望页面往下滚(scroll<0)
                        scroll_y = (dy / dist) * speed_scalar * -1 
                        scroll_x = (dx / dist) * speed_scalar * 1  # 鼠标往右拉(dx>0)，页面往右滚(scroll>0)

                        mouse_controller.scroll(scroll_x, scroll_y)
                        
                    time.sleep(0.01)
                except Exception as e:
                    # print(f"Error: {e}") 
                    pass
            else:
                last_dir = 'neutral'
                time.sleep(0.05)

if __name__ == "__main__":
    myappid = 'adai.smoothscroll.xy.v2.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    
    if os.path.exists(resource_path("logo.ico")):
        app.setWindowIcon(QIcon(resource_path("logo.ico")))
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())