# Global Mouse - A smooth scrolling tool for Windows & macOS
# Copyright (C) 2026 AouTzxc
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import sys
import os
import math
import time
import threading
import json
import platform
import subprocess
from pynput import mouse, keyboard

# --- PySide6 导入 ---
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame, QSlider, QDoubleSpinBox, 
                             QPushButton, QDialog, QGridLayout, QCheckBox, 
                             QSystemTrayIcon, QMenu, QMessageBox, QComboBox, 
                             QInputDialog, QTextEdit, QKeySequenceEdit)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QIcon, QCursor, QAction, QKeySequence

# --- 跨平台特定的库 ---
OS_NAME = platform.system()
if OS_NAME == "Windows":
    import winreg
    import ctypes
    from ctypes import wintypes
elif OS_NAME == "Darwin":
    import plistlib

# --- 资源定位 ---
def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".global_mouse_config.json")

# --- 跨平台开机自启管理 ---
class AutoStartManager:
    def __init__(self):
        self.app_name = "GlobalMouse"
        if getattr(sys, 'frozen', False):
            self.app_path = sys.executable
        else:
            self.app_path = os.path.abspath(__file__)
            
        if OS_NAME == "Darwin":
            self.label = "com.adai.globalmouse"
            self.plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{self.label}.plist")
    
    def is_autorun(self):
        if OS_NAME == "Windows":
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                value, _ = winreg.QueryValueEx(key, self.app_name)
                winreg.CloseKey(key)
                return value == self.app_path
            except: return False
        elif OS_NAME == "Darwin":
            return os.path.exists(self.plist_path)
        return False

    def set_autorun(self, enable):
        if OS_NAME == "Windows":
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                if enable: winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, self.app_path)
                else:
                    try: winreg.DeleteValue(key, self.app_name)
                    except FileNotFoundError: pass
                winreg.CloseKey(key)
                return True
            except Exception as e: return False
        elif OS_NAME == "Darwin":
            if enable:
                try:
                    os.makedirs(os.path.dirname(self.plist_path), exist_ok=True)
                    plist_content = {'Label': self.label, 'ProgramArguments': [self.app_path], 'RunAtLoad': True, 'KeepAlive': False}
                    with open(self.plist_path, 'wb') as f: plistlib.dump(plist_content, f)
                    return True
                except Exception as e: return False
            else:
                try:
                    if os.path.exists(self.plist_path): os.remove(self.plist_path)
                    return True
                except: return False
        return False

# --- 全局配置 ---
class GlobalConfig:
    dead_zone = 20.0
    sensitivity = 2.0
    speed_factor = 2.0
    overlay_size = 60.0
    enable_horizontal = True
    start_minimized = False
    
    horizontal_hotkey = ""  
    
    filter_mode = 0  
    filter_list = [] 
    disable_fullscreen = False 
    disable_desktop = True # [新增] 默认屏蔽桌面
    
    active = False
    origin_pos = (0, 0)
    current_window_name = ""
    current_window_class = "" # [新增] 用于存储窗口底层类名
    is_fullscreen = False

    def to_dict(self):
        return {
            "sensitivity": self.sensitivity, "speed_factor": self.speed_factor,
            "dead_zone": self.dead_zone, "overlay_size": self.overlay_size,
            "enable_horizontal": self.enable_horizontal, "start_minimized": self.start_minimized,
            "horizontal_hotkey": self.horizontal_hotkey, 
            "filter_mode": self.filter_mode, "filter_list": self.filter_list,
            "disable_fullscreen": self.disable_fullscreen,
            "disable_desktop": self.disable_desktop
        }

    def from_dict(self, data):
        self.sensitivity = data.get("sensitivity", 2.0)
        self.speed_factor = data.get("speed_factor", 2.0)
        self.dead_zone = data.get("dead_zone", 20.0)
        self.overlay_size = data.get("overlay_size", 60.0)
        self.enable_horizontal = data.get("enable_horizontal", True)
        self.start_minimized = data.get("start_minimized", False)
        self.horizontal_hotkey = data.get("horizontal_hotkey", "") 
        self.filter_mode = data.get("filter_mode", 0)
        self.filter_list = data.get("filter_list", [])
        self.disable_fullscreen = data.get("disable_fullscreen", False)
        self.disable_desktop = data.get("disable_desktop", True)

cfg = GlobalConfig()
mouse_controller = mouse.Controller()

# --- 全局键盘监听器 ---
class KeyboardManager:
    def __init__(self, bridge_callback):
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.current_keys = set()
        self.bridge_callback = bridge_callback
        self.qt_to_pynput = {
            'pgup': 'page_up', 'pgdown': 'page_down', 'ins': 'insert',
            'del': 'delete', 'esc': 'esc', 'return': 'enter'
        }

    def start(self):
        self.listener.start()

    def _get_key_name(self, key):
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else None
        elif isinstance(key, keyboard.Key):
            return key.name
        return None

    def on_press(self, key):
        key_name = self._get_key_name(key)
        if key_name:
            if 'ctrl' in key_name: key_name = 'ctrl'
            elif 'alt' in key_name: key_name = 'alt'
            elif 'shift' in key_name: key_name = 'shift'
            elif 'cmd' in key_name: key_name = 'meta'
            
            self.current_keys.add(key_name)
            self.check_hotkey()

    def on_release(self, key):
        key_name = self._get_key_name(key)
        if key_name:
            if 'ctrl' in key_name: key_name = 'ctrl'
            elif 'alt' in key_name: key_name = 'alt'
            elif 'shift' in key_name: key_name = 'shift'
            elif 'cmd' in key_name: key_name = 'meta'
            
            if key_name in self.current_keys:
                self.current_keys.remove(key_name)

    def check_hotkey(self):
        if not cfg.horizontal_hotkey: return
        
        qt_keys = cfg.horizontal_hotkey.lower().split('+')
        target_keys = set()
        for k in qt_keys:
            k = self.qt_to_pynput.get(k, k)
            target_keys.add(k)
            
        if self.current_keys == target_keys:
            self.bridge_callback()

# --- 窗口侦听器 ---
class WindowMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.screen_width = 0
        self.screen_height = 0

    def run(self):
        time.sleep(2)
        try:
            screen_geom = QApplication.primaryScreen().geometry()
            self.screen_width = screen_geom.width()
            self.screen_height = screen_geom.height()
        except: pass

        while True:
            try:
                if OS_NAME == "Windows":
                    user32 = ctypes.windll.user32
                    hwnd = user32.GetForegroundWindow()
                    if hwnd:
                        length = user32.GetWindowTextLengthW(hwnd)
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        cfg.current_window_name = buf.value
                        
                        # [获取类名，用于屏蔽桌面]
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, class_buf, 256)
                        cfg.current_window_class = class_buf.value
                        
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        cfg.is_fullscreen = (w >= self.screen_width and h >= self.screen_height)
                
                elif OS_NAME == "Darwin":
                    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
                    res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
                    cfg.current_window_name = res.stdout.strip()
                    cfg.is_fullscreen = False 
            except Exception: pass
            time.sleep(0.5)

# --- 逻辑信号桥接 ---
class LogicBridge(QObject):
    show_overlay = Signal()
    hide_overlay = Signal()
    update_direction = Signal(str)
    update_size = Signal(int)
    preview_size = Signal()
    toggle_horizontal = Signal() 

# --- 悬浮图标 ---
class ResizableOverlay(QWidget):
    def __init__(self):
        super().__init__()
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if OS_NAME == "Windows": flags |= Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.base_size = 60.0
        self.update_geometry(int(cfg.overlay_size))
        self.direction = 'neutral'
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.hide)

    def update_geometry(self, size):
        self.setFixedSize(size, size); self.update()

    def set_direction(self, direction):
        if self.direction != direction:
            self.direction = direction; self.update()
            
    def show_preview(self):
        screen = QApplication.primaryScreen().geometry()
        self.set_direction('neutral')
        self.move(int(screen.center().x() - self.width()/2), int(screen.center().y() - self.height()/2))
        self.show(); self.raise_(); self.preview_timer.start(800)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        scale = self.width() / self.base_size; p.scale(scale, scale)

        p.setBrush(QColor(50, 50, 50)); p.setPen(QPen(QColor(255, 255, 255, 220), 2))
        p.drawEllipse(-4, -4, 8, 8)
        
        def draw_arrow(painter, angle, is_active):
            painter.save(); painter.rotate(angle); painter.translate(0, -12) 
            path = QPainterPath()
            if is_active:
                path.moveTo(0, -7); path.lineTo(-9, 7); path.lineTo(9, 7)
                painter.setBrush(QColor(0, 0, 0)); painter.setPen(QPen(Qt.white, 2))
            else:
                path.moveTo(0, -4); path.lineTo(-5, 3); path.lineTo(5, 3)
            path.closeSubpath(); painter.drawPath(path); painter.restore()

        if self.direction == 'neutral':
            draw_arrow(p, 0, False); draw_arrow(p, 180, False); draw_arrow(p, 270, False); draw_arrow(p, 90, False)
        elif self.direction == 'up': draw_arrow(p, 0, True)
        elif self.direction == 'down': draw_arrow(p, 180, True)
        elif self.direction == 'left': draw_arrow(p, 270, True)
        elif self.direction == 'right': draw_arrow(p, 90, True)

# --- 高级规则设置窗口 ---
class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("高级规则 (防误触/过滤)")
        self.setFixedSize(380, 450) 
        self.setStyleSheet("""
            QDialog { background-color: #F8F8F8; }
            QLabel { font-size: 13px; color: #333; }
            QTextEdit { border: 1px solid #CCC; border-radius: 6px; padding: 5px; background: #FFF; font-size: 13px;}
            QComboBox { border: 1px solid #CCC; border-radius: 6px; padding: 4px; background: #FFF; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        
        self.chk_fullscreen = QCheckBox("🎮 智能防误触：在所有全屏程序中自动禁用")
        self.chk_fullscreen.setChecked(cfg.disable_fullscreen)
        self.chk_fullscreen.setStyleSheet("font-weight: bold; color: #D32F2F;")
        layout.addWidget(self.chk_fullscreen)
        
        # [新增] 屏蔽桌面开关
        self.chk_desktop = QCheckBox("🖥️ 屏蔽系统桌面：在桌面上自动禁用滚动")
        self.chk_desktop.setChecked(cfg.disable_desktop)
        self.chk_desktop.setStyleSheet("font-weight: bold; color: #1976D2;")
        layout.addWidget(self.chk_desktop)
        
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #DDD;")
        layout.addWidget(line)
        
        layout.addWidget(QLabel("<b>应用过滤模式：</b>"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["全局生效 (不进行过滤)", "黑名单模式 (在以下程序中禁用)", "白名单模式 (仅在以下程序中启用)"])
        self.combo_mode.setCurrentIndex(cfg.filter_mode)
        layout.addWidget(self.combo_mode)
        
        layout.addWidget(QLabel("<b>输入应用名称关键词 (每行一个)：</b>\n(例如输入 'League' 或 'AutoCAD')"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("\n".join(cfg.filter_list))
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存规则")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("background-color: #007AFF; color: white; border-radius: 6px; padding: 8px 0; font-weight: bold;")
        btn_save.clicked.connect(self.save_and_close)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def save_and_close(self):
        cfg.disable_fullscreen = self.chk_fullscreen.isChecked()
        cfg.disable_desktop = self.chk_desktop.isChecked()
        cfg.filter_mode = self.combo_mode.currentIndex()
        lines = self.text_edit.toPlainText().split('\n')
        cfg.filter_list = [line.strip() for line in lines if line.strip()]
        self.accept()

# --- 自定义快捷键输入框 (防连招且支持退格清空) ---
class HotkeyEdit(QKeySequenceEdit):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete) and event.modifiers() == Qt.NoModifier:
            self.clear() 
        else:
            super().keyPressEvent(event)

# --- 主界面 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        icon_name = "logo.icns" if OS_NAME == "Darwin" else "logo.ico"
        if os.path.exists(resource_path(icon_name)):
            self.setWindowIcon(QIcon(resource_path(icon_name)))
        
        self.setWindowTitle("Global Mouse")
        self.setFixedSize(400, 680)
        self.bridge = LogicBridge()
        self.overlay = ResizableOverlay()
        self.autostart = AutoStartManager()
        
        self.ui_widgets = {}
        self.presets = {"默认": cfg.to_dict()}
        self.current_preset_name = "默认"
        
        self.load_presets_from_file()
        self.init_system_tray(icon_name)
        
        self.bridge.show_overlay.connect(self.on_show_overlay)
        self.bridge.hide_overlay.connect(self.on_hide_overlay)
        self.bridge.update_direction.connect(self.overlay.set_direction)
        self.bridge.update_size.connect(self.overlay.update_geometry)
        self.bridge.preview_size.connect(self.overlay.show_preview)
        self.bridge.toggle_horizontal.connect(self.on_toggle_horizontal_hotkey)
        
        self.init_ui()
        self.start_threads()

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
        data = {"presets": self.presets, "last_used": self.current_preset_name}
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass

    def init_system_tray(self, icon_name):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path(icon_name)
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            from PySide6.QtWidgets import QStyle
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))

        tray_menu = QMenu()
        action_show = QAction("显示设置", self)
        action_show.triggered.connect(self.show_normal_window)
        action_quit = QAction("退出程序", self)
        action_quit.triggered.connect(QApplication.instance().quit)
        
        tray_menu.addAction(action_show); tray_menu.addSeparator(); tray_menu.addAction(action_quit)
        self.tray_icon.setContextMenu(tray_menu); self.tray_icon.activated.connect(self.on_tray_click); self.tray_icon.show()

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.show_normal_window()

    def show_normal_window(self):
        self.show(); self.setWindowState(Qt.WindowNoState); self.raise_(); self.activateWindow()

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            if OS_NAME == "Windows" and not getattr(self, 'has_shown_msg', False):
                self.tray_icon.showMessage("已最小化", "程序正在后台运行", QSystemTrayIcon.Information, 2000)
                self.has_shown_msg = True
            event.ignore()
        else: event.accept()

    def init_ui(self):
        if OS_NAME == "Darwin": self.setStyleSheet("QMainWindow { background-color: #ECECEC; font-family: '.AppleSystemUIFont', sans-serif; }")
        else: self.setStyleSheet("QMainWindow { background-color: #F2F2F7; font-family: 'Segoe UI', sans-serif; }")
            
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central); main_layout.setSpacing(15); main_layout.setContentsMargins(20, 20, 20, 20)
        
        header = QLabel("滚动配置")
        header.setStyleSheet("font-size: 26px; font-weight: 800; color: #1C1C1E; margin-left: 5px;")
        main_layout.addWidget(header)

        settings_panel = QFrame()
        settings_panel.setStyleSheet("""
            QFrame { background-color: white; border-radius: 12px; border: 1px solid #D1D1D1; }
            QLabel { color: #000; font-size: 14px; font-weight: 500; }
            QCheckBox { color: #000; font-size: 14px; font-weight: 500; spacing: 8px; }
        """)
        
        grid = QGridLayout(settings_panel)
        grid.setContentsMargins(20, 20, 20, 20); grid.setVerticalSpacing(18); grid.setHorizontalSpacing(15)
        
        def add_row(key, row_idx, label_text, val, min_v, max_v, callback, decimals=1):
            lbl = QLabel(label_text); grid.addWidget(lbl, row_idx, 0)
            spin = QDoubleSpinBox()
            spin.setRange(min_v, max_v); spin.setValue(val); spin.setDecimals(decimals)
            spin.setSingleStep(1.0 / (10 ** decimals))
            spin.setMinimumWidth(100) # [原生控件适配 4K]
            spin.valueChanged.connect(callback); spin.setFocusPolicy(Qt.ClickFocus)

            scale = 10 ** decimals
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(min_v * scale), int(max_v * scale)); slider.setValue(int(val * scale))
            slider.valueChanged.connect(lambda v: spin.setValue(v / scale))
            spin.valueChanged.connect(lambda v: slider.setValue(int(v * scale)))
            slider.setFocusPolicy(Qt.NoFocus)
            
            grid.addWidget(slider, row_idx, 1); grid.addWidget(spin, row_idx, 2)
            self.ui_widgets[key] = spin

        add_row("sensitivity", 0, "加速度曲线", cfg.sensitivity, 1.0, 5.0, lambda v: setattr(cfg, 'sensitivity', v), decimals=1)
        add_row("speed_factor", 1, "基础速度", cfg.speed_factor, 0.01, 10.00, lambda v: setattr(cfg, 'speed_factor', v), decimals=2)
        add_row("dead_zone", 2, "中心死区", cfg.dead_zone, 0.0, 100.0, lambda v: setattr(cfg, 'dead_zone', v), decimals=1)
        add_row("overlay_size", 3, "UI 大小", cfg.overlay_size, 30, 150, lambda v: (setattr(cfg, 'overlay_size', v), self.bridge.update_size.emit(int(v)), self.bridge.preview_size.emit()), decimals=0)

        horiz_layout = QHBoxLayout()
        chk_horiz = QCheckBox("启用横向滚动")
        chk_horiz.setChecked(cfg.enable_horizontal)
        chk_horiz.toggled.connect(lambda v: setattr(cfg, 'enable_horizontal', v))
        chk_horiz.setFocusPolicy(Qt.NoFocus)
        self.ui_widgets["enable_horizontal"] = chk_horiz
        
        lbl_hotkey = QLabel("快捷键:")
        lbl_hotkey.setStyleSheet("color: #666; font-size: 12px; margin-left: 10px;")
        
        self.hotkey_edit = HotkeyEdit()
        self.hotkey_edit.setKeySequence(QKeySequence(cfg.horizontal_hotkey))
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.setToolTip("点击输入框，直接按下你要的快捷键 (按退格键清除)")
        self.hotkey_edit.setStyleSheet("QKeySequenceEdit { border: 1px solid #CCC; border-radius: 4px; padding: 2px; background: #FFF; color: #000; min-width: 80px; }")
        self.hotkey_edit.keySequenceChanged.connect(lambda seq: setattr(cfg, 'horizontal_hotkey', seq.toString()))
        self.ui_widgets["hotkey_edit"] = self.hotkey_edit
        
        horiz_layout.addWidget(chk_horiz); horiz_layout.addStretch(); horiz_layout.addWidget(lbl_hotkey); horiz_layout.addWidget(self.hotkey_edit)
        grid.addLayout(horiz_layout, 4, 0, 1, 3)

        chk_autorun = QCheckBox("开机自动启动")
        chk_autorun.setChecked(self.autostart.is_autorun())
        chk_autorun.toggled.connect(self.toggle_autorun)
        chk_autorun.setFocusPolicy(Qt.NoFocus); grid.addWidget(chk_autorun, 5, 0, 1, 3)

        chk_min = QCheckBox("启动时隐藏最小化")
        chk_min.setChecked(cfg.start_minimized)
        chk_min.toggled.connect(lambda v: setattr(cfg, 'start_minimized', v))
        chk_min.setFocusPolicy(Qt.NoFocus); grid.addWidget(chk_min, 6, 0, 1, 3)
        self.ui_widgets["start_minimized"] = chk_min

        main_layout.addWidget(settings_panel)
        
        btn_adv = QPushButton("🚀 高级规则 (防误触/应用排除)")
        btn_adv.setCursor(Qt.PointingHandCursor)
        btn_adv.setStyleSheet("QPushButton { background-color: #E5E5EA; color: #1C1C1E; border-radius: 8px; padding: 10px; font-weight: bold; font-size: 13px; } QPushButton:hover { background-color: #D1D1D6; }")
        btn_adv.clicked.connect(self.open_advanced_settings)
        main_layout.addWidget(btn_adv)
        
        main_layout.addStretch()

        preset_layout = QHBoxLayout(); preset_layout.setSpacing(10)
        self.combo_presets = QComboBox()
        self.combo_presets.addItems(list(self.presets.keys())); self.combo_presets.setCurrentText(self.current_preset_name)
        self.combo_presets.currentTextChanged.connect(self.load_selected_preset)
        self.combo_presets.setFocusPolicy(Qt.NoFocus)
        self.combo_presets.setStyleSheet("QComboBox { color: #000; background: white; border-radius: 8px; padding: 5px; }")
        
        btn_save = QPushButton("保存")
        btn_save.setFocusPolicy(Qt.NoFocus); btn_save.setCursor(Qt.PointingHandCursor); btn_save.clicked.connect(self.save_new_preset)
        btn_save.setStyleSheet("QPushButton { background-color: #34C759; color: white; border-radius: 8px; padding: 6px 12px; border:none;}")
        
        btn_del = QPushButton("删除")
        btn_del.setFocusPolicy(Qt.NoFocus); btn_del.setCursor(Qt.PointingHandCursor); btn_del.clicked.connect(self.delete_preset)
        btn_del.setStyleSheet("QPushButton { background-color: #FF3B30; color: white; border-radius: 8px; padding: 6px 12px; border:none;}")
        
        preset_layout.addWidget(self.combo_presets); preset_layout.addWidget(btn_save); preset_layout.addWidget(btn_del)
        main_layout.addLayout(preset_layout)

        footer_link = QLabel()
        footer_link.setAlignment(Qt.AlignCenter); footer_link.setOpenExternalLinks(True)
        footer_link.setText("<a href='https://github.com/AouTzxc/Global-mouse' style='color: #8E8E93; text-decoration: none; font-weight: bold;'>By: 阿呆</a>")
        main_layout.addWidget(footer_link)

    def on_toggle_horizontal_hotkey(self):
        new_state = not cfg.enable_horizontal
        setattr(cfg, 'enable_horizontal', new_state)
        self.ui_widgets["enable_horizontal"].setChecked(new_state)
        if self.tray_icon.isVisible():
            state_str = "已开启 🟢" if new_state else "已关闭 🔴"
            self.tray_icon.showMessage("横向滚动切换", f"横向滚动 {state_str}", QSystemTrayIcon.Information, 1500)

    def open_advanced_settings(self):
        dialog = AdvancedSettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.save_presets_to_file()

    def toggle_autorun(self, checked):
        if not self.autostart.set_autorun(checked):
            self.sender().blockSignals(True); self.sender().setChecked(not checked); self.sender().blockSignals(False)
            QMessageBox.warning(self, "设置失败", "权限不足或路径错误。")

    def save_new_preset(self):
        text, ok = QInputDialog.getText(self, "保存参数", "请输入预设名称:", text=self.current_preset_name)
        if ok and text:
            self.presets[text] = cfg.to_dict(); self.current_preset_name = text; self.save_presets_to_file()
            self.combo_presets.blockSignals(True); self.combo_presets.clear(); self.combo_presets.addItems(list(self.presets.keys()))
            self.combo_presets.setCurrentText(text); self.combo_presets.blockSignals(False)

    def delete_preset(self):
        name = self.combo_presets.currentText()
        if name == "默认": QMessageBox.warning(self, "提示", "默认配置无法删除。"); return
        del self.presets[name]; self.current_preset_name = "默认"; self.save_presets_to_file()
        self.combo_presets.blockSignals(True); self.combo_presets.clear(); self.combo_presets.addItems(list(self.presets.keys()))
        self.combo_presets.setCurrentText("默认"); self.combo_presets.blockSignals(False); self.load_selected_preset("默认")

    def load_selected_preset(self, name):
        if name in self.presets:
            cfg.from_dict(self.presets[name]); self.current_preset_name = name
            self.ui_widgets["sensitivity"].setValue(cfg.sensitivity); self.ui_widgets["speed_factor"].setValue(cfg.speed_factor)
            self.ui_widgets["dead_zone"].setValue(cfg.dead_zone); self.ui_widgets["overlay_size"].setValue(cfg.overlay_size)
            self.ui_widgets["enable_horizontal"].setChecked(cfg.enable_horizontal)
            self.ui_widgets["start_minimized"].setChecked(cfg.start_minimized)
            self.ui_widgets["hotkey_edit"].setKeySequence(QKeySequence(cfg.horizontal_hotkey))
            self.save_presets_to_file()

    def on_show_overlay(self):
        self.overlay.set_direction('neutral')
        self.overlay.move(int(QCursor.pos().x() - cfg.overlay_size / 2), int(QCursor.pos().y() - cfg.overlay_size / 2))
        self.overlay.show(); self.overlay.raise_()
    
    def on_hide_overlay(self):
        self.overlay.hide()

    def start_threads(self):
        try:
            self.window_monitor = WindowMonitor()
            self.window_monitor.start()
        except Exception: pass

        try:
            self.key_manager = KeyboardManager(lambda: self.bridge.toggle_horizontal.emit())
            self.key_manager.start()
        except Exception as e:
            print(f"Keyboard Hook Failed: {e}") 

        # [微软商店过审护盾：捕获无 runFullTrust 权限时的崩溃并弹窗提示]
        try:
            self.listener = mouse.Listener(on_click=self.on_click)
            self.listener.start()
        except Exception as e:
            self.ui_widgets["enable_horizontal"].setChecked(False) 
            QMessageBox.critical(self, "权限不足", "无法启动鼠标拦截服务。\n\n这通常是因为缺少底层挂钩权限。\n如果是在应用商店版中运行，请确保已授予该权限。")
            
        try:
            self.scroller = threading.Thread(target=self.scroll_loop, daemon=True)
            self.scroller.start()
        except Exception: pass

    def is_current_app_allowed(self):
        if cfg.disable_fullscreen and cfg.is_fullscreen: return False
        
        # [新增] 拦截 Windows 桌面
        if cfg.disable_desktop and OS_NAME == "Windows":
            if cfg.current_window_class in ("Progman", "WorkerW"): 
                return False

        if cfg.filter_mode == 0: return True
            
        app_name = cfg.current_window_name.lower()
        if cfg.filter_mode == 1:
            for keyword in cfg.filter_list:
                if keyword.lower() in app_name: return False
            return True
        elif cfg.filter_mode == 2:
            for keyword in cfg.filter_list:
                if keyword.lower() in app_name: return True
            return False
        return True

    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.middle:
            if pressed:
                if not self.is_current_app_allowed(): return
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
                    dx, dy = curr_x - cfg.origin_pos[0], curr_y - cfg.origin_pos[1]
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
                        base_multiplier = 0.0001 if OS_NAME == "Darwin" else 0.00005
                        speed_scalar = math.pow(eff_dist, cfg.sensitivity) * base_multiplier * cfg.speed_factor
                        mouse_controller.scroll((dx / dist) * speed_scalar, (dy / dist) * speed_scalar * -1)
                    time.sleep(0.01)
                except: pass
            else:
                last_dir = 'neutral'
                time.sleep(0.05)

if __name__ == "__main__":
    try:
        # 必须在 QApplication 实例化之前设置高分屏缩放策略
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        
        if OS_NAME == "Windows":
            myappid = 'adai.globalmouse.app.v3' 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        app.setQuitOnLastWindowClosed(False)

        font_name = ".AppleSystemUIFont" if OS_NAME == "Darwin" else "Segoe UI"
        app.setFont(QFont(font_name, 11 if OS_NAME == "Windows" else 13))
        
        window = MainWindow()
        if not cfg.start_minimized: window.show()
        sys.exit(app.exec())
    except Exception as e:
        # [最后一道防线] 发生致命崩溃时，在用户的【文档】目录下生成 crash_log.txt
        import traceback
        log_path = os.path.join(os.path.expanduser("~"), "Documents", "GlobalMouse_Crash_Log.txt")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"Crash Time: {time.ctime()}\n")
                f.write(f"Error: {str(e)}\n")
                f.write(traceback.format_exc())
            ctypes.windll.user32.MessageBoxW(0, f"程序遇到致命错误，日志已保存至:\n{log_path}", "Global Mouse Crash", 16)
        except: pass
        sys.exit(1)