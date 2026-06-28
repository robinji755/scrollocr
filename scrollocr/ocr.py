"""OCR 文本提取模块 - 从拼接图像中提取文本内容。"""

from PIL import Image
import numpy as np
from typing import List
import logging

logger = logging.getLogger(__name__)

# 默认 OCR 配置
DEFAULT_CONFIG = "--psm 6"
DEFAULT_LANG = "chi_sim+eng"


def extract_text(
    image: Image.Image,
    lang: str = DEFAULT_LANG,
    config: str = DEFAULT_CONFIG,
    preprocess: bool = False,
) -> str:
    """从图像中提取文本。

    Args:
        image: PIL Image
        lang: Tesseract 语言包
        config: Tesseract 配置
        preprocess: 是否预处理图像 (二值化、去噪；默认关闭，开启可能降低英文识别率)

    Returns:
        提取的文本
    """
    try:
        import pytesseract
    except ImportError:
        logger.error("pytesseract is required for OCR. Install: pip install pytesseract")
        return ""

    if preprocess:
        image = _preprocess_for_ocr(image)

    text = pytesseract.image_to_string(image, lang=lang, config=config)
    return text.strip()


def extract_text_by_columns(
    image: Image.Image,
    num_columns: int = 1,
    lang: str = DEFAULT_LANG,
    config: str = DEFAULT_CONFIG,
) -> str:
    """按列提取文本，适用于多栏布局。

    Args:
        image: PIL Image
        num_columns: 列数
        lang: Tesseract 语言包
        config: Tesseract 配置

    Returns:
        按阅读顺序排列的文本
    """
    if num_columns <= 1:
        return extract_text(image, lang, config)

    w = image.width
    col_w = w // num_columns
    texts = []
    for i in range(num_columns):
        col_img = image.crop((i * col_w, 0, (i + 1) * col_w, image.height))
        text = extract_text(col_img, lang, config)
        texts.append(text)

    return "\n".join(texts)


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """OCR 预处理：灰度化、二值化、去噪。"""
    import numpy as np

    arr = np.array(img.convert("L"))

    # 自适应二值化
    from PIL import ImageFilter
    blur = Image.fromarray(arr).filter(ImageFilter.MedianFilter(size=3))
    arr = np.array(blur)

    # Otsu 二值化
    threshold = _otsu_threshold(arr)
    binary = (arr > threshold).astype(np.uint8) * 255

    return Image.fromarray(binary)


def _otsu_threshold(arr: np.ndarray) -> int:
    """Otsu 算法计算最佳二值化阈值。"""
    import numpy as np
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = sum(i * hist[i] for i in range(256))

    sum_bg = 0
    w_bg = 0
    max_var = 0
    threshold = 0

    for t in range(256):
        w_bg += hist[t]
        if w_bg == 0:
            continue
        w_fg = total - w_bg
        if w_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / w_bg
        mean_fg = (sum_total - sum_bg) / w_fg
        var = w_bg * w_fg * (mean_bg - mean_fg) ** 2
        if var > max_var:
            max_var = var
            threshold = t

    return threshold


def extract_code_blocks(text: str) -> List[str]:
    """从 OCR 文本中提取代码块（启发式检测缩进和特殊字符）。"""
    import re

    lines = text.split("\n")
    blocks = []
    current_block = []
    in_code = False

    code_patterns = [
        r"^\s{4,}",           # 4+ 空格缩进
        r"^(def |class |import |from |return |if |for |while |with |try |except |raise )",
        r"^(function|const|let|var|async|await|export|module\.)",
        r"^(#|//|/\*|'''|\"\"\")",  # 注释
        r"[{}()\[\]=<>+\-*/%&|^~]",  # 代码符号
    ]

    for line in lines:
        is_code = any(re.match(p, line) for p in code_patterns)
        if is_code:
            current_block.append(line)
            in_code = True
        elif in_code and line.strip() == "":
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = []
            in_code = False
        elif in_code:
            current_block.append(line)
        else:
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = []

    if current_block:
        blocks.append("\n".join(current_block))

    return blocks
