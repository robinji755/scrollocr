"""屏幕捕获模块 - 基于 Glass 项目的 screencapture 技术。"""

import os
import subprocess
import tempfile
from datetime import datetime
from PIL import Image
import io


def capture_screen(output_path: str | None = None, format: str = "jpg") -> Image.Image:
    """捕获当前屏幕内容。

    基于 Glass 项目的 screencapture 技术 (macOS)，
    回退到 Pillow ImageGrab (跨平台)。

    Args:
        output_path: 保存路径，None 则返回 PIL Image
        format: 图片格式 (jpg/png)

    Returns:
        PIL Image 对象
    """
    if os.uname().sysname == "Darwin":
        return _capture_macos(output_path, format)
    else:
        return _capture_pillow(output_path, format)


def _capture_macos(output_path: str | None = None, fmt: str = "jpg") -> Image.Image:
    """macOS 下使用 screencapture 命令截屏 (Glass 项目核心技术)。"""
    tmp_path = None
    if output_path is None:
        fd, tmp_path = tempfile.mkstemp(suffix=f".{fmt}")
        os.close(fd)
        save_path = tmp_path
    else:
        save_path = output_path

    try:
        subprocess.run(
            ["screencapture", "-x", "-t", fmt, save_path],
            check=True, capture_output=True, timeout=10,
        )
        img = Image.open(save_path)
        img.load()  # 确保文件可关闭
        return img
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _capture_pillow(output_path: str | None = None, fmt: str = "jpg") -> Image.Image:
    """跨平台回退方案：使用 Pillow ImageGrab。"""
    from PIL import ImageGrab
    img = ImageGrab.grab()
    if output_path:
        img.save(output_path, format=fmt.upper())
    return img


def capture_screen_region(region: tuple[int, int, int, int] | None = None) -> Image.Image:
    """捕获屏幕指定区域。

    Args:
        region: (left, top, right, bottom) 坐标元组，None 则全屏
    """
    img = capture_screen()
    if region:
        img = img.crop(region)
    return img


def compress_image(img: Image.Image, quality: int = 80, max_height: int | None = None) -> Image.Image:
    """压缩图片 (基于 Glass 项目的 sharp 处理逻辑)。

    Args:
        img: 输入 PIL Image
        quality: JPEG 质量 (1-100)
        max_height: 最大高度，超此值等比缩放
    """
    if max_height and img.height > max_height:
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, max_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf)


def timestamp() -> str:
    """生成时间戳字符串。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
