# Changelog

## 0.1.0 (2026-06-28)

### 新增

- **原生 macOS 浮动按钮** (Swift) — 替代 tkinter GUI，解决 macOS 26 兼容性问题
  - 半透明圆形浮动按钮，置顶显示，可拖拽
  - 点击开始/停止截屏，状态反馈（灰 → 红 → 绿）
  - 无边框、透明背景，支持全空间显示
- **CHANGELOG.md** — 版本变更记录

### 修复

- `capture.py`: 移除已废弃的 `screencapture -x` 参数，修复 macOS 26 截屏失败问题
- `gui.py`: 修复 `attributes("-transparent", True)` 语法错误（macOS 应为 `transparentcolor`）
- `gui.py`: 修复 tkinter 在 macOS 26 上的 `overrideredirect` 崩溃问题（改用 withdraw/deiconify 模式）

### 技术变更

- GUI 层从 tkinter 迁移至原生 Swift (`gui_app/`)
- 新增 `gui_app/main.swift` — Swift 浮动按钮源码
- 新增 `gui_app/FloatingButton` — 预编译 arm64 二进制
- 更新 `~/.zshrc` 别名：`scrollocr` 指向原生浮动按钮
- 新增 `.gitignore`
