"""浮动按钮 GUI 模块 — 类似 Glass 的悬浮半透明捕获按钮。

基于 Glass 项目的窗口设计理念：
  - frame: false          -> overrredirect(True)  无边框
  - transparent: true     -> attributes(-transparent)  透明背景
  - alwaysOnTop: true     -> attributes(-topmost)  置顶
  - 可拖动 reposition     -> bind <Button-1> + <B1-Motion>

交互流程：
  [空闲态] 灰色按钮 -> 点击 -> 开始捕获
  [捕获态] 红色脉冲 + 帧数 -> 滚动浏览内容 -> 自动检测底部/手动点击停止
  [完成态] 绿色勾 + 行数 -> OCR 完成 -> 5秒后回到空闲

默认输出: .txt 文本文件 (OCR 提取屏幕文字内容)
"""

import tkinter as tk
import threading
import time
import os
import logging
from datetime import datetime

from .capture import capture_screen, compress_image
from .stitch import ScrollCaptureSession
from .ocr import extract_text

logger = logging.getLogger(__name__)

# 默认保存路径: ~/scrollocr_saved_files (独立存储，不与代码混淆)
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/scrollocr_saved_files")
os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)


class FloatingCaptureButton:
    """浮动半透明捕获按钮。

    类似 Glass header window 的浮动 UI：
    - 无边框、透明背景、置顶显示
    - 可拖拽 reposition
    - 点击切换 空闲/捕获 状态
    - 自动检测滚动到底部并停止
    - 默认输出为 .txt 文本文件 (OCR 提取)
    """

    BUTTON_SIZE = 64
    PADDING = 8

    COLORS = {
        # idle - semi-transparent grey
        "idle_bg": "#444444",
        "idle_fg": "#ffffff",
        "idle_hover": "#555555",
        # working - semi-transparent blue (capturing + OCR OK)
        "working_bg": "#2266cc",
        "working_fg": "#ffffff",
        "working_hover": "#3377dd",
        # warning - semi-transparent red (scroll too fast / alignment failed)
        "warning_bg": "#cc3333",
        "warning_fg": "#ffffff",
        "warning_hover": "#dd4444",
        # complete - green confirmation
        "complete_bg": "#33aa33",
        "complete_fg": "#ffffff",
    }

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR):
        self.output_dir = output_dir
        self.session = None
        self.is_recording = False
        self.frame_count = 0
        self._capture_thread = None
        self._stop_capture = False
        self._pulse_id = None
        self._consecutive_no_new = 0  # 连续无新内容的帧数
        self._last_text_path = None   # 上次保存的文本路径

        # 创建窗口 (macOS 需要先 withdraw 再设置 overrideredirect)
        self.root = tk.Tk()
        self.root.title("Scroll Capture")
        self.root.withdraw()  # 先隐藏，避免 macOS 菜单栏崩溃
        self.root.overrideredirect(True)  # 无边框 (Glass: frame: false)
        self.root.attributes("-topmost", True)  # 置顶 (Glass: alwaysOnTop: true)
        self.root.wm_attributes("-transparentcolor", "grey")  # 透明背景 (Glass: transparent: true, macOS: transparentcolor)
        self.root.configure(bg="grey")
        self.root.wm_attributes("-alpha", 0.88)  # 半透明
        self.root.deiconify()  # 重新显示

        # 窗口置中于屏幕顶部
        screen_w = self.root.winfo_screenwidth()
        x = (screen_w - self.BUTTON_SIZE) // 2
        y = 40
        self.root.geometry(f"{self.BUTTON_SIZE}x{self.BUTTON_SIZE}+{x}+{y}")

        # 创建圆形画布按钮
        self.canvas = tk.Canvas(
            self.root,
            width=self.BUTTON_SIZE,
            height=self.BUTTON_SIZE,
            bg="grey",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()

        # 绘制初始状态
        self._draw_idle()

        # 绑定事件
        self.canvas.tag_bind("btn", "<Button-1>", self._on_click)
        self.canvas.tag_bind("btn", "<Enter>", self._on_enter)
        self.canvas.tag_bind("btn", "<Leave>", self._on_leave)

        # 右键菜单 (退出)
        self._menu = tk.Menu(self.root, tearoff=0, bg="#333333", fg="white",
                             activebackground="#555555", activeforeground="white",
                             font=("Helvetica", 12))
        self._menu.add_command(label="退出", command=self._stop_and_quit)
        self.root.bind("<Button-3>", self._show_context_menu)

        # 拖拽支持
        self.canvas.tag_bind("btn", "<ButtonRelease-1>", self._on_drag_start)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)

        # 键盘快捷键
        self.root.bind("<Escape>", lambda e: self._stop_and_quit())
        self.root.bind("<space>", lambda e: self._toggle_capture())

        self._drag_data = {"x": 0, "y": 0}
        self._is_dragging = False

    # ── 绘制 ──────────────────────────────────────

    def _draw_idle(self):
        """绘制空闲态按钮。"""
        self.canvas.delete("all")
        s = self.BUTTON_SIZE
        r = s // 2 - self.PADDING
        cx, cy = s // 2, s // 2

        # 外圈光晕
        self.canvas.create_oval(
            cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
            fill="", outline="#666666", width=1, tags="btn",
        )
        # 主圆形
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.COLORS["idle_bg"], outline="#666666", width=1, tags="btn",
        )
        # 录制图标 (圆形)
        inner_r = r // 3
        self.canvas.create_oval(
            cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
            fill=self.COLORS["idle_fg"], outline="", tags="btn",
        )
        # 文字标签
        self.canvas.create_text(
            cx, cy + r + 14,
            text="点击录制", fill="#999999",
            font=("Helvetica", 9), tags="btn",
        )
        self.status = "idle"

    def _draw_working(self):
        """Draw working state (blue) - capture/OCR in progress."""
        self.canvas.delete("all")
        s = self.BUTTON_SIZE
        r = s // 2 - self.PADDING
        cx, cy = s // 2, s // 2

        pulse_r = r + 4 + int(4 * __import__("math").sin(time.time() * 3))
        self.canvas.create_oval(
            cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r,
            fill="", outline="#2266cc", width=2, tags="btn",
        )
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.COLORS["working_bg"], outline="#4488ee", width=2, tags="btn",
        )
        inner_r = r // 3
        self.canvas.create_oval(
            cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
            fill=self.COLORS["working_fg"], outline="", tags="btn",
        )
        self.canvas.create_text(
            cx, cy + r + 14,
            text=f"{self.frame_count} frame", fill="#4488ee",
            font=("Helvetica", 9, "bold"), tags="btn",
        )
        self.status = "working"

    def _draw_warning(self):
        """Draw warning state (red) - scroll too fast / alignment failed."""
        self.canvas.delete("all")
        s = self.BUTTON_SIZE
        r = s // 2 - self.PADDING
        cx, cy = s // 2, s // 2

        pulse_r = r + 4 + int(6 * __import__("math").sin(time.time() * 5))
        self.canvas.create_oval(
            cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r,
            fill="", outline="#cc3333", width=2, tags="btn",
        )
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.COLORS["warning_bg"], outline="#ff4444", width=2, tags="btn",
        )
        self.canvas.create_text(
            cx, cy, text="!", fill="white",
            font=("Helvetica", 20, "bold"), tags="btn",
        )
        self.canvas.create_text(
            cx, cy + r + 14,
            text="too fast", fill="#cc3333",
            font=("Helvetica", 8, "bold"), tags="btn",
        )
        self.status = "warning"

    def _draw_recording(self):
        """绘制捕获态按钮 (红色脉冲 + 帧数)。"""
        self.canvas.delete("all")
        s = self.BUTTON_SIZE
        r = s // 2 - self.PADDING
        cx, cy = s // 2, s // 2

        # 脉冲外圈
        pulse_r = r + 4 + int(4 * __import__("math").sin(time.time() * 4))
        self.canvas.create_oval(
            cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r,
            fill="", outline="#cc3333", width=2, tags="btn",
        )
        # 主圆形
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.COLORS["recording_bg"], outline="#ff4444", width=2, tags="btn",
        )
        # 停止图标 (正方形)
        stop_s = r * 0.55
        self.canvas.create_rectangle(
            cx - stop_s, cy - stop_s, cx + stop_s, cy + stop_s,
            fill=self.COLORS["recording_fg"], outline="", tags="btn",
        )
        # 帧数 + 提示
        self.canvas.create_text(
            cx, cy + r + 14,
            text=f"{self.frame_count} 帧", fill="#cc3333",
            font=("Helvetica", 9, "bold"), tags="btn",
        )
        self.status = "recording"

    def _draw_complete(self, path: str, line_count: int = 0):
        """绘制完成态按钮 (绿色勾 + 行数)。"""
        self.canvas.delete("all")
        s = self.BUTTON_SIZE
        r = s // 2 - self.PADDING
        cx, cy = s // 2, s // 2

        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.COLORS["complete_bg"], outline="#44cc44", width=2, tags="btn",
        )
        # 勾号
        self.canvas.create_text(
            cx, cy, text="✓", fill="white",
            font=("Helvetica", 20, "bold"), tags="btn",
        )
        # 行数
        self.canvas.create_text(
            cx, cy + r + 14,
            text=f"{line_count} 行", fill="#33aa33",
            font=("Helvetica", 9, "bold"), tags="btn",
        )
        self.status = "complete"

    def _pulse_animation(self):
        """脉冲动画循环 (根据当前状态选择对应的脉冲绘制)。"""
        if not self.is_recording:
            return
        if self.status == "working":
            self._draw_working()
        elif self.status == "warning":
            self._draw_warning()
        elif self.status == "recording":
            self._draw_recording()
        self._pulse_id = self.root.after(200, self._pulse_animation)

    # ── 事件处理 ──────────────────────────────────

    def _on_click(self, event):
        """点击按钮切换捕获状态。"""
        if self._is_dragging:
            self._is_dragging = False
            return
        self._toggle_capture()

    def _toggle_capture(self):
        """切换 开始/停止 捕获。"""
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        """开始捕获会话 (初始状态为蓝色工作态)。"""
        self.is_recording = True
        self.frame_count = 0
        self._consecutive_no_new = 0
        self._consecutive_poor_align = 0
        self._prev_unique = 0
        self.session = ScrollCaptureSession(strategy="pixel")
        self._stop_capture = False

        self._draw_working()
        self._pulse_animation()

        # 启动捕获线程
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        logger.info("Capture started")

    def _stop_recording(self):
        """停止捕获：拼接 -> OCR -> 保存为 .txt 文件。"""
        self.is_recording = False
        self._stop_capture = True

        if self._pulse_id:
            self.root.after_cancel(self._pulse_id)
            self._pulse_id = None

        if self.session and len(self.session.frames) > 0:
            try:
                # 1. 拼接图像
                result = self.session.stitch()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # 2. OCR 提取文本
                self._show_status("文本提取中...")
                self.root.update()
                text = extract_text(result, lang="chi_sim+eng", preprocess=False)

                # 3. 保存 .txt (默认输出 - 用户关心的屏幕内容)
                txt_fname = f"scroll_capture_{timestamp}.txt"
                txt_path = os.path.join(self.output_dir, txt_fname)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self._last_text_path = txt_path

                # 4. 可选保存 .png (辅助，不是主要输出)
                img_fname = f"scroll_capture_{timestamp}.png"
                img_path = os.path.join(self.output_dir, img_fname)
                result.save(img_path)

                line_count = len([line for line in text.split("\n") if line.strip()])
                logger.info(
                    f"Saved: {txt_path} ({line_count} lines, "
                    f"image={result.width}x{result.height})"
                )
                self._draw_complete(txt_fname, line_count)
                # 5秒后回到空闲态
                self.root.after(5000, self._reset_to_idle)

            except Exception as e:
                logger.error(f"Save error: {e}")
                import traceback
                traceback.print_exc()
                self._draw_idle()
        else:
            self._draw_idle()

        self.session = None
        logger.info(f"Capture stopped, {self.frame_count} frames captured")

    def _reset_to_idle(self):
        """回到空闲态。"""
        if not self.is_recording:
            self._draw_idle()

    def _capture_loop(self):
        """后台捕获循环 (含颜色状态切换 + 底部检测)。

        Color state flow:
          blue(working) -> red(warning) -> blue(working) -> ... -> green(complete) -> grey(idle)

        Warning triggers:
          1. unique > 150: too much new content (scrolled too fast)
          2. quality > 30: poor alignment MSE (content jumped too much)
          3. overlap == 0 and prev_unique > 10: alignment completely failed

        Recovery:
          Next frame with unique < 100 and quality < 20 -> back to blue
        """
        import time as _time
        while not self._stop_capture:
            try:
                frame = capture_screen()
                frame = compress_image(frame, quality=80)
                if self.session:
                    overlap, unique, quality = self.session.add_frame(frame)
                    self.frame_count = len(self.session.frames)

                    # === Color state logic ===
                    if self.frame_count > 1:
                        too_fast = unique > 150
                        poor_align = quality > 30 if quality > 0 else False
                        align_failed = (overlap == 0 and self._prev_unique > 10)

                        if too_fast or poor_align or align_failed:
                            self._consecutive_poor_align += 1
                            if self._consecutive_poor_align >= 1 and self.status != "warning":
                                logger.info(
                                    f"Warning: fast={too_fast}, "
                                    f"quality={quality:.1f}, failed={align_failed}"
                                )
                                self.root.after(0, self._set_status_warning)
                        else:
                            if self._consecutive_poor_align > 0:
                                logger.info("Recovered: alignment OK again")
                            self._consecutive_poor_align = 0
                            if self.status != "working":
                                self.root.after(0, self._set_status_working)

                    self._prev_unique = unique

                    # 底部检测：连续 2 帧无新内容 -> 自动停止
                    if unique <= 2:
                        self._consecutive_no_new += 1
                        if self._consecutive_no_new >= 2:
                            logger.info("Bottom reached, auto-stopping")
                            self.root.after(0, self._auto_stop)
                            break
                    else:
                        self._consecutive_no_new = 0

                    # 更新 UI
                    self.root.after(0, self._update_frame_count)
                _time.sleep(0.8)
            except Exception as e:
                logger.error(f"Capture error: {e}")
                break

    def _update_frame_count(self):
        """更新 UI 帧数显示 (根据当前状态刷新)。"""
        if self.status == "working":
            self._draw_working()
        elif self.status == "warning":
            self._draw_warning()
        elif self.status == "recording":
            self._draw_recording()

    # ── 底部检测 & 状态提示 ───────────────────────

    # ---- status switching & bottom detection ----

    def _set_status_working(self):
        """Switch to working state (blue) - capture/OCR in progress."""
        if self.is_recording:
            self._draw_working()

    def _set_status_warning(self):
        """Switch to warning state (red) - scroll too fast / can't align."""
        if self.is_recording:
            self._draw_warning()
            if self._pulse_id:
                self.root.after_cancel(self._pulse_id)
            self._pulse_id = self.root.after(200, self._pulse_animation)

    # ---- bottom detection & status ----

    def _auto_stop(self):
        """Auto-stop: detected bottom of page reached."""
        if self.is_recording:
            logger.info("Auto-stop triggered (bottom reached)")
            self._stop_recording()

    def _show_status(self, text: str):
        """在按钮下方显示状态文字。"""
        self.canvas.delete("status_text")
        s = self.BUTTON_SIZE
        cx, cy = s // 2, s // 2
        r = s // 2 - self.PADDING
        self.canvas.create_text(
            cx, cy + r + 14,
            text=text, fill="#999999",
            font=("Helvetica", 9), tags="status_text",
        )

    # ── 右键菜单 ──────────────────────────────────

    def _show_context_menu(self, event):
        """显示右键退出菜单。"""
        self._menu.tk_popup(event.x_root, event.y_root)
        self._menu.grab_release()

    # ── 拖拽支持 ──────────────────────────────────

    def _on_drag_start(self, event):
        """记录拖拽起始位置。"""
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()
        self._is_dragging = True

    def _on_drag_move(self, event):
        """拖拽移动窗口。"""
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def _on_enter(self, event):
        """鼠标悬停效果。"""
        if self.status == "idle":
            self._set_button_color(self.COLORS["idle_hover"])

    def _on_leave(self, event):
        """鼠标离开效果。"""
        if self.status == "idle":
            self._set_button_color(self.COLORS["idle_bg"])

    def _set_button_color(self, color):
        """更新按钮颜色。"""
        self.canvas.itemconfig("btn_fill", fill=color)

    # ── 生命周期 ──────────────────────────────────

    def _stop_and_quit(self):
        """停止并退出。"""
        if self.is_recording:
            self._stop_recording()
        self.root.quit()
        self.root.destroy()

    def run(self):
        """启动 GUI 主循环。"""
        logger.info(f"Floating capture button started (output: {self.output_dir})")
        self.root.mainloop()


def launch_gui(output_dir: str = DEFAULT_OUTPUT_DIR):
    """启动浮动按钮 GUI。

    Args:
        output_dir: 截图保存目录
    """
    app = FloatingCaptureButton(output_dir=output_dir)
    app.run()
