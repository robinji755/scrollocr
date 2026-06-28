"""图像对齐与重叠检测模块 - 滚动截屏去重核心算法。

核心方法：全重叠区域 MSE (均方误差) 最小化。

原理：
  当用户向下滚动 S 像素时：
    - prev_img: 页面 rows [A, A+h]
    - curr_img: 页面 rows [A+S, A+S+h]
    - 重叠区域: curr_img[0:h-S] == prev_img[S:h]  (像素完全相同)
  
  我们遍历所有可能的 S 值 (1 ~ max_scroll)，找到使
    MSE(curr_img[0:h-S], prev_img[S:h])
  最小的 S，即为实际滚动量。

  这比局部模板匹配更鲁棒，因为利用了所有重叠像素进行验证。

支持三种策略:
1. pixel: 全重叠 MSE 最小化 (默认，最鲁棒)
2. ssim: 结构相似性匹配 (备选)
3. ocr: OCR 文本行匹配 (内容级去重，较慢)
"""

import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def find_overlap(
    prev_img: Image.Image,
    curr_img: Image.Image,
    strategy: str = "pixel",
    search_region: int = 200,
    min_overlap: int = 10,
) -> "tuple[int, float]":
    """检测两张连续截图的重叠行数。

    使用全重叠区域 MSE 最小化算法，找到 curr_img 中
    与 prev_img 重复的行数。

    Args:
        prev_img: 上一张截图
        curr_img: 当前截图
        strategy: 匹配策略 - "pixel" | "ssim" | "ocr"
        search_region: 最大搜索范围 (行数)
        min_overlap: 最小重叠行数，低于此值视为无重叠

    Returns:
        重叠的行数 (应从 curr_img 顶部裁剪的行数)
    """
    if strategy == "ssim":
        return _find_overlap_ssim(prev_img, curr_img, search_region, min_overlap)
    elif strategy == "ocr":
        return _find_overlap_ocr(prev_img, curr_img, search_region, min_overlap)
    else:
        return _find_overlap_pixel(prev_img, curr_img, search_region, min_overlap)  # returns (overlap, mse)


def _find_overlap_pixel(
    prev_img: Image.Image, curr_img: Image.Image,
    search_region: int = 200, min_overlap: int = 10,
) -> int:
    """全重叠区域 MSE 最小化算法。

    算法步骤:
    1. 对每个候选滚动量 S (1 ~ search_region):
       - 取 curr_img[0 : h-S] 和 prev_img[S : h]
       - 计算两者 MSE
    2. 找到 MSE 最小的 S
    3. 重叠行数 = h - S

    Why this works:
    当用户向下滚动 S 像素时，curr_img 中前 h-S 行的内容
    与 prev_img 中从 S 行开始的内容完全相同。
    MSE 在正确的 S 处会趋近于 0。

    Complexity: O(search_region * h * w) ≈ 200*600*800 ≈ 96M ops
    实际运行速度很快 (毫秒级)。
    """
    prev_arr = np.array(prev_img.convert("L"), dtype=np.float64)
    curr_arr = np.array(curr_img.convert("L"), dtype=np.float64)

    h = prev_img.height
    max_scroll = min(search_region, h - min_overlap)

    if max_scroll < 1:
        return 0

    best_S = 0
    best_mse = float("inf")

    for S in range(1, max_scroll + 1):
        overlap_h = h - S
        if overlap_h < 1:
            break

        diff = curr_arr[:overlap_h, :] - prev_arr[S:, :]
        mse = np.mean(diff ** 2)

        if mse < best_mse:
            best_mse = mse
            best_S = S

    # 如果最小 MSE 仍较大，可能没有重叠或内容变化过大
    if best_mse > 50.0:
        logger.debug(f"MSE={best_mse:.2f} > 50, no reliable overlap detected")
        return (0, best_mse)

    overlap_rows = h - best_S
    logger.debug(
        f"Overlap: scroll_S={best_S}, overlap={overlap_rows}px, "
        f"mse={best_mse:.4f}"
    )

    if overlap_rows < min_overlap or overlap_rows >= h:
        return (0, best_mse)

    return (max(0, overlap_rows), best_mse)


def _find_overlap_ssim(
    prev_img: Image.Image, curr_img: Image.Image,
    search_region: int = 200, min_overlap: int = 10,
) -> int:
    """基于结构相似性 (SSIM) 的匹配。

    对光照变化、微小位移更鲁棒。
    需要 scikit-image 库。
    """
    try:
        from skimage.metrics import structural_similarity as ssim  # type: ignore  # optional dep
    except ImportError:
        logger.warning("scikit-image not installed, falling back to pixel strategy")
        return _find_overlap_pixel(prev_img, curr_img, search_region, min_overlap)  # returns (overlap, mse)

    prev_arr = np.array(prev_img.convert("L"), dtype=np.float64)
    curr_arr = np.array(curr_img.convert("L"), dtype=np.float64)

    h = prev_img.height
    max_scroll = min(search_region, h - min_overlap)

    if max_scroll < 1:
        return 0

    best_S = 0
    best_score = -1.0

    for S in range(1, max_scroll + 1):
        overlap_h = h - S
        if overlap_h < 1:
            break

        try:
            score = ssim(curr_arr[:overlap_h, :], prev_arr[S:, :], data_range=255)
            if score > best_score:
                best_score = score
                best_S = S
        except ValueError:
            continue

    if best_score < 0.5:
        return (0, best_score)

    overlap_rows = h - best_S
    if overlap_rows < min_overlap or overlap_rows >= h:
        return (0, best_score)
    return (max(0, overlap_rows), best_score)


def _find_overlap_ocr(
    prev_img: Image.Image, curr_img: Image.Image,
    search_region: int = 200, min_overlap: int = 10,
) -> int:
    """基于 OCR 文本行匹配的内容级去重。

    适合纯文本/代码内容，对格式变化不敏感但速度较慢。
    作为 pixel/ssim 的补充。
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed, falling back to pixel strategy")
        return _find_overlap_pixel(prev_img, curr_img, search_region, min_overlap)  # returns (overlap, mse)  # returns (overlap, mse)

    config = "--psm 6 -l chi_sim+eng"

    prev_bottom = prev_img.crop((
        0, max(0, prev_img.height - search_region),
        prev_img.width, prev_img.height,
    ))
    prev_text = pytesseract.image_to_string(prev_bottom, config=config)

    curr_top = curr_img.crop((
        0, 0, curr_img.width,
        min(search_region, curr_img.height),
    ))
    curr_text = pytesseract.image_to_string(curr_top, config=config)

    prev_lines = [line.strip() for line in prev_text.split("\n") if line.strip()]
    curr_lines = [line.strip() for line in curr_text.split("\n") if line.strip()]

    if not prev_lines or not curr_lines:
        return 0

    # 找最长公共子串 (从 prev 底部匹配 curr 顶部)
    max_match = 0
    for i in range(len(prev_lines)):
        for j in range(len(curr_lines)):
            k = 0
            while (i + k < len(prev_lines) and j + k < len(curr_lines)
                   and prev_lines[i + k] == curr_lines[j + k]):
                k += 1
            if k > max_match:
                max_match = k

    if max_match == 0:
        return 0

    avg_line_h = search_region / max(len(prev_lines), 1)
    overlap_px = int(max_match * avg_line_h)

    if overlap_px < min_overlap:
        return (0, 0)
    return (overlap_px, 0)


def auto_detect_strategy(prev_img: Image.Image, curr_img: Image.Image) -> str:
    """自动检测最佳匹配策略。

    目前 pixel (MSE) 策略已足够鲁棒，默认返回 "pixel"。
    当检测到大量纯色区域时仍使用 pixel。
    """
    arr = np.array(prev_img.convert("L"))
    # 如果图像几乎纯色 (std 很小)，MSE 可能不可靠
    if arr.std() < 5:
        return "ssim"
    return "pixel"
