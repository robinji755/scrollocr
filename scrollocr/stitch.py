"""内容拼接模块 - 将多张截图拼接为完整图像并提取文本。"""

from PIL import Image
from typing import List, Tuple, Optional
import logging

from .capture import capture_screen, timestamp, compress_image
from .align import find_overlap, auto_detect_strategy

logger = logging.getLogger(__name__)


class ScrollCaptureSession:
    """滚动截屏会话管理。

    管理连续截屏 → 去重对齐 → 拼接 → 输出的完整流程。

    基于 Glass 项目的 screencapture + sharp 图像处理管线，
    扩展为支持多帧滚动捕捉与自动去重。
    """

    def __init__(
        self,
        strategy: str = "auto",
        quality: int = 80,
        search_region: int = 150,
        min_overlap: int = 10,
        capture_interval: float = 0.5,
    ):
        """
        Args:
            strategy: 对齐策略 "auto" | "pixel" | "ssim" | "ocr"
            quality: JPEG 压缩质量
            search_region: 重叠搜索区域 (像素行数)
            min_overlap: 最小重叠行数
            capture_interval: 连续捕获间隔 (秒)
        """
        self.strategy = strategy
        self.quality = quality
        self.search_region = search_region
        self.min_overlap = min_overlap
        self.capture_interval = capture_interval
        self.frames: List[Image.Image] = []
        self.overlaps: List[int] = []
        self._running = False

    def capture_frame(self) -> Image.Image:
        """捕获一帧屏幕内容。"""
        img = capture_screen()
        return compress_image(img, quality=self.quality)

    def add_frame(self, frame: Image.Image) -> Tuple[int, int, float]:
        """添加一帧并检测与上一帧的重叠。

        重叠检测算法:
        - 取 frame (curr) 顶部 30 行作为"探针"
        - 在上一帧 (prev) 中搜索探针的最佳匹配位置
        - 匹配位置 = 滚动偏移量 (scroll_offset)
        - 重叠行数 = frame.height - scroll_offset
        - 新增行数 = scroll_offset

        Returns:
            (overlap_rows, unique_rows)
            - overlap_rows: curr 中与 prev 重复的行数 (应从顶部裁剪)
            - unique_rows: curr 中新增的行数 (应保留)
        """
        if not self.frames:
            self.frames.append(frame)
            return (0, frame.height, 0.0)

        prev = self.frames[-1]
        strategy = self.strategy
        if strategy == "auto":
            strategy = auto_detect_strategy(prev, frame)

        overlap, quality = find_overlap(
            prev, frame, strategy,
            self.search_region, self.min_overlap,
        )

        self.overlaps.append(overlap)
        self.frames.append(frame)

        unique = frame.height - overlap
        logger.info(
            f"Frame {len(self.frames)}: overlap={overlap}px, "
            f"new={unique}px, quality={quality:.2f} (strategy={strategy})"
        )
        return (overlap, max(0, unique), quality)

    def stitch(self) -> Image.Image:
        """将所有帧拼接为完整图像。

        算法:
        1. 第一帧全部保留
        2. 后续帧裁剪掉与上一帧重叠的部分 (从顶部裁剪)
        3. 垂直拼接所有非重叠条带
        """
        if not self.frames:
            raise ValueError("No frames to stitch")

        if len(self.frames) == 1:
            return self.frames[0]

        strips = [self.frames[0]]
        for i in range(1, len(self.frames)):
            overlap = self.overlaps[i - 1]
            frame = self.frames[i]
            h, w = frame.height, frame.width

            if overlap <= 0:
                # 无重叠：整帧保留
                strips.append(frame)
            elif overlap >= h:
                # 完全重叠：跳过此帧
                logger.warning(f"Frame {i+1} fully overlaps previous, skipping")
                continue
            else:
                # 部分重叠：裁剪掉重叠部分（顶部），保留新增部分（底部）
                # overlap 行在顶部是重复的，保留 [overlap:h] 的新内容
                strip = frame.crop((0, overlap, w, h))
                strips.append(strip)

        # 垂直拼接
        total_height = sum(s.height for s in strips)
        max_width = max(s.width for s in strips)
        result = Image.new("RGB", (max_width, total_height), (255, 255, 255))

        y_offset = 0
        for strip in strips:
            result.paste(strip, (0, y_offset))
            y_offset += strip.height

        logger.info(f"Stitched {len(strips)} strips → {result.width}x{result.height}")
        return result

    def run_interactive(self, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """交互式运行：按 Enter 捕获，输入 q 退出。

        Args:
            output_path: 拼接结果保存路径

        Returns:
            拼接后的完整图像，无帧时返回 None
        """
        print("=" * 58)
        print("  📸 滚动屏幕内容捕捉工具")
        print("  基于 Glass 技术原理 — screencapture + 自动对齐去重")
        print("=" * 58)
        print()
        print("操作说明:")
        print("  [Enter]  捕获当前屏幕 (滚动后按此键捕获新内容)")
        print("  [d]      删除上一帧")
        print("  [s]      显示已捕获帧数")
        print("  [q]      完成捕捉并拼接输出")
        print()

        frame_count = 0
        while True:
            try:
                cmd = input(f"[帧 {frame_count}] 操作 [Enter/d/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if cmd == "q":
                break
            elif cmd == "d":
                if self.frames:
                    removed = self.frames.pop()
                    if self.overlaps:
                        self.overlaps.pop()
                    frame_count -= 1
                    print(f"  ✓ 已删除上一帧 ({removed.width}x{removed.height})")
                else:
                    print("  ! 没有可删除的帧")
                continue
            elif cmd == "s":
                print(f"  已捕获: {len(self.frames)} 帧")
                total_unique = self.frames[0].height if self.frames else 0
                for i, f in enumerate(self.frames):
                    info = f"{f.width}x{f.height}"
                    if i > 0 and i - 1 < len(self.overlaps):
                        info += f" (重叠={self.overlaps[i-1]}px)"
                        total_unique += f.height - self.overlaps[i - 1]
                    print(f"    帧 {i+1}: {info}")
                print(f"  预估总高度: ~{total_unique}px")
                continue
            elif cmd != "":
                continue

            # 捕获
            frame = self.capture_frame()
            overlap, unique, _quality = self.add_frame(frame)
            frame_count += 1
            print(f"  ✓ 帧 {frame_count}: {frame.width}x{frame.height}"
                  f" | 重叠: {overlap}px | 新增: {unique}px")

        if not self.frames:
            print("未捕获任何帧")
            return None

        # 拼接
        print(f"\n⏳ 正在拼接 {len(self.frames)} 帧...")
        result = self.stitch()

        if output_path is None:
            output_path = f"scroll_capture_{timestamp()}.png"
        result.save(output_path)
        print(f"✅ 已保存: {output_path} ({result.width}x{result.height})")

        return result

    def run_auto(
        self, num_shots: int = 5, delay: float = 2.0,
        output_path: Optional[str] = None,
    ) -> Optional[Image.Image]:
        """自动模式：按固定间隔连续捕获。

        Args:
            num_shots: 捕获次数
            delay: 每次捕获间隔 (秒)
            output_path: 输出路径
        """
        import time as _time

        print(f"🔄 自动捕获模式: {num_shots} 次, 间隔 {delay}s")
        print("请切换到目标窗口...")
        for i in range(3, 0, -1):
            print(f"  {i}...")
            _time.sleep(1)

        for i in range(num_shots):
            _time.sleep(delay)
            frame = self.capture_frame()
            overlap, unique, _quality = self.add_frame(frame)
            print(f"  ✓ 帧 {i+1}/{num_shots}: {frame.width}x{frame.height}"
                  f" | 重叠: {overlap}px | 新增: {unique}px")

        if not self.frames:
            print("未捕获任何帧")
            return None

        result = self.stitch()
        if output_path is None:
            output_path = f"scroll_capture_auto_{timestamp()}.png"
        result.save(output_path)
        print(f"✅ 已保存: {output_path} ({result.width}x{result.height})")
        return result
