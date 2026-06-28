"""scrollocr - 基于 Glass 技术原理的滚动屏幕内容抓取工具。

从 pickle-com/glass 项目获取的核心技术:
- macOS: screencapture 命令行截屏
- 图像处理: 缩放 + JPEG 压缩
- 多模态 AI 视觉分析

本工具扩展实现:
- 连续滚动截屏 + 自动重叠检测与去重
- 多算法图像对齐 (像素匹配 / SSIM / OCR)
- 内容拼接与文件输出
"""

__version__ = "0.1.0"
