<div align="center">
  <img src="logo.png" alt="Global Mouse Logo" width="120" height="120">
  <h1>🖱️ Global Mouse (全局平滑滚动)</h1>
  <p>一个极其轻量、跨平台且高度可定制的系统级鼠标中键平滑滚动增强工具。</p>
  
  [![Release](https://img.shields.io/github/v/release/AouTzxc/Global-mouse?color=success&style=flat-square)](https://github.com/AouTzxc/Global-mouse/releases)
  [![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-blue?style=flat-square)](#)
  [![Build Status](https://img.shields.io/github/actions/workflow/status/AouTzxc/Global-mouse/release.yml?style=flat-square)](https://github.com/AouTzxc/Global-mouse/actions)
</div>

---

## 🌟 为什么需要 Global Mouse？
很多专业软件或网页不支持鼠标中键按下后的“惯性平滑滚动”，或者原生的滚动极其生硬。
**Global Mouse** 能够在系统底层接管鼠标中键，为你带来如丝般顺滑的全局多向滚动体验。彻底解放你的食指，提升浏览长文档、写代码、看网页的效率！

## ✨ 核心特性

- **🚀 极致平滑 & 全局生效**：基于底层输入拦截，无论什么软件都能享受丝滑的惯性滚动。
- **⚙️ 曲线级自定义**：支持精细调节“加速度曲线”、“基础速度”、“中心死区”等硬核参数。
- **🎮 智能防误触 (游戏模式)**：
  - **全屏禁用**：看电影、打游戏全屏时自动挂起，绝不干扰正常操作。
  - **黑/白名单过滤**：支持指定特定软件（如 CAD、Blender、LOL 等）自动屏蔽此功能。
- **⌨️ 独立快捷键设定**：为横向滚动等高频功能绑定全局快捷键，一键秒切。
- **💾 多场景预设**：你可以为“办公”、“冲浪”、“设计”保存不同的滚动参数预设，随时无缝切换。
- **🖥️ 完美适配 4K 高分屏**：原生支持 Windows 高 DPI 缩放，UI 清晰锐利，绝不偏移。
- **⚡ 超轻量级**：使用 Nuitka 编译为底层 C/C++ 机器码，无黑框运行，极低内存占用，绿色免安装。

---

## 📥 下载与运行

本程序完全免费、开源，且**无需安装任何 Python 环境**，开箱即用。

1. 前往右侧的 [Releases 页面](https://github.com/AouTzxc/Global-mouse/releases)。
2. 找到最新的版本（Latest）。
3. 根据你的操作系统下载对应的包：
   - **Windows 用户**: 下载 `Global_Mouse_Win.exe`，双击直接运行。
   - **macOS 用户**: 下载 `Global_Mouse_Mac.zip`，解压后运行。
4. 程序启动后会隐藏在右下角**系统托盘**（Windows）或**状态栏**（macOS）中，点击图标即可打开设置面板。

---
```
## 🛠️ 进阶使用技巧
```
### 1. 什么是中心死区？
当你在屏幕上按下中键时，会产生一个虚拟的中心点。鼠标移动超出这个“死区”的范围后，页面才会开始滚动。调大死区可以防止手抖造成的误触。

### 2. 如何设置黑名单防误触？
点击主界面的 **“🚀 高级规则”** 按钮。
- 勾选“在所有全屏程序中自动禁用”（玩游戏必备）。
- 选择“黑名单模式”，并在下方输入框填入软件名称的关键词（如 `League of Legends` 或 `Photoshop`），每行一个。保存后，在这些软件内按下中键将执行系统原生操作。

---
## 👨‍💻 开发者指南 (从源码构建)

如果你想自己修改代码并编译，本项目采用了最现代化的工具链：基于 `uv` 的极速环境管理和 `Nuitka` 编译。

---

**1. 克隆项目与环境准备**
```bash
git clone [https://github.com/AouTzxc/Global-mouse.git](https://github.com/AouTzxc/Global-mouse.git)
cd Global-mouse

---

# 使用 uv 极速同步环境依赖
uv sync
---
2. 本地运行测试
```bash
uv run main.py
---
3. CI/CD 自动化构建
本项目已配置完整的 GitHub Actions 工作流。只需向主分支推送一个带有 v*.*.* 格式的 Tag，云端双平台服务器即可全自动编译打包并发布 Release！

---
```
### 🤝 贡献与反馈
如果你发现了 Bug，请提交 Issue。

如果你有好的想法，欢迎提交 Pull Request。

### 👤 作者 (Author)
Global Mouse made with ❤️ by 阿呆
Github: @AouTzxc

### 📄 许可证 (License)
本项目采用 MIT 许可证。
---

## ☕ 支持作者 (Support)

<p align="center">
    <b>如果觉得这个工具好用，不妨请作者喝杯咖啡，这将鼓励我继续维护和开发！</b>
    <br>
    <i>If you find this tool useful, consider buying me a coffee to support maintenance and development!</i>
</p>

<p align="center">
    <img src="screenshots/qr.jpg" width="250" alt="Donate QR Code" style="border-radius: 10px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);">
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Thanks-感谢支持-ff69b4.svg?style=flat-square&logo=github&logoColor=white" alt="Thanks">
</p>
