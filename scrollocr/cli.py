"""CLI 入口 - 滚动屏幕内容捕捉命令行工具。

支持两种模式:
  1. GUI 模式 (默认): 启动浮动半透明按钮
  2. CLI 模式: 终端交互/自动捕获
"""

import argparse
import sys
import logging
import os

from .stitch import ScrollCaptureSession
from .ocr import extract_text, extract_code_blocks
from .capture import timestamp

# 默认保存路径: 项目目录下的 scrollocr
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/scrollocr_saved_files")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="滚动屏幕内容抓取工具 — 基于 Glass 技术原理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                        # GUI 模式: 启动浮动按钮
  %(prog)s --cli                  # CLI 交互模式
  %(prog)s --auto --shots 10      # 自动模式
  %(prog)s --gui                  # 显式启动 GUI 模式
        """,
    )

    mode = parser.add_argument_group("模式选项")
    mode.add_argument("--gui", action="store_true", help="启动浮动按钮 GUI 模式 (默认)")
    mode.add_argument("--cli", action="store_true", help="CLI 交互模式 (手动按 Enter 捕获)")
    mode.add_argument("--auto", action="store_true", help="自动捕获模式（固定间隔）")
    mode.add_argument("--shots", type=int, default=5, help="自动模式下的捕获次数 (默认: 5)")
    mode.add_argument("--delay", type=float, default=2.0, help="自动模式下的捕获间隔秒数 (默认: 2.0)")

    output = parser.add_argument_group("输出选项")
    output.add_argument("-o", "--output", help=f"输出图像路径 (默认: {DEFAULT_OUTPUT_DIR}/scroll_capture_<timestamp>.png)")
    output.add_argument("--ocr", action="store_true", help="OCR 提取文本并保存为 .txt 文件")
    output.add_argument("--ocr-lang", default="chi_sim+eng", help="OCR 语言 (默认: chi_sim+eng)")
    output.add_argument("--code-only", action="store_true", help="仅提取代码块")
    output.add_argument("--txt-output", help="OCR 文本输出路径")
    output.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"输出目录 (默认: {DEFAULT_OUTPUT_DIR})")

    algo = parser.add_argument_group("对齐算法")
    algo.add_argument("--strategy", choices=["auto", "pixel", "ssim", "ocr"],
                      default="auto", help="重叠检测策略 (默认: auto)")
    algo.add_argument("--search-region", type=int, default=200,
                      help="重叠搜索区域行数 (默认: 200)")
    algo.add_argument("--min-overlap", type=int, default=10,
                      help="最小重叠行数 (默认: 10)")

    adv = parser.add_argument_group("高级选项")
    adv.add_argument("--quality", type=int, default=80,
                     help="JPEG 压缩质量 1-100 (默认: 80)")
    adv.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 确保输出目录存在
    os.makedirs(args.output_dir, exist_ok=True)

    # 默认模式: GUI (除非指定了 --cli 或 --auto)
    if not args.cli and not args.auto:
        _launch_gui(args)
        return

    # CLI 模式
    _run_cli(args)


def _launch_gui(args):
    """启动 GUI 浮动按钮模式。"""
    try:
        from .gui import launch_gui
        print("启动浮动捕获按钮...")
        print(f"输出目录: {args.output_dir}")
        print("快捷键: [Space] 开始/停止  [Esc] 退出")
        launch_gui(output_dir=args.output_dir)
    except ImportError as e:
        print(f"GUI 模式不可用: {e}")
        print("请确保 tkinter 可用 (Python 内置)")
        sys.exit(1)
    except Exception as e:
        print(f"GUI 错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _run_cli(args):
    """运行 CLI 模式。"""
    session = ScrollCaptureSession(
        strategy=args.strategy,
        quality=args.quality,
        search_region=args.search_region,
        min_overlap=args.min_overlap,
    )

    # 处理输出路径
    if args.output:
        output_path = args.output
    else:
        ts = timestamp()
        output_path = os.path.join(args.output_dir, f"scroll_capture_{ts}.png")

    try:
        if args.auto:
            result = session.run_auto(
                num_shots=args.shots,
                delay=args.delay,
                output_path=output_path,
            )
        else:
            result = session.run_interactive(output_path=output_path)

    except KeyboardInterrupt:
        print("\n\n用户中断")
        if session.frames and len(session.frames) >= 1:
            result = session.stitch()
            result.save(output_path)
            print(f"已保存部分结果: {output_path}")
        return
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if result is None:
        return

    # OCR 提取
    if args.ocr:
        _do_ocr(result, args)


def _do_ocr(image, args):
    """执行 OCR 并保存文本。"""
    print("\n正在 OCR 提取文本...")
    text = extract_text(image, lang=args.ocr_lang)

    if args.code_only:
        blocks = extract_code_blocks(text)
        output_text = "\n\n".join(blocks)
        print(f"  提取了 {len(blocks)} 个代码块")
    else:
        output_text = text

    if args.txt_output:
        txt_path = args.txt_output
    else:
        ts = timestamp()
        txt_path = os.path.join(args.output_dir, f"scroll_capture_{ts}.txt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(output_text)

    # 显示预览
    lines = output_text.split("\n")
    preview_lines = min(20, len(lines))
    print(f"\n文本预览 (前 {preview_lines} 行 / 共 {len(lines)} 行):")
    print("-" * 40)
    for line in lines[:preview_lines]:
        if line.strip():
            print(f"  {line[:80]}")
    print("-" * 40)
    print(f"已保存: {txt_path}")


if __name__ == "__main__":
    main()
