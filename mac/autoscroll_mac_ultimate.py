import sys
import os
import math
import time
import threading
import json
import plistlib # [新增] 用于操作 Mac 的 plist 文件
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame, QSlider, QDoubleSpinBox, 
                             QPushButton, QDialog, QGraphicsDropShadowEffect, 
                             QGridLayout, QCheckBox, QComboBox, QInputDialog, 
                             QMessageBox, QSystemTrayIcon, QMenu, QAction, qApp)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QIcon, QCursor
from pynput import mouse

# --- 资源定位 ---
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- 配置文件路径 ---
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".global_mouse_mac_config.json")

# --- [新增] Mac 开机自启管理 ---
class AutoStartManager:
    def __init__(self):
        # 定义 plist 文件的存放路径
        self.label = "com.adai.globalmouse"
        self.plist_name = f"{self.label}.plist"
        self.user_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
        self.plist_path = os.path.join(self.user_agents_dir, self.plist_name)
        
        # 获取当前可执行文件的绝对路径
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的 executable 路径
            self.app_path = sys.executable
        else:
            self.app_path = sys.executable # 开发环境用 python解释器路径

    def is_autorun(self):
        return os.path.exists(self.plist_path)

    def set_autorun(self, enable):
        if enable:
            return self._create_plist()
        else:
            return self._remove_plist()

    def _create_plist(self):
        try:
            if not os.path.exists(self.user_agents_dir):
                os.makedirs(self.user_agents_dir)
            
            plist_content = {
                'Label': self.label,
                'ProgramArguments': [self.app_path],
                'RunAtLoad': True, # 登录时运行
                'KeepAlive': False,
                # 标准输出日志，方便调试（可选）
                # 'StandardOutPath': '/tmp/globalmouse.out',
                # 'StandardErrorPath': '/tmp/globalmouse.err'
            }
            
            with open(self.plist_path, 'wb') as f:
                plistlib.dump(plist_content, f)
            return True
        except Exception as e:
            print(f"Error creating plist: {e}")
            return False

    def _remove_plist(self):
        try:
            if os.path.exists(self.plist_path):
                os.remove(self.plist_path)
            return True
        except Exception as e:
            print(f"Error removing plist: {e}")
            return False

# --- 全局配置 ---
class GlobalConfig:
    dead_zone = 20.0
    sensitivity = 2.0
    speed_factor = 2.0
    overlay_size = 60.0
    enable_horizontal = True 
    start_minimized = False # [新增]
    active = False
    origin_pos = (0, 0)

    def to_dict(self):
        return {
            "sensitivity": self.sensitivity,
            "speed_factor": self.speed_factor,
            "dead_zone": self.dead_zone,
            "overlay_size": self.overlay_size,
            "enable_horizontal": self.enable_horizontal,
            "start_minimized": self.start_minimized
        }

    def from_dict(self, data):
        self.sensitivity = data.get("sensitivity", 2.0)
        self.speed_factor = data.get("speed_factor", 2.0)
        self.dead_zone = data.get("dead_zone", 20.0)
        self.overlay_size = data.get("overlay_size", 60.0)
        self.enable_horizontal = data.get("enable_horizontal", True)
        self.start_minimized = data.get("start_minimized", False)

cfg = GlobalConfig()
mouse_controller = mouse.Controller()

# --- 逻辑信号桥接 ---
class LogicBridge(QObject):
    show_overlay = pyqtSignal()
    hide_overlay = pyqtSignal()
    update_direction = pyqtSignal(str)
    update_size = pyqtSignal(int)
    preview_size = pyqtSignal()

# --- 悬浮图标 ---
class ResizableOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
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
        self.raise_()
        self.preview_timer.start(800)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        scale_factor = self.width() / self.base_size
        p.scale(scale_factor, scale_factor)

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
                path.moveTo(0, -7)
                path.lineTo(-9, 7)
                path.lineTo(9, 7)
                painter.setBrush(QColor(0, 0, 0))
                painter.setPen(QPen(Qt.white, 2))
            else:
                path.moveTo(0, -4)
                path.lineTo(-5, 3)
                path.lineTo(5, 3)
            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()

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
        title = QLabel("Mac 权限说明")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #000000;")
        cl.addWidget(title)
        content = QLabel()
        content.setWordWrap(True); content.setTextFormat(Qt.RichText)
        content.setStyleSheet("font-size: 13px; color: #333333; line-height: 1.5;")
        content.setText("""
            <p><b>⚠️ 权限</b>：请在 系统设置 > 隐私与安全性 > 辅助功能 中勾选本程序。</p>
            <p><b>👻 后台运行</b>：点击左上角红色 X，程序会隐藏到顶部菜单栏。</p>
            <p><b>🚀 开机自启</b>：建议将 APP 放入【应用程序】文件夹后再开启此功能。</p>
        """)
        cl.addWidget(content); cl.addStretch()
        btn = QPushButton("已授权，继续")
        btn.setCursor(Qt.PointingHandCursor); btn.clicked.connect(self.accept)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet("""
            QPushButton { 
                background-color: #007AFF; color: white; font-size: 15px; font-weight: 600; 
                border-radius: 8px; padding: 8px; border: none; 
            }
        """)
        cl.addWidget(btn)
        layout.addWidget(container)

# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        if os.path.exists(resource_path("logo.icns")):
            self.setWindowIcon(QIcon(resource_path("logo.icns")))
        
        self.setWindowTitle("Global Mouse for Mac")
        self.setFixedSize(400, 640) # 增加高度
        self.bridge = LogicBridge()
        self.overlay = ResizableOverlay()
        self.autostart = AutoStartManager() # 自启管理
        
        self.ui_widgets = {}
        self.presets = {"默认": cfg.to_dict()}
        self.current_preset_name = "默认"

        # --- [新增] 初始化菜单栏图标 ---
        self.init_system_tray()

        self.bridge.show_overlay.connect(self.on_show_overlay)
        self.bridge.hide_overlay.connect(self.on_hide_overlay)
        self.bridge.update_direction.connect(self.overlay.set_direction)
        self.bridge.update_size.connect(self.overlay.update_geometry)
        self.bridge.preview_size.connect(self.overlay.show_preview)
        
        self.load_presets_from_file()
        self.init_ui()
        self.start_threads()

    def init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Mac 的菜单栏图标通常使用 monochrome (单色)，但用 icns 也没问题
        if os.path.exists(resource_path("logo.icns")):
            self.tray_icon.setIcon(QIcon(resource_path("logo.icns")))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(3))

        tray_menu = QMenu()
        
        action_show = QAction("显示设置", self)
        action_show.triggered.connect(self.show_normal_window)
        
        action_quit = QAction("完全退出", self)
        action_quit.triggered.connect(qApp.quit)
        
        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        # Mac 上 QSystemTrayIcon 点击行为可能和 Win 不同，主要靠菜单
        self.tray_icon.show()

    def show_normal_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # 重写关闭事件：点击左上角红色 X 时隐藏而不是退出
    def closeEvent(self, event):
        # 隐藏窗口
        self.hide()
        # 第一次隐藏时提示（可选，Mac 用户习惯看菜单栏，可能不需要弹窗）
        event.ignore()

    def load_presets_from_file(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.presets = data.get("presets", {"默认": cfg.to_dict()})
                    last_used = data.get("last_used", "默认")
                    if last_used in self.presets:
                        self.current_preset_name = last_used
                        cfg.from_dict(self.presets[last_used])
            except: pass

    def save_presets_to_file(self):
        data = {
            "presets": self.presets,
            "last_used": self.current_preset_name
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #ECECEC; font-family: '.AppleSystemUIFont', sans-serif; }")
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        header = QLabel("滚动配置")
        header.setStyleSheet("font-size: 26px; font-weight: 800; color: #1C1C1E; margin-left: 5px;")
        main_layout.addWidget(header)

        settings_panel = QFrame()
        settings_panel.setStyleSheet("""
            QFrame { background-color: white; border-radius: 12px; border: 1px solid #D1D1D1; }
            QLabel { color: #000000; font-size: 14px; font-weight: 500; }
            QCheckBox { color: #000000; font-size: 14px; font-weight: 500; spacing: 8px; }
        """)
        
        grid = QGridLayout(settings_panel)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setVerticalSpacing(20)
        grid.setHorizontalSpacing(15)
        
        def add_row(key, row_idx, label_text, val, min_v, max_v, callback, decimals=1):
            lbl = QLabel(label_text)
            grid.addWidget(lbl, row_idx, 0)
            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v); spin.setValue(val); spin.setDecimals(decimals)
            step = 1.0 / (10 ** decimals)
            spin.setSingleStep(step); spin.setFixedWidth(60)
            spin.setStyleSheet("""
                QDoubleSpinBox { color: #000000; background-color: #FFFFFF; border: 1px solid #C0C0C0; 
                    border-radius: 6px; padding: 2px; selection-background-color: #007AFF; selection-color: white; }
            """)
            spin.valueChanged.connect(callback)
            spin.setFocusPolicy(Qt.ClickFocus)

            scale = 10 ** decimals
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(min_v * scale), int(max_v * scale))
            slider.setValue(int(val * scale))
            slider.setStyleSheet("""
                QSlider::groove:horizontal { height: 4px; background: #E5E5EA; border-radius: 2px; }
                QSlider::handle:horizontal { background: #FFFFFF; border: 1px solid #D1D1D6; width: 22px; height: 22px; margin: -9px 0; border-radius: 11px; }
            """)
            slider.valueChanged.connect(lambda v: spin.setValue(v / scale))
            spin.valueChanged.connect(lambda v: slider.setValue(int(v * scale)))
            slider.setFocusPolicy(Qt.NoFocus)
            grid.addWidget(slider, row_idx, 1)
            grid.addWidget(spin, row_idx, 2)
            self.ui_widgets[key] = spin

        add_row("sensitivity", 0, "加速度曲线", cfg.sensitivity, 1.0, 5.0, lambda v: setattr(cfg, 'sensitivity', v), decimals=1)
        add_row("speed_factor", 1, "基础速度", cfg.speed_factor, 0.01, 10.00, lambda v: setattr(cfg, 'speed_factor', v), decimals=2)
        add_row("dead_zone", 2, "中心死区", cfg.dead_zone, 0.0, 100.0, lambda v: setattr(cfg, 'dead_zone', v), decimals=1)
        
        def update_size(val):
            cfg.overlay_size = val
            self.bridge.update_size.emit(int(val))
            self.bridge.preview_size.emit()
        add_row("overlay_size", 3, "UI 大小", cfg.overlay_size, 30, 150, update_size, decimals=0)

        # ---------------- 底部功能开关 ----------------
        # 1. 横向滚动
        chk_horiz = QCheckBox("启用横向滚动")
        chk_horiz.setChecked(cfg.enable_horizontal)
        chk_horiz.toggled.connect(lambda v: setattr(cfg, 'enable_horizontal', v))
        chk_horiz.setFocusPolicy(Qt.NoFocus) 
        grid.addWidget(chk_horiz, 4, 0, 1, 3)
        self.ui_widgets["enable_horizontal"] = chk_horiz

        # 2. [新增] 开机自启
        chk_autorun = QCheckBox("开机自动启动")
        chk_autorun.setChecked(self.autostart.is_autorun())
        chk_autorun.toggled.connect(self.toggle_autorun)
        chk_autorun.setFocusPolicy(Qt.NoFocus)
        grid.addWidget(chk_autorun, 5, 0, 1, 3)

        # 3. [新增] 启动时最小化
        chk_min = QCheckBox("启动时隐藏 (仅显示在菜单栏)")
        chk_min.setChecked(cfg.start_minimized)
        chk_min.toggled.connect(lambda v: setattr(cfg, 'start_minimized', v))
        chk_min.setFocusPolicy(Qt.NoFocus)
        grid.addWidget(chk_min, 6, 0, 1, 3)
        self.ui_widgets["start_minimized"] = chk_min

        main_layout.addWidget(settings_panel)
        main_layout.addStretch()

        # 预设管理
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(10)
        self.combo_presets = QComboBox()
        self.combo_presets.addItems(list(self.presets.keys()))
        self.combo_presets.setCurrentText(self.current_preset_name)
        self.combo_presets.currentTextChanged.connect(self.load_selected_preset)
        self.combo_presets.setFocusPolicy(Qt.NoFocus)
        self.combo_presets.setStyleSheet("QComboBox { color: #000; background: white; border-radius: 8px; padding: 5px; }")
        
        btn_save = QPushButton("保存")
        btn_save.setFocusPolicy(Qt.NoFocus)
        btn_save.setCursor(Qt.PointingHandCursor); btn_save.clicked.connect(self.save_new_preset)
        btn_save.setStyleSheet("QPushButton { background-color: #34C759; color: white; border-radius: 8px; padding: 6px 12px; border:none;}")
        
        btn_del = QPushButton("删除")
        btn_del.setFocusPolicy(Qt.NoFocus)
        btn_del.setCursor(Qt.PointingHandCursor); btn_del.clicked.connect(self.delete_preset)
        btn_del.setStyleSheet("QPushButton { background-color: #FF3B30; color: white; border-radius: 8px; padding: 6px 12px; border:none;}")
        
        preset_layout.addWidget(self.combo_presets)
        preset_layout.addWidget(btn_save)
        preset_layout.addWidget(btn_del)
        main_layout.addLayout(preset_layout)

        btn_help = QPushButton("权限说明")
        btn_help.setCursor(Qt.PointingHandCursor); btn_help.clicked.connect(lambda: HelpDialog(self).exec_())
        btn_help.setFocusPolicy(Qt.NoFocus)
        btn_help.setStyleSheet("""
            QPushButton { background-color: white; color: #007AFF; font-weight: 600; border-radius: 12px; padding: 12px; border: 1px solid #D1D1D6; }
            QPushButton:hover { background-color: #F5F5F5; }
        """)
        main_layout.addWidget(btn_help)

        footer_link = QLabel()
        footer_link.setAlignment(Qt.AlignCenter)
        footer_link.setOpenExternalLinks(True)
        footer_link.setText("<a href='https://github.com/AouTzxc/Global-mouse' style='color: #8E8E93; text-decoration: none; font-weight: bold; font-family: .AppleSystemUIFont;'>By: 阿呆</a>")
        main_layout.addWidget(footer_link)

    def toggle_autorun(self, checked):
        # 写入 ~/Library/LaunchAgents/com.adai.globalmouse.plist
        success = self.autostart.set_autorun(checked)
        if not success:
            sender = self.sender()
            sender.blockSignals(True)
            sender.setChecked(not checked) # 回滚
            sender.blockSignals(False)
            QMessageBox.warning(self, "错误", "无法写入启动配置文件。\n请确保程序在【应用程序】文件夹中运行。")

    def save_new_preset(self):
        text, ok = QInputDialog.getText(self, "保存参数", "请输入预设名称:", text=self.current_preset_name)
        if ok and text:
            self.presets[text] = cfg.to_dict()
            self.current_preset_name = text
            self.save_presets_to_file()
            self.combo_presets.blockSignals(True)
            self.combo_presets.clear()
            self.combo_presets.addItems(list(self.presets.keys()))
            self.combo_presets.setCurrentText(text)
            self.combo_presets.blockSignals(False)

    def delete_preset(self):
        name = self.combo_presets.currentText()
        if name == "默认":
            QMessageBox.warning(self, "提示", "默认配置无法删除。")
            return
        del self.presets[name]
        self.current_preset_name = "默认"
        self.save_presets_to_file()
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        self.combo_presets.addItems(list(self.presets.keys()))
        self.combo_presets.setCurrentText("默认")
        self.combo_presets.blockSignals(False)
        self.load_selected_preset("默认")

    def load_selected_preset(self, name):
        if name in self.presets:
            data = self.presets[name]
            self.current_preset_name = name
            cfg.from_dict(data)
            self.ui_widgets["sensitivity"].setValue(cfg.sensitivity)
            self.ui_widgets["speed_factor"].setValue(cfg.speed_factor)
            self.ui_widgets["dead_zone"].setValue(cfg.dead_zone)
            self.ui_widgets["overlay_size"].setValue(cfg.overlay_size)
            self.ui_widgets["enable_horizontal"].setChecked(cfg.enable_horizontal)
            self.ui_widgets["start_minimized"].setChecked(cfg.start_minimized)
            self.save_presets_to_file()

    def on_show_overlay(self):
        self.overlay.set_direction('neutral')
        cursor_pos = QCursor.pos()
        x = cursor_pos.x()
        y = cursor_pos.y()
        offset = cfg.overlay_size / 2
        self.overlay.move(int(x - offset), int(y - offset))
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.repaint()
    
    def on_hide_overlay(self):
        self.overlay.hide()

    def start_threads(self):
        try:
            self.listener = mouse.Listener(on_click=self.on_click)
            self.listener.start()
            self.scroller = threading.Thread(target=self.scroll_loop, daemon=True)
            self.scroller.start()
        except Exception as e:
            print(f"Permission Error: {e}")

    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.middle:
            if pressed:
                cfg.active = not cfg.active
                if cfg.active:
                    cfg.origin_pos = (x, y)
                    self.bridge.show_overlay.emit()
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
                    dx = curr_x - origin_x
                    dy = curr_y - origin_y
                    if not cfg.enable_horizontal: dx = 0

                    dist = math.hypot(dx, dy)
                    
                    current_dir = 'neutral'
                    if dist > cfg.dead_zone:
                        if abs(dx) > abs(dy): current_dir = 'right' if dx > 0 else 'left'
                        else: current_dir = 'down' if dy > 0 else 'up'
                    if current_dir != last_dir:
                        self.bridge.update_direction.emit(current_dir)
                        last_dir = current_dir

                    if dist > cfg.dead_zone:
                        eff_dist = dist - cfg.dead_zone
                        speed_scalar = math.pow(eff_dist, cfg.sensitivity) * 0.0001 * cfg.speed_factor
                        scroll_y = (dy / dist) * speed_scalar * -1 
                        scroll_x = (dx / dist) * speed_scalar * 1
                        mouse_controller.scroll(scroll_x, scroll_y)
                    time.sleep(0.01)
                except: pass
            else:
                last_dir = 'neutral'
                time.sleep(0.05)

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    
    if os.path.exists(resource_path("logo.icns")):
        app.setWindowIcon(QIcon(resource_path("logo.icns")))
    
    # [关键] 保持后台运行：关闭所有窗口后，app 不退出（因为要在菜单栏运行）
    app.setQuitOnLastWindowClosed(False)

    font = QFont(".AppleSystemUIFont", 13) 
    app.setFont(font)
    
    window = MainWindow()
    
    # [核心] 如果勾选了“启动时隐藏”，则不调用 show()，只显示菜单栏图标
    if not cfg.start_minimized:
        window.show()
    
    sys.exit(app.exec_())