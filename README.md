# ScrollOCR

基于 [pickle-com/glass](https://github.com/pickle-com/glass) 技术原理的滚动屏幕内容抓取 + OCR 文字识别工具。

## 核心功能

- **浮动按钮 GUI** (原生 macOS) — 半透明悬浮圆形按钮，点击即录，类似 Glass 的浮动窗口设计
- **滚动截屏** — 连续捕获屏幕内容，支持自动去重对齐
- **图像拼接** — 将所有非重叠区域拼接为完整长图
- **OCR 文本提取** — 可选从拼接结果中提取文本内容

## 技术原理

### 从 Glass 项目继承的核心技术

| Glass 技术 | 本工具实现 |
|-----------|-----------|
| `screencapture -t jpg` macOS 截屏 | 相同命令，支持全屏截取 |
| `sharp` 图像缩放+JPEG压缩 | Pillow 等效处理 |
| 浮动无边框窗口 (`frame: false`, `transparent: true`, `alwaysOnTop: true`) | Swift `borderless` + `clear` background + `.floating` level |
| 多模态 AI 视觉分析 | 扩展为多帧去重拼接管线 |

### 自研核心算法：全重叠区域 MSE 最小化

```
prev_img (rows [A, A+h]) ──── curr_img (rows [A+S, A+S+h])
                                    │
                    ┌───────────────┴───────────────┐
                    │ 重叠区域 (h-S 行)              │
                    │ curr[0 : h-S] == prev[S : h]  │
                    │ MSE → 0                       │
                    │                               │
                    │ 新增区域 (S 行)                │
                    │ curr[h-S : h] = 新内容         │
                    └───────────────────────────────┘
```

## 快速开始

### 前提

- macOS (需授予终端**屏幕录制权限**)
- Python 3.10+
- 依赖：`pip install pillow numpy`
- 可选：`pip install pytesseract scikit-image`

### GUI 模式 (推荐)

```bash
scrollocr
```

启动后会在屏幕顶部出现一个**半透明圆形浮动按钮**：

| 状态 | 外观 | 操作 |
|------|------|------|
| 🟤 空闲 | 灰色圆形 + ● 图标 | 点击 → 开始捕获 |
| 🔴 录制中 | 红色按钮 | 点击 → 停止并保存 |
| 🟢 完成 | 绿色 ✓ + 帧数 | 自动 3 秒后回到空闲 |

**操作：**
- **点击** — 开始/停止捕获
- **拖拽** — 按住按钮任意位置拖动
- **输出文件：** 自动保存到 `scrollocr/scroll_capture_<timestamp>.png`

### CLI 交互模式

```bash
scrollocr-cli
```

手动按 Enter 逐帧捕获，支持删除上一帧、查看已捕获帧数。

### 自动模式

```bash
scrollocr-auto
```

自动捕获 10 帧，间隔 2 秒。

### 直接运行 (不通过别名)

```bash
cd /Users/robin/iapp/ipkgs/Pymodelverse
python3 -m scrollocr.cli                        # GUI 模式
python3 -m scrollocr.cli --cli                  # CLI 交互模式
python3 -m scrollocr.cli --auto --shots 10      # 自动模式
```

### OCR 文本提取

```bash
python3 -m scrollocr.cli --cli --ocr --ocr-lang eng
python3 -m scrollocr.cli --cli --ocr --code-only
```

## 项目结构

```
scrollocr/
├── gui_app/
│   ├── main.swift           # 原生 macOS 浮动按钮源码
│   └── FloatingButton       # 预编译 arm64 二进制
├── __init__.py              # 包信息
├── capture.py               # 屏幕捕获模块 (基于 Glass screencapture)
├── align.py                 # 重叠检测算法 (MSE 最小化)
├── stitch.py                # 帧管理与拼接
├── ocr.py                   # OCR 文本提取
├── gui.py                   # (已弃用) tkinter GUI — macOS 26 不兼容
├── cli.py                   # CLI/GUI 入口
├── pyproject.toml           # 包配置
├── CHANGELOG.md             # 版本变更记录
└── README.md                # 本文档
```

## 与 Glass 的对比

| 特性 | Glass (原版) | 本工具 |
|------|-------------|--------|
| 屏幕捕获 | `screencapture` + `desktopCapturer` | ✅ `screencapture` |
| 浮动 UI | Electron BrowserWindow (353x47) | ✅ Swift 圆形按钮 (64x64) |
| 无边框透明 | `frame: false` + `transparent: true` | ✅ `borderless` + `clear` background |
| 置顶显示 | `alwaysOnTop: true` | ✅ `.floating` level |
| 可拖拽 | `moved` event + `animateWindowPosition` | ✅ `isMovableByWindowBackground` |
| 滚动去重 | ❌ 无 (单帧 AI 分析) | ✅ MSE 全重叠匹配 |
| 图像拼接 | ❌ 无 | ✅ 多帧自动拼接 |
| AI 多模态 | ✅ GPT-4V / Gemini Vision | ❌ 不依赖 LLM |
| 会议摘要 | ✅ STT + LLM | ❌ 不包含 |
| OCR 文本 | ❌ 无 | ✅ Tesseract (可选) |
