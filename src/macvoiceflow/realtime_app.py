import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, Menu
import os
import threading
import time
import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
import gc
import warnings
import sys
import subprocess
import re
import json
from pathlib import Path

import logging
from logging.handlers import RotatingFileHandler

def clean_and_format_transcript(raw_text, target_chars_per_para=150):
    """
    机械化后处理转录文本：
    1. 降低时间戳密度，将碎片化切片合并为大段落（约 150 字一个段落并配一个起始时间戳）
    2. 过滤语气单字与孤立微弱噪声
    """
    lines = raw_text.strip().split('\n')
    paragraphs = []
    current_ts = None
    current_para_parts = []
    current_char_count = 0
    noise_patterns = {'嗯。', '啊。', '哦。', '呃。', '嗯', '啊', '哦', '呃'}

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)', line)
        if m:
            ts, text = m.group(1), m.group(2).strip()
        else:
            ts, text = '', line

        # 过滤孤立微弱语气词噪声
        if text in noise_patterns or len(text) <= 1:
            continue

        if not current_ts:
            current_ts = ts

        current_para_parts.append(text)
        current_char_count += len(text)

        # 达到目标字数且遇到句末标点时断段
        if current_char_count >= target_chars_per_para and text.endswith(('。', '！', '？', '；')):
            combined = ''.join(current_para_parts)
            prefix = f'[{current_ts}] ' if current_ts else ''
            paragraphs.append(f'{prefix}{combined}')
            current_ts = None
            current_para_parts = []
            current_char_count = 0

    if current_para_parts:
        combined = ''.join(current_para_parts)
        prefix = f'[{current_ts}] ' if current_ts else ''
        paragraphs.append(f'{prefix}{combined}')

    return '\n\n'.join(paragraphs)

# === 0. 基础环境配置 ===
os.environ["PATH"] = os.pathsep.join(filter(None, ["/opt/homebrew/bin", os.environ.get("PATH", "")]))
warnings.filterwarnings("ignore")

# === 1. 路径与常量配置 ===
APP_NAME = "MacVoiceFlow"
APP_VERSION = "0.1.0"
DATA_ROOT = Path(os.path.expanduser(os.environ.get("MACVOICEFLOW_DATA_DIR", "~/Documents/MacVoiceFlow")))
CACHE_ROOT = Path(os.path.expanduser(os.environ.get("MACVOICEFLOW_CACHE_DIR", "~/Library/Caches/MacVoiceFlow")))
os.environ.setdefault("HF_HOME", str(CACHE_ROOT / "huggingface"))

BASE_DIR = str(DATA_ROOT)
TEMP_DIR = str(DATA_ROOT / "TempChunks")
RECORD_DIR = str(DATA_ROOT / "Record")
RESULT_DIR = str(DATA_ROOT / "转录结果")
LOG_FILE = str(DATA_ROOT / "app.log")
CONFIG_FILE = str(DATA_ROOT / "config.json")

DEFAULT_SETTINGS = {
    "model": "1.7B-4bit (默认/推荐)",
    "language": "中文",
    "max_lines": "3000",
    "max_segment_duration": 10.0,
    "vad_threshold": 0.006,
    "pause_duration": 0.8
}

for d in [TEMP_DIR, RECORD_DIR, RESULT_DIR]:
    os.makedirs(d, exist_ok=True)

# === 1.1 结构化日志系统与崩溃追踪 ===
logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _rfh = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=3, encoding="utf-8")
    _rfh.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s][%(threadName)s] %(message)s"))
    logger.addHandler(_rfh)
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s"))
    logger.addHandler(_sh)

def _handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("主线程未捕获异常退出:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = _handle_exception

if hasattr(threading, "excepthook"):
    def _handle_thread_exception(args):
        logger.critical(f"子线程 [{args.thread.name}] 未捕获异常:", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _handle_thread_exception

# 模型库 (调整顺序，1.7B-4bit 为首选默认)
MODELS = {
    "1.7B-4bit (默认/推荐)": "mlx-community/Qwen3-ASR-1.7B-4bit",
    "1.7B-8bit (高精)": "mlx-community/Qwen3-ASR-1.7B-8bit",
    "0.6B-8bit (极速)": "mlx-community/Qwen3-ASR-0.6B-8bit",
}

LANGUAGES = {
    "中文": "zh", "英语": "en", "法语": "fr", "日语": "ja",
    "韩语": "ko", "德语": "de", "西语": "es", "自动": None
}

# === 2. 录音室控制台设计系统 (Design System Tokens) ===
THEME = {
    "bg_main":       "#F0F0EC",  # 页面外沿
    "bg_card":       "#FFFFFF",  # 唯一主表面
    "bg_input":      "#F6F6F2",  # 输入背景
    "bg_paper":      "#FFFFFF",  # 转录稿面
    "bg_paper_soft": "#F6F6F2",
    "border":        "#D9DAD4",
    "fg_text":       "#1D2426",
    "fg_sub":        "#6F7778",
    "fg_subtle":     "#A6ACAC",
    "paper_text":    "#1D2426",
    "paper_sub":     "#6F7778",
    "accent":        "#C65645",  # 唯一主信号色
    "accent_hover":  "#A94435",
    "accent_soft":   "#F4E4DF",
    "danger":        "#C65645",
    "danger_hover":  "#A94435",
    "danger_soft":   "#F4E4DF",
    "success":       "#2F7A64",
    "success_soft":  "#E5F0EC",
    "warning":       "#A96E25",
    "vu_active":     "#C65645",
    "vu_inactive":   "#E3E4DF",
    "font_title":    ("SF Pro Display", 15, "bold"),
    "font_section":  ("SF Pro Display", 12, "bold"),
    "font_main":     ("SF Pro Text", 11),
    "font_caption":  ("SF Pro Text", 10),
    "font_mono":     ("SF Mono", 11),
    "font_body":     ("PingFang SC", 13)
}

class UltimateASR:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} · 实时语音转写")
        self.root.geometry("1400x950")
        self.root.configure(bg=THEME["bg_main"])

        # --- 核心状态 ---
        self.is_listening = False
        self.is_paused = False
        self.audio_queue = queue.Queue()
        self.asr_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.current_lang = "zh"

        self.full_recording = []
        self.vad_buffer = []
        self.model = None
        self.current_model_id = ""
        self.speech_active = False

        # 实时会话与文件状态
        self.current_live_md = None
        self.current_session_ts = ""
        self.last_q_size = -1
        self.var_current_filename = tk.StringVar(value="未开始录音")
        self.active_selected_file = None
        self.active_list = None
        self.custom_session_name = ""
        self.var_char_count = tk.StringVar(value="字数: 0")
        self.var_rec_timer = tk.StringVar(value="00:00:00")
        self.record_start_time = 0
        self.total_chars_accumulated = 0

        # UI 与性能参数持久化 (全部支持填入框绑定与校验)
        self.settings = self.load_settings()
        self.var_max_lines = tk.StringVar(value=str(self.settings.get("max_lines", "3000")))
        self.var_max_dur = tk.StringVar(value=str(self.settings.get("max_segment_duration", "10.0")))
        self.var_vad_threshold = tk.StringVar(value=str(self.settings.get("vad_threshold", "0.006")))
        self.var_pause_duration = tk.StringVar(value=str(self.settings.get("pause_duration", "0.8")))

        # 核心 VAD 浮点数参数
        self.silence_threshold = float(self.settings.get("vad_threshold", 0.006))
        self.silence_duration = float(self.settings.get("pause_duration", 0.8))
        self.max_segment_duration = float(self.settings.get("max_segment_duration", 10.0))
        self.last_speech_time = time.time()
        self.segment_start_time = time.time()
        self.stream = None

        # --- 初始化 ---
        self.setup_styles()
        self.setup_ui()
        self.setup_menus()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 启动主线程 UI 事件分发循环（彻底杜绝跨线程操作 Tkinter 引发的崩溃）
        self.poll_ui_queue()

        # --- 启动专属 ASR 工作线程（确保模型加载与推理在同一线程同一 GPU Stream 下） ---
        threading.Thread(target=self.asr_worker, daemon=True, name="ASRWorker").start()
        threading.Thread(target=self.queue_monitor, daemon=True, name="QueueMonitor").start()

        # 应用记忆的设置
        saved_model = self.settings.get("model", DEFAULT_SETTINGS["model"])
        if saved_model in MODELS:
            self.cb_model.set(saved_model)
        else:
            self.cb_model.current(0)

        saved_lang = self.settings.get("language", DEFAULT_SETTINGS["language"])
        if saved_lang in LANGUAGES:
            self.cb_lang.set(saved_lang)
        else:
            self.cb_lang.current(0)

        self._on_lang_change()
        self.refresh_files()
        self._cleanup_old_temp_chunks()

        # 异步加载
        self.root.after(300, self.trigger_model_switch)

    def load_settings(self):
        s = DEFAULT_SETTINGS.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        s.update(saved)
            except Exception as e:
                logger.warning(f"读取用户配置异常，使用默认设置: {e}")
        return s

    def save_settings(self):
        try:
            s = {
                "model": self.cb_model.get() if hasattr(self, 'cb_model') else DEFAULT_SETTINGS["model"],
                "language": self.cb_lang.get() if hasattr(self, 'cb_lang') else DEFAULT_SETTINGS["language"],
                "max_lines": self.var_max_lines.get() if hasattr(self, 'var_max_lines') else str(DEFAULT_SETTINGS["max_lines"]),
                "max_segment_duration": getattr(self, "max_segment_duration", DEFAULT_SETTINGS["max_segment_duration"]),
                "vad_threshold": getattr(self, "silence_threshold", DEFAULT_SETTINGS["vad_threshold"]),
                "pause_duration": getattr(self, "silence_duration", DEFAULT_SETTINGS["pause_duration"])
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
            logger.info("用户设置已持久化保存")
        except Exception as e:
            logger.warning(f"保存设置异常: {e}")

    def apply_settings(self, silent=False):
        """应用并校验所有填入框设置，若输入负数或非法字符则自动弹回默认设置"""
        corrected = False

        # 1. 最大行数校验 (正整数)
        try:
            val_lines = self.var_max_lines.get().strip()
            if not val_lines.isdigit() or int(val_lines) <= 0:
                raise ValueError()
        except Exception:
            self.var_max_lines.set(str(DEFAULT_SETTINGS["max_lines"]))
            corrected = True

        # 2. 最长单句秒数校验 (正数，且 >= 1.0)
        try:
            val_dur = float(self.var_max_dur.get().strip())
            if val_dur <= 0 or val_dur < 1.0:
                raise ValueError()
            self.max_segment_duration = val_dur
        except Exception:
            self.var_max_dur.set(str(DEFAULT_SETTINGS["max_segment_duration"]))
            self.max_segment_duration = DEFAULT_SETTINGS["max_segment_duration"]
            corrected = True

        # 3. 麦克风阈值校验 (0.0001 ~ 1.0 之间的正浮点数)
        try:
            val_sens = float(self.var_vad_threshold.get().strip())
            if val_sens <= 0 or val_sens > 1.0:
                raise ValueError()
            self.silence_threshold = val_sens
        except Exception:
            self.var_vad_threshold.set(str(DEFAULT_SETTINGS["vad_threshold"]))
            self.silence_threshold = DEFAULT_SETTINGS["vad_threshold"]
            corrected = True

        # 4. 断句停顿秒数校验 (0.01 ~ 60.0 之间的正浮点数)
        try:
            val_pause = float(self.var_pause_duration.get().strip())
            if val_pause <= 0 or val_pause > 60.0:
                raise ValueError()
            self.silence_duration = val_pause
        except Exception:
            self.var_pause_duration.set(str(DEFAULT_SETTINGS["pause_duration"]))
            self.silence_duration = DEFAULT_SETTINGS["pause_duration"]
            corrected = True

        self.save_settings()

        if not silent:
            if corrected:
                self.lbl_status.config(text="数值无效，已恢复默认并保存", foreground=THEME["warning"])
            else:
                self.lbl_status.config(text="设置已应用并保存", foreground=THEME["success"])

    def reset_to_default_settings(self):
        logger.info("重置为默认设置")
        self.cb_model.set(DEFAULT_SETTINGS["model"])
        self.cb_lang.set(DEFAULT_SETTINGS["language"])
        self.var_max_lines.set(str(DEFAULT_SETTINGS["max_lines"]))
        self.var_max_dur.set(str(DEFAULT_SETTINGS["max_segment_duration"]))
        self.var_vad_threshold.set(str(DEFAULT_SETTINGS["vad_threshold"]))
        self.var_pause_duration.set(str(DEFAULT_SETTINGS["pause_duration"]))
        self.max_segment_duration = DEFAULT_SETTINGS["max_segment_duration"]
        self.silence_threshold = DEFAULT_SETTINGS["vad_threshold"]
        self.silence_duration = DEFAULT_SETTINGS["pause_duration"]
        self._on_lang_change()
        self.trigger_model_switch()
        self.save_settings()
        self.lbl_status.config(text="已恢复默认设置", foreground=THEME["success"])

    def poll_ui_queue(self):
        try:
            while not self.ui_queue.empty():
                msg = self.ui_queue.get_nowait()
                mtype = msg[0]
                if mtype == "TEXT":
                    self.append_text(msg[1])
                elif mtype == "STATUS":
                    self.lbl_status.config(text=msg[1], foreground=msg[2])
                elif mtype == "PROGRESS":
                    mode, val, action = msg[1], msg[2], msg[3]
                    if action == "start":
                        self.progress.config(mode=mode)
                        self.progress.start(val)
                    elif action == "stop":
                        self.progress.stop()
                        self.progress.config(mode=mode, value=val)
                elif mtype == "QUEUE_LABEL":
                    self.lbl_queue.config(text=msg[1], foreground=msg[2])
                elif mtype == "VU_METER":
                    self.update_vu_meter(msg[1], msg[2])
                elif mtype == "SAVE_FLOW":
                    self._save_flow()
        except Exception as e:
            logger.error(f"UI 队列分发异常: {e}", exc_info=True)
        finally:
            try:
                if hasattr(self, 'root') and self.root.winfo_exists():
                    self.root.after(80, self.poll_ui_queue)
            except Exception:
                pass

    def update_vu_meter(self, level, is_active):
        """实时渲染 20 段 LED 立体声感动态电平表"""
        if not hasattr(self, 'canvas_vu'): return
        try:
            self.canvas_vu.delete("all")
            w = self.canvas_vu.winfo_width() or 220
            h = self.canvas_vu.winfo_height() or 12
            num_bars = 20
            gap = 3
            bar_w = max((w - (num_bars - 1) * gap) // num_bars, 2)
            active_count = int(level * num_bars)
            for i in range(num_bars):
                x0 = i * (bar_w + gap)
                x1 = x0 + bar_w
                if i < active_count:
                    ratio = i / num_bars
                    if ratio < 0.7:
                        color = THEME["success"]
                    elif ratio < 0.9:
                        color = THEME["warning"]
                    else:
                        color = THEME["danger"]
                else:
                    color = THEME["vu_inactive"]
                self.canvas_vu.create_rectangle(x0, 2, x1, h - 2, fill=color, outline="")

            if hasattr(self, 'lbl_vu_hint'):
                if is_active:
                    self.lbl_vu_hint.config(text="正在收音 (说话中)", foreground=THEME["success"])
                else:
                    self.lbl_vu_hint.config(text="环境静音中", foreground=THEME["fg_sub"])
        except Exception:
            pass

    def _timer_tick(self):
        """精确到秒的专业录音时长计时器"""
        if self.is_listening and not self.is_paused:
            elapsed = int(time.time() - self.record_start_time)
            hrs = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            self.var_rec_timer.set(f"{hrs:02d}:{mins:02d}:{secs:02d}")
        if self.is_listening:
            self.root.after(1000, self._timer_tick)

    def on_close(self):
        logger.info("应用程序正常关闭")
        self.is_listening = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.root.destroy()

    def _on_lang_change(self, event=None):
        name = self.cb_lang.get()
        self.current_lang = LANGUAGES.get(name, "zh")
        self.save_settings()
        logger.info(f"语言配置切换为: {name} (参数: {self.current_lang})")

    def setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Main.TFrame", background=THEME["bg_main"])
        s.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        s.configure("SubCard.TFrame", background=THEME["bg_input"], relief="flat")
        s.configure("H1.TLabel", background=THEME["bg_card"], foreground=THEME["fg_text"], font=THEME["font_title"])
        s.configure("Section.TLabel", background=THEME["bg_card"], foreground=THEME["fg_sub"], font=THEME["font_section"])
        s.configure("Std.TLabel", background=THEME["bg_card"], foreground=THEME["fg_text"], font=THEME["font_main"])
        s.configure("Sub.TLabel", background=THEME["bg_card"], foreground=THEME["fg_sub"], font=THEME["font_caption"])
        s.configure("Badge.TLabel", background=THEME["bg_input"], foreground=THEME["fg_text"], font=THEME["font_mono"], padding=(8, 3))
        s.configure("Timer.TLabel", background=THEME["bg_card"], foreground=THEME["fg_text"], font=THEME["font_mono"])
        s.configure("Accent.TButton", background=THEME["accent"], foreground="#FFFFFF", borderwidth=0, font=("SF Pro Text", 12, "bold"), padding=(14, 7))
        s.map("Accent.TButton", background=[("active", THEME["accent_hover"]), ("disabled", THEME["fg_subtle"])])
        s.configure("Danger.TButton", background=THEME["danger"], foreground="#FFFFFF", borderwidth=0, font=("SF Pro Text", 12, "bold"), padding=(14, 7))
        s.map("Danger.TButton", background=[("active", THEME["danger_hover"]), ("disabled", THEME["fg_subtle"])])
        s.configure("Normal.TButton", background=THEME["bg_input"], foreground=THEME["fg_text"], borderwidth=0, font=("SF Pro Text", 11), padding=(9, 5))
        s.map("Normal.TButton", background=[("active", THEME["border"]), ("disabled", THEME["bg_input"])])
        s.configure("Action.TButton", background=THEME["accent_soft"], foreground=THEME["accent"], borderwidth=0, font=("SF Pro Text", 11, "bold"), padding=(9, 5))
        s.map("Action.TButton", background=[("active", "#EDD3CC"), ("disabled", THEME["bg_input"])])
        s.configure("Small.TButton", background=THEME["bg_card"], foreground=THEME["fg_sub"], borderwidth=0, font=("SF Pro Text", 10), padding=(7, 4))
        s.map("Small.TButton", background=[("active", THEME["bg_input"]), ("disabled", THEME["bg_card"])])
        s.configure("TEntry", fieldbackground=THEME["bg_input"], foreground=THEME["fg_text"], bordercolor=THEME["border"], lightcolor=THEME["bg_input"], darkcolor=THEME["bg_input"], padding=(7, 4), font=THEME["font_main"])
        s.configure("TCombobox", fieldbackground=THEME["bg_input"], background=THEME["bg_input"], foreground=THEME["fg_text"], bordercolor=THEME["border"], lightcolor=THEME["bg_input"], darkcolor=THEME["bg_input"], padding=(7, 4), font=THEME["font_main"])
        s.configure("Minimal.Horizontal.TProgressbar", background=THEME["accent"], troughcolor=THEME["bg_input"], bordercolor=THEME["bg_main"], lightcolor=THEME["accent"], darkcolor=THEME["accent"])

    def setup_ui(self):
        top = ttk.Frame(self.root, style="Card.TFrame", padding=(18, 14))
        top.pack(fill=tk.X, padx=16, pady=(16, 12))
        for column in range(8):
            top.columnconfigure(column, weight=0)
        top.columnconfigure(6, weight=1)

        ttk.Label(top, text="模型引擎", style="Sub.TLabel").grid(row=0, column=0, sticky="w", padx=(6, 10))
        self.cb_model = ttk.Combobox(top, values=list(MODELS.keys()), state="readonly", width=22)
        self.cb_model.grid(row=1, column=0, sticky="w", padx=(6, 10), pady=(3, 0))
        self.cb_model.bind("<<ComboboxSelected>>", self.trigger_model_switch)

        ttk.Label(top, text="输出语言", style="Sub.TLabel").grid(row=0, column=1, sticky="w", padx=10)
        self.cb_lang = ttk.Combobox(top, values=list(LANGUAGES.keys()), state="readonly", width=8)
        self.cb_lang.grid(row=1, column=1, sticky="w", padx=10, pady=(3, 0))
        self.cb_lang.bind("<<ComboboxSelected>>", self._on_lang_change)

        ttk.Label(top, text="最大行数", style="Sub.TLabel").grid(row=0, column=2, sticky="w", padx=10)
        self.entry_max_lines = ttk.Entry(top, textvariable=self.var_max_lines, width=7)
        self.entry_max_lines.grid(row=1, column=2, sticky="w", padx=10, pady=(3, 0))
        self.entry_max_lines.bind("<Return>", lambda e: self.apply_settings())

        ttk.Label(top, text="最长单句 (秒)", style="Sub.TLabel").grid(row=0, column=3, sticky="w", padx=10)
        self.entry_max_dur = ttk.Entry(top, textvariable=self.var_max_dur, width=7)
        self.entry_max_dur.grid(row=1, column=3, sticky="w", padx=10, pady=(3, 0))
        self.entry_max_dur.bind("<Return>", lambda e: self.apply_settings())

        ttk.Label(top, text="麦克风阈值 (VAD)", style="Sub.TLabel").grid(row=0, column=4, sticky="w", padx=10)
        self.entry_vad_thresh = ttk.Entry(top, textvariable=self.var_vad_threshold, width=7)
        self.entry_vad_thresh.grid(row=1, column=4, sticky="w", padx=10, pady=(3, 0))
        self.entry_vad_thresh.bind("<Return>", lambda e: self.apply_settings())

        ttk.Label(top, text="断句停顿 (秒)", style="Sub.TLabel").grid(row=0, column=5, sticky="w", padx=10)
        self.entry_pause_dur = ttk.Entry(top, textvariable=self.var_pause_duration, width=7)
        self.entry_pause_dur.grid(row=1, column=5, sticky="w", padx=10, pady=(3, 0))
        self.entry_pause_dur.bind("<Return>", lambda e: self.apply_settings())
        f_btns = ttk.Frame(top, style="Card.TFrame")
        f_btns.grid(row=0, column=6, rowspan=2, sticky="e", padx=(10, 16))
        self.btn_reset_cfg = ttk.Button(f_btns, text="默认设置", style="Small.TButton", command=self.reset_to_default_settings)
        self.btn_reset_cfg.pack(fill=tk.X, pady=(0, 2))
        self.btn_apply_cfg = ttk.Button(f_btns, text="应用设置", style="Action.TButton", command=self.apply_settings)
        self.btn_apply_cfg.pack(fill=tk.X, pady=(2, 0))

        self.lbl_status = ttk.Label(top, text="● 系统初始化...", style="H1.TLabel", foreground=THEME["fg_sub"])
        self.lbl_status.grid(row=0, column=7, rowspan=2, sticky="e", padx=(10, 4))

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=THEME["bg_main"], sashwidth=2, bd=0)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

        left = ttk.Frame(paned, style="Card.TFrame")
        paned.add(left, width=380)

        self._create_header(left, "原始录音 (Record)", btn_text="打开", btn_cmd=lambda: subprocess.run(["open", RECORD_DIR]))
        self.lst_rec = self._create_listbox(left)
        self.lst_rec.pack(fill=tk.BOTH, expand=True, padx=12)
        self._create_toolbar(left, "批量转译", self.transcribe_sel, "刷新列表", self.on_manual_refresh)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=16, pady=8)

        self._create_header(left, "转录结果 (Results)", btn_text="打开", btn_cmd=lambda: subprocess.run(["open", RESULT_DIR]))
        self.lst_res = self._create_listbox(left)
        self.lst_res.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        right = ttk.Frame(paned, style="Card.TFrame")
        paned.add(right)

        f_head_right = ttk.Frame(right, style="Card.TFrame")
        f_head_right.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(f_head_right, text="实时同传 / 编辑区", style="H1.TLabel").pack(side=tk.LEFT)

        ttk.Label(f_head_right, text="文件名称:", style="Sub.TLabel").pack(side=tk.LEFT, padx=(18, 5))
        self.entry_filename = ttk.Entry(f_head_right, textvariable=self.var_current_filename, width=22)
        self.entry_filename.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_filename.bind("<Return>", lambda e: self.save_or_rename_filename())

        self.btn_save_filename = ttk.Button(f_head_right, text="保存名称", style="Action.TButton", command=self.save_or_rename_filename)
        self.btn_save_filename.pack(side=tk.LEFT, padx=(0, 12))

        f_indicators = ttk.Frame(f_head_right, style="Card.TFrame")
        f_indicators.pack(side=tk.RIGHT)

        self.lbl_queue = ttk.Label(f_indicators, text="队列空闲", style="Badge.TLabel", foreground=THEME["success"])
        self.lbl_queue.pack(side=tk.RIGHT, padx=(6, 0))

        self.lbl_char_count = ttk.Label(f_indicators, textvariable=self.var_char_count, style="Badge.TLabel", foreground=THEME["fg_sub"])
        self.lbl_char_count.pack(side=tk.RIGHT)

        self.txt = scrolledtext.ScrolledText(
            right, font=THEME["font_body"],
            bg=THEME["bg_card"], fg=THEME["fg_text"], insertbackground=THEME["accent"],
            bd=0, highlightthickness=0,
            padx=24, pady=20,
            spacing1=3, spacing2=4, spacing3=6,
            selectbackground=THEME["accent_soft"], selectforeground=THEME["accent"]
        )
        self.txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.txt.bind("<Button-2>", self.show_text_menu)
        self.txt.bind("<Button-3>", self.show_text_menu)

        self.txt.tag_configure("timestamp", foreground=THEME["fg_subtle"], font=THEME["font_mono"])
        self.txt.tag_configure("content", foreground=THEME["fg_text"], font=THEME["font_body"])

        btm = ttk.Frame(right, style="Card.TFrame", padding=(18, 12))
        btm.pack(fill=tk.X)

        f_vu = ttk.Frame(btm, style="Card.TFrame")
        f_vu.pack(fill=tk.X, pady=(0, 10))

        f_timer = ttk.Frame(f_vu, style="Card.TFrame")
        f_timer.pack(side=tk.LEFT)
        self.lbl_rec_dot = ttk.Label(f_timer, text="●", foreground=THEME["fg_subtle"], font=("SF Pro Text", 12))
        self.lbl_rec_dot.pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_timer = ttk.Label(f_timer, textvariable=self.var_rec_timer, style="Timer.TLabel")
        self.lbl_timer.pack(side=tk.LEFT)

        self.canvas_vu = tk.Canvas(f_vu, height=12, bg=THEME["bg_card"], bd=0, highlightthickness=0)
        self.canvas_vu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=16)

        self.lbl_vu_hint = ttk.Label(f_vu, text="麦克风待命", style="Sub.TLabel")
        self.lbl_vu_hint.pack(side=tk.RIGHT)

        f_actions = ttk.Frame(btm, style="Card.TFrame")
        f_actions.pack(fill=tk.X)

        self.btn_start = ttk.Button(f_actions, text="开始录音", style="Accent.TButton", command=self.start_rec)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.btn_pause = ttk.Button(f_actions, text="暂停", style="Normal.TButton", command=self.toggle_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self.btn_stop = ttk.Button(f_actions, text="停止并保存", style="Danger.TButton", command=self.stop_rec, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self.progress = ttk.Progressbar(self.root, style="Minimal.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(side=tk.BOTTOM, fill=tk.X)

    # === 辅助函数 ===
    def _create_header(self, p, t, btn_text=None, btn_cmd=None):
        f = ttk.Frame(p, style="Card.TFrame")
        f.pack(fill=tk.X, padx=15, pady=(15, 8))
        ttk.Label(f, text=t, style="H1.TLabel").pack(side=tk.LEFT)
        if btn_text and btn_cmd:
            ttk.Button(f, text=btn_text, style="Normal.TButton", command=btn_cmd).pack(side=tk.RIGHT)

    def _create_listbox(self, p):
        container = ttk.Frame(p, style="Card.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=10)
        lb = tk.Listbox(
            container, font=THEME["font_main"],
            selectmode=tk.EXTENDED, bd=0, highlightthickness=0,
            bg=THEME["bg_input"], fg=THEME["fg_text"],
            selectbackground=THEME["accent_soft"], selectforeground=THEME["accent"],
            activestyle="none"
        )
        sb = ttk.Scrollbar(container, orient="vertical", command=lb.yview)
        lb.config(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.bind("<Button-2>", lambda e: self.show_file_menu(e)); lb.bind("<Button-3>", lambda e: self.show_file_menu(e))
        lb.bind("<Double-Button-1>", self.dbl_click_open)
        lb.bind("<<ListboxSelect>>", self.on_listbox_select)
        return lb

    def _create_toolbar(self, p, t1, c1, t2, c2):
        f = ttk.Frame(p, style="Card.TFrame", padding=(10, 10))
        f.pack(fill=tk.X)
        ttk.Button(f, text=t1, style="Normal.TButton", command=c1).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ttk.Button(f, text=t2, style="Normal.TButton", command=c2).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5,0))

    def setup_menus(self):
        self.m_file = Menu(self.root, tearoff=0)
        self.m_file.add_command(label="打开 / 播放", command=self.menu_open)
        self.m_file.add_command(label="复制文件", command=self.menu_copy_file)
        self.m_file.add_separator()
        self.m_file.add_command(label="在 Finder 中显示", command=self.menu_reveal)
        self.m_file.add_command(label="重命名", command=self.menu_rename)
        self.m_file.add_command(label="删除选中", command=self.menu_delete)
        self.m_txt = Menu(self.root, tearoff=0)
        self.m_txt.add_command(label="复制选中", command=self.copy_selection)
        self.m_txt.add_command(label="清空", command=lambda: self.txt.delete("1.0", tk.END))

    def _update_sens(self, v):
        self.silence_threshold = float(v)
        if hasattr(self, 'lbl_sens_val'):
            self.lbl_sens_val.config(text=f"{float(v):.3f}")
    def _update_pause(self, v):
        self.silence_duration = float(v)
        if hasattr(self, 'lbl_pause_val'):
            self.lbl_pause_val.config(text=f"{float(v):.2f}s")

    def _update_max_dur(self, v):
        self.max_segment_duration = float(v)
        if hasattr(self, 'lbl_max_dur_val'):
            self.lbl_max_dur_val.config(text=f"{float(v):.1f}s")

    def _cleanup_old_temp_chunks(self):
        try:
            now = time.time()
            if os.path.exists(TEMP_DIR):
                for f in os.listdir(TEMP_DIR):
                    fp = os.path.join(TEMP_DIR, f)
                    if os.path.isfile(fp) and (now - os.path.getmtime(fp) > 86400):
                        try: os.remove(fp)
                        except Exception: pass
        except Exception:
            pass

    # === 模型加载 ===
    def trigger_model_switch(self, e=None):
        mid = MODELS.get(self.cb_model.get())
        self.save_settings()
        if not mid or mid == self.current_model_id: return
        self.current_model_id = mid
        self.root.after(0, lambda: [
            self.lbl_status.config(text="模型加载中...", foreground=THEME["warning"]),
            self.progress.config(mode='indeterminate'),
            self.progress.start(10)
        ])
        self.asr_queue.put(("LOAD_MODEL", mid))

    # === 录音与实时切片逻辑 ===
    def start_rec(self):
        self.is_listening = True
        self.is_paused = False
        self.full_recording = []
        self.vad_buffer = []
        self.speech_active = False
        self.segment_start_time = time.time()
        self.last_speech_time = time.time()

        # 清空右侧编辑区，让新一轮录音拥有崭新清爽的展示
        self.txt.delete("1.0", tk.END)

        # 初始化录音文件名称：优先采用用户输入框中或预设的名字，否则默认 "录音_时间戳"
        self.current_session_ts = time.strftime("%Y%m%d_%H%M%S")
        cur_input = self.var_current_filename.get().strip() if hasattr(self, 'var_current_filename') else ""
        if cur_input and cur_input != "未开始录音":
            self.custom_session_name = cur_input
        else:
            self.custom_session_name = f"录音_{self.current_session_ts}"

        self.var_current_filename.set(self.custom_session_name)
        self.active_selected_file = None # 开启录音时脱离左侧文件选中

        # 初始化实时草稿文件，每识别一句即刻追加，杜绝断电或崩溃导致内容丢失
        self.current_live_md = os.path.join(RESULT_DIR, f"实时草稿_{self.current_session_ts}.md")
        try:
            with open(self.current_live_md, "w", encoding="utf-8") as f:
                f.write(f"# 录音实时转写草稿 - {self.current_session_ts}\n\n")
        except Exception as e:
            logger.warning(f"初始化实时草稿文件失败: {e}")

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL, text="暂停")

        status_text = "录音进行中" if self.model else "录音中 (缓冲待转译)"
        status_color = THEME["danger"] if self.model else THEME["warning"]
        self.lbl_status.config(text=status_text, foreground=status_color)

        # 启动工作台计时器与重置字数
        self.record_start_time = time.time()
        self.var_rec_timer.set("00:00:00")
        self.total_chars_accumulated = 0
        self.var_char_count.set("字数: 0")
        if hasattr(self, 'lbl_rec_dot'):
            self.lbl_rec_dot.config(foreground=THEME["danger"])
        if hasattr(self, 'lbl_vu_hint'):
            self.lbl_vu_hint.config(text="正在收音 (环境监听中)", foreground=THEME["fg_sub"])
        self.root.after(1000, self._timer_tick)

        logger.info("开始录音，初始化音频输入流...")
        try:
            self.stream = sd.InputStream(callback=self.audio_cb, channels=1, samplerate=16000)
            self.stream.start()
            threading.Thread(target=self.loop, daemon=True, name="AudioVADLoop").start()
            logger.info("音频流启动成功")
        except Exception as e:
            logger.error(f"启动麦克风输入流失败: {e}", exc_info=True)
            self.lbl_status.config(text="麦克风启动失败", foreground=THEME["danger"])
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_pause.config(state=tk.DISABLED)
            self.is_listening = False

    def audio_cb(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio Stream Warning: {status}")
        if self.is_listening and not self.is_paused:
            try:
                d = indata.copy()
                self.audio_queue.put(d)
                self.full_recording.append(d)
            except Exception as e:
                logger.error(f"Error in audio_cb: {e}")

    def loop(self):
        logger.info("VAD 监测循环已启动")
        while self.is_listening:
            try:
                try:
                    data = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if self.is_paused:
                    continue

                rms = np.sqrt(np.mean(data**2))
                current_time = time.time()

                # 发送动态声波电平 (0.0 ~ 1.0) 驱动底部 LED 律动表
                norm_level = min(rms / (self.silence_threshold * 4.0 + 1e-6), 1.0)
                self.ui_queue.put(("VU_METER", norm_level, rms > self.silence_threshold))

                if rms > self.silence_threshold:
                    if not self.speech_active:
                        self.speech_active = True
                        self.segment_start_time = current_time
                    self.last_speech_time = current_time
                    self.vad_buffer.append(data)
                else:
                    if self.speech_active:
                        # 处于活跃说话中的静音停顿，追加到缓冲中
                        self.vad_buffer.append(data)
                        if current_time - self.last_speech_time > self.silence_duration:
                            self.push_queue()
                            self.speech_active = False
                    else:
                        # 处于纯静音状态：维护最多 8 个块 (~0.25秒) 的 pre-roll 缓冲，丢弃多余静音，严禁产生静音切片
                        self.vad_buffer.append(data)
                        if len(self.vad_buffer) > 8:
                            self.vad_buffer.pop(0)

                # 说话者持续说话超长强制切片
                if self.speech_active and (current_time - self.segment_start_time > self.max_segment_duration):
                    self.push_queue()
                    self.segment_start_time = current_time

            except Exception as e:
                logger.error(f"VAD 循环发生异常: {e}", exc_info=True)
        logger.info("VAD 监测循环已退出")

    def push_queue(self):
        if not self.vad_buffer: return
        audio = np.concatenate(self.vad_buffer, axis=0)
        self.vad_buffer = []

        # 音频长度检查：低于 0.3 秒无有效语义，忽略
        if len(audio) < 4800: return

        # 能量过滤：若整段最大振幅过低，说明仅为微弱底噪，过滤丢弃
        max_val = np.max(np.abs(audio))
        if max_val < (self.silence_threshold * 0.6): return

        # 平滑增益归一化，最大放大倍数限制为 3 倍，避免爆音与白噪放大
        if max_val > 0.01:
            gain = min(0.95 / max_val, 3.0)
            audio = audio * gain

        # 直接向 ASR 专属队列推送转录任务
        self.asr_queue.put(("TRANSCRIBE", audio))

    # === ASR 专属单一工作线程（模型加载与转录全生命周期共用同一线程，彻底根除 MLX Stream 冲突） ===
    def asr_worker(self):
        logger.info("ASR 专属工作线程已启动（严格保证 MLX GPU Stream 上下文一致）")
        while True:
            try:
                task = self.asr_queue.get()
                action, payload = task[0], task[1]

                if action == "LOAD_MODEL":
                    mid = payload
                    logger.info(f"ASR 线程开始加载模型: {mid}")
                    self.ui_queue.put(("STATUS", "模型加载中...", THEME["warning"]))
                    self.ui_queue.put(("PROGRESS", "indeterminate", 10, "start"))

                    if self.model:
                        del self.model
                        self.model = None
                    gc.collect()
                    try:
                        import mlx.core as mx
                        if hasattr(mx, "clear_cache"):
                            mx.clear_cache()
                        elif hasattr(mx, "metal") and mx.metal.is_available() and hasattr(mx.metal, "clear_cache"):
                            mx.metal.clear_cache()
                    except Exception as e:
                        logger.warning(f"清除显存缓存异常: {e}")

                    try:
                        from mlx_audio.stt.utils import load_model
                        self.model = load_model(mid)
                        logger.info(f"ASR 线程模型加载成功: {mid}")
                        self.ui_queue.put(("STATUS", "模型就绪", THEME["success"]))
                        self.ui_queue.put(("PROGRESS", "determinate", 0, "stop"))
                    except Exception as e:
                        logger.error(f"模型加载失败 [{mid}]: {e}", exc_info=True)
                        self.ui_queue.put(("STATUS", "加载失败", THEME["danger"]))
                        self.ui_queue.put(("PROGRESS", "determinate", 0, "stop"))

                elif action in ("TRANSCRIBE", "TRANSCRIBE_FILE"):
                    if self.model is None:
                        logger.warning("模型尚未就绪，任务稍后重试")
                        time.sleep(0.3)
                        self.asr_queue.put(task)
                        continue
                    self._do_trans(payload, is_file=(action == "TRANSCRIBE_FILE"))

            except Exception as e:
                logger.error(f"ASR 线程任务执行异常: {e}", exc_info=True)

    def queue_monitor(self):
        while True:
            try:
                q_size = self.asr_queue.qsize()
                if q_size != self.last_q_size:
                    self.last_q_size = q_size
                    if q_size > 0:
                        self.ui_queue.put(("QUEUE_LABEL", f"队列积压: {q_size}", THEME["warning"]))
                    else:
                        self.ui_queue.put(("QUEUE_LABEL", "队列空闲", THEME["success"]))
            except Exception:
                pass
            time.sleep(0.5)

    def _do_trans(self, item, is_file=False):
        try:
            if self.model is None:
                return

            if is_file:
                # 批量文件转录：安全读取，绝不删除用户原始文件
                if not os.path.exists(item):
                    return
                arr, sr = sf.read(item)
                if sr != 16000:
                    import librosa
                    arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
                if arr.ndim > 1:
                    arr = np.mean(arr, axis=1)
                arr = arr.astype(np.float32)
            else:
                # 内存切片
                arr = item.astype(np.float32).flatten()

            if len(arr) == 0:
                return

            # 安全读取当前语言变量
            lang = self.current_lang
            kwargs = {'language': lang} if lang else {}

            # 使用 model.generate 推理
            res = self.model.generate(arr, verbose=False, **kwargs)
            txt = res.text.strip() if hasattr(res, 'text') else str(res).strip()

            if txt:
                logger.info(f"转录成功: {txt}")
                self.ui_queue.put(("TEXT", txt))

                # 实时增量落盘：每句直接写盘，断电或崩溃零丢失 (仅限实时录音切片，杜绝批量转译串写)
                if not is_file and self.current_live_md:
                    try:
                        with open(self.current_live_md, "a", encoding="utf-8") as f:
                            f.write(f"[{time.strftime('%H:%M:%S')}] {txt}\n")
                    except Exception as e_write:
                        logger.warning(f"实时草稿追加写入失败: {e_write}")
                elif is_file:
                    try:
                        base = os.path.splitext(os.path.basename(item))[0]
                        file_md = os.path.join(RESULT_DIR, f"{base}.md")
                        formatted = clean_and_format_transcript(txt, target_chars_per_para=150)
                        with open(file_md, "w", encoding="utf-8") as f:
                            f.write(f"# {base}\n**文件**: {item}\n**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n{formatted}\n")
                        logger.info(f"批量文件转录结果已保存: {file_md}")
                        self.root.after(0, self.refresh_files)
                    except Exception as ef:
                        logger.warning(f"保存批量转录文件异常: {ef}")

        except Exception as e:
            logger.error(f"转录执行异常: {e}", exc_info=True)
        finally:
            # 即刻清理 MLX 显存缓存与局部引用，防止内存泄漏导致系统级 Swap 换页卡死
            if 'res' in locals():
                del res
            try:
                import mlx.core as mx
                if hasattr(mx, "clear_cache"):
                    mx.clear_cache()
            except Exception:
                pass

    # === 停止与保存 ===
    def stop_rec(self):
        if not self.is_listening: return
        self.is_listening = False
        self.lbl_status.config(text="整理文件中...", foreground=THEME["accent"])
        self.btn_stop.config(state=tk.DISABLED)
        threading.Thread(target=self._stop_bg, daemon=True, name="StopRecorder").start()

    def _stop_bg(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.warning(f"关闭音频流提示: {e}")
        # 将剩余buffer强制推出
        if self.vad_buffer:
            self.push_queue()

        # 等待队列中的最后切片处理完毕（最多等待 3 秒）
        t0 = time.time()
        while self.asr_queue.qsize() > 0 and time.time() - t0 < 3.0:
            time.sleep(0.1)

        self.ui_queue.put(("SAVE_FLOW",))

    def _save_flow(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)

        ts = getattr(self, "current_session_ts", "") or time.strftime("%Y%m%d_%H%M%S")
        custom = getattr(self, "custom_session_name", "").strip()
        input_name = self.var_current_filename.get().strip() if hasattr(self, 'var_current_filename') else ""
        if custom:
            default_name = custom
        elif input_name and input_name != "未开始录音":
            default_name = input_name
        else:
            default_name = f"录音_{ts}"

        for ch in r'/\:*?"<>|':
            default_name = default_name.replace(ch, "_")
        self.custom_session_name = ""

        # 1. 保存完整音频并立即清空内存释放
        if self.full_recording and len(self.full_recording) > 0:
            try:
                wav = os.path.join(RECORD_DIR, f"ok]{default_name}.wav")
                full_audio = np.concatenate(self.full_recording, axis=0)
                self.full_recording.clear() # 关键：立即释放几十万个小对象
                if len(full_audio) > 0:
                    mx = np.max(np.abs(full_audio))
                    if mx > 0.01:
                        gain = min(0.95 / mx, 3.0)
                        full_audio = full_audio * gain
                    sf.write(wav, full_audio, 16000)
                    del full_audio
                    logger.info(f"录音音频已保存: {wav}")
            except Exception as e:
                logger.error(f"保存录音音频异常: {e}", exc_info=True)
                self.full_recording.clear()

        # 2. 机械化规整转写文本（优先读取实时草稿全量文本，防止文本框滑动窗口截断丢失早期内容）
        raw_text = ""
        if self.current_live_md and os.path.exists(self.current_live_md):
            try:
                with open(self.current_live_md, "r", encoding="utf-8") as f:
                    raw_text = f.read().strip()
            except Exception as e:
                logger.warning(f"读取实时草稿全量文件异常: {e}")
        if not raw_text:
            raw_text = self.txt.get(1.0, tk.END).strip()

        if raw_text:
            try:
                formatted_text = clean_and_format_transcript(raw_text, target_chars_per_para=150)
                final_md = os.path.join(RESULT_DIR, f"{default_name}.md")
                with open(final_md, "w", encoding="utf-8") as f:
                    f.write(f"# {default_name}\n**时间**: {ts}\n\n---\n\n{formatted_text}\n")

                # 清理临时实时草稿
                if self.current_live_md and os.path.exists(self.current_live_md):
                    try:
                        os.remove(self.current_live_md)
                    except Exception:
                        pass
                self.current_live_md = None

                self.refresh_files()
                self.lbl_status.config(text=f"已保存: {default_name}", foreground=THEME["success"])
                logger.info(f"录音与规整文本已保存: {final_md}")
            except Exception as e:
                logger.error(f"规整转录文本异常: {e}", exc_info=True)
                self.lbl_status.config(text="保存失败", foreground=THEME["danger"])
        else:
            self.lbl_status.config(text="录音无效(无内容)", foreground=THEME["fg_sub"])
            self.current_live_md = None

        # 复位电平表与指示灯
        if hasattr(self, 'lbl_rec_dot'):
            self.lbl_rec_dot.config(foreground=THEME["fg_subtle"])
        self.update_vu_meter(0.0, False)
        if hasattr(self, 'lbl_vu_hint'):
            self.lbl_vu_hint.config(text="麦克风待命", foreground=THEME["fg_sub"])

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        txt = "继续" if self.is_paused else "暂停"
        self.btn_pause.config(text=txt)
        if self.is_paused:
            if hasattr(self, 'lbl_rec_dot'):
                self.lbl_rec_dot.config(foreground=THEME["warning"])
            if hasattr(self, 'lbl_vu_hint'):
                self.lbl_vu_hint.config(text="已暂停收音", foreground=THEME["warning"])
            self.update_vu_meter(0.0, False)
        else:
            if hasattr(self, 'lbl_rec_dot'):
                self.lbl_rec_dot.config(foreground=THEME["danger"])
            if hasattr(self, 'lbl_vu_hint'):
                self.lbl_vu_hint.config(text="正在收音 (环境监听中)", foreground=THEME["success"])
        self.lbl_status.config(text="已暂停" if self.is_paused else "录音中", foreground=THEME["warning"] if self.is_paused else THEME["danger"])

    def append_text(self, t):
        ts = time.strftime("%H:%M:%S")
        # 带有标签的高保真渲染：时间戳弱化代码字体，正文使用自然屏显正文字体
        self.txt.insert(tk.END, f"[{ts}] ", "timestamp")
        self.txt.insert(tk.END, f"{t}\n", "content")

        # 实时字数累计更新
        self.total_chars_accumulated += len(t.strip())
        if hasattr(self, 'var_char_count'):
            self.var_char_count.set(f"字数: {self.total_chars_accumulated:,}")

        # 动态读取最大保留行数设置，自动裁切最早行，防止长久运行渲染卡顿
        try:
            val = self.var_max_lines.get().strip()
            max_l = int(val) if val.isdigit() and int(val) > 0 else 3000
        except Exception:
            max_l = 3000
        try:
            total_lines = int(self.txt.index('end-1c').split('.')[0]) - 1
            if total_lines > max_l:
                self.txt.delete("1.0", f"{total_lines - max_l + 1}.0")
        except Exception:
            pass
        self.txt.see(tk.END)

    def refresh_files(self):
        self.lst_rec.delete(0, tk.END); self.lst_res.delete(0, tk.END)
        for f in sorted([x for x in os.listdir(RECORD_DIR) if not x.startswith('.')], reverse=True): self.lst_rec.insert(tk.END, f)
        for f in sorted([x for x in os.listdir(RESULT_DIR) if not x.startswith('.')], reverse=True): self.lst_res.insert(tk.END, f)

    def on_manual_refresh(self):
        """用户点击刷新列表：清除左侧所有选中，并切回当前正在转录的工作流文件状态（若未在转录则为无选中状态）"""
        self.refresh_files()
        self.lst_rec.selection_clear(0, tk.END)
        self.lst_res.selection_clear(0, tk.END)
        self.active_selected_file = None

        if self.is_listening:
            cur_name = getattr(self, "custom_session_name", "")
            if not cur_name:
                ts = getattr(self, "current_session_ts", "") or time.strftime("%Y%m%d_%H%M%S")
                cur_name = f"录音_{ts}"
                self.custom_session_name = cur_name
            self.var_current_filename.set(cur_name)
            self.lbl_status.config(text=f"已切回当前转录状态: {cur_name}", foreground=THEME["accent"])
            logger.info(f"手动刷新列表：已清除选中并切回当前转录状态: {cur_name}")
        else:
            self.var_current_filename.set("未开始录音")
            self.lbl_status.config(text="列表已刷新，已取消文件选中", foreground=THEME["fg_sub"])
            logger.info("手动刷新列表：已清除选中，当前无转录工作流")

    def on_listbox_select(self, event):
        """当选中左侧列表中的单个文件时，自动将文件名同步到编辑区旁边的填入框"""
        w = event.widget
        sel = w.curselection()
        if len(sel) == 1:
            idx = sel[0]
            filename = w.get(idx)
            folder = RECORD_DIR if w == self.lst_rec else RESULT_DIR
            self.active_selected_file = os.path.join(folder, filename)

            clean_name = filename
            if clean_name.startswith("ok]"):
                clean_name = clean_name[3:]
            name_no_ext, _ = os.path.splitext(clean_name)
            self.var_current_filename.set(name_no_ext)
            logger.info(f"选中单个文件: {self.active_selected_file}，填入框同步为: {name_no_ext}")

    def save_or_rename_filename(self):
        """保存当前录音文件名或对选中的单个文件执行快捷重命名"""
        new_name = self.var_current_filename.get().strip()
        if not new_name:
            self.lbl_status.config(text="文件名称不能为空", foreground=THEME["warning"])
            return

        # 过滤非法字符
        for ch in r'/\:*?"<>|':
            new_name = new_name.replace(ch, "_")
        self.var_current_filename.set(new_name)

        # 场景 1：当前正在录音中 -> 设定本次录音的最终落盘名称
        if self.is_listening:
            self.custom_session_name = new_name
            self.lbl_status.config(text=f"已设定本次录音文件名为: {new_name}", foreground=THEME["success"])
            logger.info(f"录音进行中，已设定本次会话自定义名称: {new_name}")
            return

        # 场景 2：当前选中了左侧单个已有文件 -> 执行快捷重命名并协同配对文件
        if hasattr(self, 'active_selected_file') and self.active_selected_file and os.path.exists(self.active_selected_file):
            old_path = self.active_selected_file
            d = os.path.dirname(old_path)
            old_filename = os.path.basename(old_path)
            ext = os.path.splitext(old_filename)[1]
            prefix = "ok]" if old_filename.startswith("ok]") else ""
            new_filename = f"{prefix}{new_name}{ext}"
            new_path = os.path.join(d, new_filename)

            if old_path != new_path:
                try:
                    os.rename(old_path, new_path)
                    self.active_selected_file = new_path
                    logger.info(f"文件快捷重命名成功: {old_path} -> {new_path}")

                    # 协同联动：如果存在对应的配对文件（录音 <-> Markdown），一并协同重命名
                    old_base = old_filename[3:] if old_filename.startswith("ok]") else os.path.splitext(old_filename)[0]
                    if old_path.startswith(RECORD_DIR):
                        pair_md = os.path.join(RESULT_DIR, f"{old_base}.md")
                        if os.path.exists(pair_md):
                            pair_new_md = os.path.join(RESULT_DIR, f"{new_name}.md")
                            try:
                                os.rename(pair_md, pair_new_md)
                                logger.info(f"协同重命名关联转录文件: {pair_md} -> {pair_new_md}")
                            except Exception: pass
                    elif old_path.startswith(RESULT_DIR):
                        pair_wav = os.path.join(RECORD_DIR, f"ok]{old_base}.wav")
                        if os.path.exists(pair_wav):
                            pair_new_wav = os.path.join(RECORD_DIR, f"ok]{new_name}.wav")
                            try:
                                os.rename(pair_wav, pair_new_wav)
                                logger.info(f"协同重命名关联录音文件: {pair_wav} -> {pair_new_wav}")
                            except Exception: pass

                    self.refresh_files()
                    self.lbl_status.config(text=f"已成功重命名为: {new_name}", foreground=THEME["success"])
                    return
                except Exception as e:
                    logger.error(f"重命名文件失败: {e}", exc_info=True)
                    self.lbl_status.config(text="重命名失败", foreground=THEME["danger"])
                    return
            else:
                self.lbl_status.config(text="文件名未发生变动", foreground=THEME["fg_sub"])
                return

        # 场景 3：未在录音且未选中具体文件 -> 预设下一次录音名称
        self.custom_session_name = new_name
        self.lbl_status.config(text=f"已预设下一次录音名称为: {new_name}", foreground=THEME["success"])

    def get_sel_paths(self, w):
        d = RECORD_DIR if w == self.lst_rec else RESULT_DIR
        return [os.path.join(d, w.get(i)) for i in w.curselection()]

    def show_file_menu(self, e):
        w = e.widget; idx = w.nearest(e.y)
        if idx not in w.curselection(): w.selection_clear(0, tk.END); w.selection_set(idx)
        self.active_list = w
        self.m_file.tk_popup(e.x_root, e.y_root)

    def show_text_menu(self, e): self.m_txt.tk_popup(e.x_root, e.y_root)
    def copy_selection(self):
        try: self.root.clipboard_append(self.txt.get("sel.first", "sel.last"))
        except: pass

    def menu_open(self):
        if not self.active_list:
            return
        for p in self.get_sel_paths(self.active_list): subprocess.run(["open", p])
    def dbl_click_open(self, e):
        self.active_list = e.widget
        self.menu_open()
    def menu_copy_file(self):
        ps = self.get_sel_paths(self.active_list)
        if ps:
            fl = ", ".join([f'POSIX file "{p}"' for p in ps])
            os.system(f"osascript -e 'set the clipboard to {{{fl}}}'")
    def menu_reveal(self):
        ps = self.get_sel_paths(self.active_list)
        if ps: subprocess.run(["open", "-R", ps[0]])
    def menu_delete(self):
        for p in self.get_sel_paths(self.active_list): os.remove(p)
        self.refresh_files()
    def menu_rename(self):
        ps = self.get_sel_paths(self.active_list)
        if ps:
            p = ps[0]
            new = simpledialog.askstring("重命名", "新名:", initialvalue=os.path.basename(p))
            if new: os.rename(p, os.path.join(os.path.dirname(p), new)); self.refresh_files()
    def transcribe_sel(self):
        ps = self.get_sel_paths(self.lst_rec)
        for p in ps: self.asr_queue.put(("TRANSCRIBE_FILE", p))
        self.lbl_status.config(text="已加入批量队列", foreground=THEME["accent"])

if __name__ == "__main__":
    root = tk.Tk()
    app = UltimateASR(root)
    root.mainloop()
