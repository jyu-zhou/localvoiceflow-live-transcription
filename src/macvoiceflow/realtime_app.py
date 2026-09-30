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
import shutil
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
if sys.platform == "darwin":
    os.environ["PATH"] = os.pathsep.join(filter(None, ["/opt/homebrew/bin", os.environ.get("PATH", "")]))
warnings.filterwarnings("ignore")

# === 1. 路径与常量配置 ===
APP_NAME = "LocalVoiceFlow"
LEGACY_APP_NAME = "MacVoiceFlow"
APP_VERSION = "0.3.0"


def _expand_path(value):
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def _default_data_root():
    current = Path.home() / "Documents" / APP_NAME
    legacy = Path.home() / "Documents" / LEGACY_APP_NAME
    return legacy if legacy.exists() and not current.exists() else current


def _default_cache_root():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    if sys.platform == "darwin":
        current = Path.home() / "Library" / "Caches" / APP_NAME
        legacy = Path.home() / "Library" / "Caches" / LEGACY_APP_NAME
        return legacy if legacy.exists() and not current.exists() else current
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


DATA_ROOT = _expand_path(
    os.environ.get("LOCALVOICEFLOW_DATA_DIR")
    or os.environ.get("MACVOICEFLOW_DATA_DIR")
    or str(_default_data_root())
)
CACHE_ROOT = _expand_path(
    os.environ.get("LOCALVOICEFLOW_CACHE_DIR")
    or os.environ.get("MACVOICEFLOW_CACHE_DIR")
    or str(_default_cache_root())
)
os.environ.setdefault("HF_HOME", str(CACHE_ROOT / "huggingface"))

BASE_DIR = str(DATA_ROOT)
TEMP_DIR = str(DATA_ROOT / "TempChunks")
RECORD_DIR = str(DATA_ROOT / "Record")
RESULT_PATH = DATA_ROOT / "Transcripts"
LEGACY_RESULT_PATH = DATA_ROOT / "转录结果"
RESULT_DIR = str(RESULT_PATH)
LOG_FILE = str(DATA_ROOT / "app.log")
CONFIG_FILE = str(DATA_ROOT / "config.json")

DEFAULT_SETTINGS = {
    "ui_language": "en",
    "model": "qwen-1.7b-4bit",
    "language": "zh",
    "max_lines": "3000",
    "max_segment_duration": 10.0,
    "vad_threshold": 0.006,
    "pause_duration": 0.8
}

def migrate_legacy_result_dir():
    """Move the former Chinese result directory without overwriting user files."""
    if not LEGACY_RESULT_PATH.exists():
        return
    try:
        if not RESULT_PATH.exists():
            LEGACY_RESULT_PATH.rename(RESULT_PATH)
            return

        for item in sorted(LEGACY_RESULT_PATH.iterdir(), key=lambda path: path.name):
            target = RESULT_PATH / item.name
            if target.exists():
                index = 2
                while True:
                    target = RESULT_PATH / f"{item.stem} (legacy {index}){item.suffix}"
                    if not target.exists():
                        break
                    index += 1
            shutil.move(str(item), str(target))
        LEGACY_RESULT_PATH.rmdir()
    except OSError as exc:
        print(f"[{APP_NAME}] Could not migrate legacy transcript folder: {exc}", file=sys.stderr)


migrate_legacy_result_dir()

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

# 模型库：macOS 使用 MLX，Windows 使用 CrispASR + Qwen3-ASR GGUF。
PLATFORM_KEY = "windows" if os.name == "nt" else "macos"
MODEL_OPTIONS = {
    "qwen-1.7b-4bit": {
        "en": "1.7B · 4-bit / Q4_K (Recommended)",
        "zh": "1.7B · 4-bit / Q4_K（默认/推荐）",
        "legacy": {"1.7B-4bit (默认/推荐)"},
        "macos": {"backend": "mlx", "id": "mlx-community/Qwen3-ASR-1.7B-4bit"},
        "windows": {
            "backend": "crispasr",
            "repo_id": "cstr/qwen3-asr-1.7b-GGUF",
            "filename": "qwen3-asr-1.7b-q4_k.gguf",
        },
    },
    "qwen-1.7b-8bit": {
        "en": "1.7B · 8-bit / Q8_0 (Higher precision)",
        "zh": "1.7B · 8-bit / Q8_0（高精度）",
        "legacy": {"1.7B-8bit (高精)"},
        "macos": {"backend": "mlx", "id": "mlx-community/Qwen3-ASR-1.7B-8bit"},
        "windows": {
            "backend": "crispasr",
            "repo_id": "cstr/qwen3-asr-1.7b-GGUF",
            "filename": "qwen3-asr-1.7b-q8_0.gguf",
        },
    },
    "qwen-0.6b-8bit": {
        "en": "0.6B · compact / Q4_K (Faster)",
        "zh": "0.6B · 轻量 / Q4_K（更快）",
        "legacy": {"0.6B-8bit (极速)"},
        "macos": {"backend": "mlx", "id": "mlx-community/Qwen3-ASR-0.6B-8bit"},
        "windows": {
            "backend": "crispasr",
            "repo_id": "cstr/qwen3-asr-0.6b-GGUF",
            "filename": "qwen3-asr-0.6b-q4_k.gguf",
        },
    },
}

UI_LANGUAGE_OPTIONS = {"English": "en", "中文": "zh"}
UI_LANGUAGE_LABELS = {code: label for label, code in UI_LANGUAGE_OPTIONS.items()}
OUTPUT_LANGUAGE_OPTIONS = [
    ("zh", "Chinese", "中文"),
    ("en", "English", "英语"),
    ("fr", "French", "法语"),
    ("ja", "Japanese", "日语"),
    ("ko", "Korean", "韩语"),
    ("de", "German", "德语"),
    ("es", "Spanish", "西语"),
    (None, "Auto", "自动"),
]

TEXT = {
    "en": {
        "app_title": "LocalVoiceFlow · Live Transcription",
        "ui_language": "Interface",
        "model": "Model",
        "output_language": "Transcription language",
        "max_lines": "Max lines",
        "max_segment_duration": "Max segment (sec)",
        "vad_threshold": "Mic threshold (VAD)",
        "pause_duration": "Pause to split (sec)",
        "defaults": "Defaults",
        "apply": "Apply",
        "initializing": "● Initializing...",
        "recordings": "Recordings",
        "results": "Transcripts",
        "open": "Open",
        "batch_transcribe": "Batch transcribe",
        "refresh": "Refresh",
        "live_editor": "Live transcript / editor",
        "file_name": "File name:",
        "save_name": "Save name",
        "queue_idle": "Queue idle",
        "microphone_ready": "Microphone ready",
        "start_recording": "Start recording",
        "pause": "Pause",
        "resume": "Resume",
        "stop_save": "Stop & save",
        "open_play": "Open / play",
        "copy_file": "Copy file",
        "show_in_finder": "Show in File Explorer" if os.name == "nt" else "Show in Finder",
        "rename": "Rename",
        "delete_selected": "Delete selected",
        "copy_selection": "Copy selection",
        "clear": "Clear",
        "model_loading": "Loading model...",
        "model_ready": "Model ready",
        "model_load_failed": "Model failed to load",
        "recording": "Recording",
        "recording_buffering": "Recording · waiting for model",
        "mic_start_failed": "Microphone unavailable",
        "organizing": "Organizing files...",
        "saved_name": "Saved: {name}",
        "save_failed": "Save failed",
        "recording_empty": "Recording empty",
        "paused": "Paused",
        "recording_listening": "Listening",
        "recording_speaking": "Listening · speech detected",
        "ambient_silence": "Ambient silence",
        "queue_backlog": "Queue: {count}",
        "invalid_values": "Invalid value(s); defaults restored",
        "settings_applied": "Settings applied",
        "settings_reset": "Defaults restored",
        "current_transcript": "Current transcript: {name}",
        "list_refreshed": "List refreshed",
        "list_refreshed_no_selection": "List refreshed · no file selected",
        "file_name_required": "File name cannot be empty",
        "filename_set": "Name set for this recording: {name}",
        "renamed": "Renamed: {name}",
        "rename_failed": "Rename failed",
        "filename_unchanged": "Name unchanged",
        "filename_preset": "Next recording name: {name}",
        "batch_queued": "Added to transcription queue",
        "rename_dialog_title": "Rename",
        "rename_dialog_prompt": "New name:",
        "not_started": "Not started",
        "recording_file_prefix": "Recording",
        "characters": "Characters: {count:,}",
        "draft_title": "Live transcript draft - {timestamp}",
        "transcript_file": "File",
        "transcript_time": "Time",
    },
    "zh": {
        "app_title": "LocalVoiceFlow · 实时转录",
        "ui_language": "界面语言",
        "model": "模型引擎",
        "output_language": "转录语言",
        "max_lines": "最大行数",
        "max_segment_duration": "最长单句（秒）",
        "vad_threshold": "麦克风阈值（VAD）",
        "pause_duration": "断句停顿（秒）",
        "defaults": "默认设置",
        "apply": "应用设置",
        "initializing": "● 系统初始化...",
        "recordings": "原始录音",
        "results": "转录结果",
        "open": "打开",
        "batch_transcribe": "批量转译",
        "refresh": "刷新列表",
        "live_editor": "实时转录 / 编辑区",
        "file_name": "文件名称:",
        "save_name": "保存名称",
        "queue_idle": "队列空闲",
        "microphone_ready": "麦克风待命",
        "start_recording": "开始录音",
        "pause": "暂停",
        "resume": "继续",
        "stop_save": "停止并保存",
        "open_play": "打开 / 播放",
        "copy_file": "复制文件",
        "show_in_finder": "在文件资源管理器中显示" if os.name == "nt" else "在 Finder 中显示",
        "rename": "重命名",
        "delete_selected": "删除选中",
        "copy_selection": "复制选中",
        "clear": "清空",
        "model_loading": "模型加载中...",
        "model_ready": "模型就绪",
        "model_load_failed": "加载失败",
        "recording": "录音中",
        "recording_buffering": "录音中（等待模型）",
        "mic_start_failed": "麦克风启动失败",
        "organizing": "整理文件中...",
        "saved_name": "已保存: {name}",
        "save_failed": "保存失败",
        "recording_empty": "录音无内容",
        "paused": "已暂停",
        "recording_listening": "正在收音",
        "recording_speaking": "正在收音（说话中）",
        "ambient_silence": "环境静音中",
        "queue_backlog": "队列积压: {count}",
        "invalid_values": "数值无效，已恢复默认并保存",
        "settings_applied": "设置已应用并保存",
        "settings_reset": "已恢复默认设置",
        "current_transcript": "已切回当前转录状态: {name}",
        "list_refreshed": "列表已刷新",
        "list_refreshed_no_selection": "列表已刷新，已取消文件选中",
        "file_name_required": "文件名称不能为空",
        "filename_set": "已设定本次录音文件名为: {name}",
        "renamed": "已成功重命名为: {name}",
        "rename_failed": "重命名失败",
        "filename_unchanged": "文件名未发生变动",
        "filename_preset": "已预设下一次录音名称为: {name}",
        "batch_queued": "已加入批量队列",
        "rename_dialog_title": "重命名",
        "rename_dialog_prompt": "新名:",
        "not_started": "未开始录音",
        "recording_file_prefix": "录音",
        "characters": "字数: {count:,}",
        "draft_title": "录音实时转写草稿 - {timestamp}",
        "transcript_file": "文件",
        "transcript_time": "时间",
    },
}


def normalize_ui_language(value):
    if value in UI_LANGUAGE_OPTIONS.values():
        return value
    return UI_LANGUAGE_OPTIONS.get(value, "en")


def normalize_output_language(value):
    valid_codes = {code for code, _, _ in OUTPUT_LANGUAGE_OPTIONS if code}
    if value in valid_codes or value is None:
        return value
    for code, english, chinese in OUTPUT_LANGUAGE_OPTIONS:
        if value in {english, chinese}:
            return code
    return "zh"


def normalize_model_key(value):
    if value in MODEL_OPTIONS:
        return value
    for key, option in MODEL_OPTIONS.items():
        if value in {option["en"], option["zh"], *option["legacy"]}:
            return key
    return "qwen-1.7b-4bit"


def model_spec(key):
    return MODEL_OPTIONS[normalize_model_key(key)][PLATFORM_KEY]


def model_identity(key):
    spec = model_spec(key)
    if spec["backend"] == "crispasr":
        return f"{spec['backend']}:{spec['repo_id']}:{spec['filename']}"
    return f"{spec['backend']}:{spec['id']}"


def open_path(path):
    """Open a file with the native file manager on each supported desktop."""
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def reveal_path(path):
    """Reveal a file in the native file manager when the platform supports it."""
    if os.name == "nt":
        subprocess.run(["explorer", "/select,", os.path.normpath(path)], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    else:
        open_path(os.path.dirname(path))

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
        self.root.geometry("1400x950")
        self.root.configure(bg=THEME["bg_main"])

        # --- 核心状态 ---
        self.is_listening = False
        self.is_paused = False
        self.audio_queue = queue.Queue()
        self.asr_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.settings = self.load_settings()
        self.ui_language = normalize_ui_language(self.settings.get("ui_language", "en"))
        self.current_lang = normalize_output_language(self.settings.get("language", "zh"))
        self.current_model_key = normalize_model_key(self.settings.get("model", DEFAULT_SETTINGS["model"]))
        self.loading_model_id = ""
        self.status_key = "initializing"
        self.status_args = {}
        self.status_color = THEME["fg_sub"]
        self.last_vu_level = 0.0
        self.last_vu_active = False
        self.ui_widgets = {}

        self.full_recording = []
        self.vad_buffer = []
        self.model = None
        self.current_model_id = ""
        self.model_backend = ""
        self.speech_active = False

        # 实时会话与文件状态
        self.current_live_md = None
        self.current_session_ts = ""
        self.last_q_size = -1
        self.var_current_filename = tk.StringVar(value=self.t("not_started"))
        self.active_selected_file = None
        self.active_list = None
        self.custom_session_name = ""
        self.var_char_count = tk.StringVar(value=self.t("characters", count=0))
        self.var_rec_timer = tk.StringVar(value="00:00:00")
        self.record_start_time = 0
        self.total_chars_accumulated = 0

        # UI 与性能参数持久化 (全部支持填入框绑定与校验)
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
        self.cb_ui_lang.set(UI_LANGUAGE_LABELS[self.ui_language])
        self.cb_model.set(self.model_label(self.current_model_key))
        self.cb_lang.set(self.output_language_label(self.current_lang))
        self._on_lang_change(persist=False)
        self.apply_language()
        self.refresh_files()
        self._cleanup_old_temp_chunks()

        # 异步加载
        self.root.after(300, self.trigger_model_switch)

    def t(self, key, **kwargs):
        template = TEXT.get(self.ui_language, TEXT["en"]).get(key, key)
        return template.format(**kwargs) if kwargs else template

    def model_label(self, key):
        return MODEL_OPTIONS[normalize_model_key(key)][self.ui_language]

    def model_values(self):
        return [option[self.ui_language] for option in MODEL_OPTIONS.values()]

    def model_key_from_value(self, value):
        return normalize_model_key(value)

    def output_language_label(self, code):
        for option_code, english, chinese in OUTPUT_LANGUAGE_OPTIONS:
            if option_code == code:
                return english if self.ui_language == "en" else chinese
        return "Auto" if self.ui_language == "en" else "自动"

    def output_language_values(self):
        return [self.output_language_label(code) for code, _, _ in OUTPUT_LANGUAGE_OPTIONS]

    def set_status(self, key, color, **kwargs):
        self.status_key = key
        self.status_args = kwargs
        self.status_color = color
        if hasattr(self, "lbl_status"):
            self.lbl_status.config(text=self.t(key, **kwargs), foreground=color)

    def set_queue_status(self, count):
        self.last_q_size = count
        if hasattr(self, "lbl_queue"):
            text = self.t("queue_idle") if count <= 0 else self.t("queue_backlog", count=count)
            color = THEME["success"] if count <= 0 else THEME["warning"]
            self.lbl_queue.config(text=text, foreground=color)

    def apply_language(self):
        """Update all visible copy without rebuilding the existing single-workspace layout."""
        if not hasattr(self, "cb_ui_lang"):
            return

        self.root.title(self.t("app_title"))
        self.cb_ui_lang["values"] = list(UI_LANGUAGE_OPTIONS.keys())
        self.cb_ui_lang.set(UI_LANGUAGE_LABELS[self.ui_language])
        self.cb_model["values"] = self.model_values()
        self.cb_model.set(self.model_label(self.current_model_key))
        self.cb_lang["values"] = self.output_language_values()
        self.cb_lang.set(self.output_language_label(self.current_lang))

        for key, widget in self.ui_widgets.items():
            widget.config(text=self.t(key))

        self.lbl_rec_header.config(text=self.t("recordings"))
        self.btn_open_record.config(text=self.t("open"))
        self.btn_batch.config(text=self.t("batch_transcribe"))
        self.btn_refresh.config(text=self.t("refresh"))
        self.lbl_res_header.config(text=self.t("results"))
        self.btn_open_results.config(text=self.t("open"))
        self.btn_pause.config(text=self.t("resume" if self.is_paused else "pause"))

        if self.var_current_filename.get() in {"Not started", "未开始录音"}:
            self.var_current_filename.set(self.t("not_started"))
        self.var_char_count.set(self.t("characters", count=self.total_chars_accumulated))
        self.set_status(self.status_key, self.status_color, **self.status_args)
        self.set_queue_status(self.last_q_size)
        self.update_vu_meter(self.last_vu_level, self.last_vu_active)

        self.m_file.entryconfigure(0, label=self.t("open_play"))
        self.m_file.entryconfigure(1, label=self.t("copy_file"))
        self.m_file.entryconfigure(3, label=self.t("show_in_finder"))
        self.m_file.entryconfigure(4, label=self.t("rename"))
        self.m_file.entryconfigure(5, label=self.t("delete_selected"))
        self.m_txt.entryconfigure(0, label=self.t("copy_selection"))
        self.m_txt.entryconfigure(1, label=self.t("clear"))

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
                "ui_language": getattr(self, "ui_language", DEFAULT_SETTINGS["ui_language"]),
                "model": self.model_key_from_value(self.cb_model.get()) if hasattr(self, 'cb_model') else DEFAULT_SETTINGS["model"],
                "language": getattr(self, "current_lang", DEFAULT_SETTINGS["language"]),
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
                self.set_status("invalid_values", THEME["warning"])
            else:
                self.set_status("settings_applied", THEME["success"])

    def reset_to_default_settings(self):
        logger.info("重置为默认设置")
        self.ui_language = DEFAULT_SETTINGS["ui_language"]
        self.current_model_key = DEFAULT_SETTINGS["model"]
        self.current_lang = DEFAULT_SETTINGS["language"]
        self.cb_ui_lang.set(UI_LANGUAGE_LABELS[self.ui_language])
        self.cb_model.set(self.model_label(self.current_model_key))
        self.cb_lang.set(self.output_language_label(self.current_lang))
        self.var_max_lines.set(str(DEFAULT_SETTINGS["max_lines"]))
        self.var_max_dur.set(str(DEFAULT_SETTINGS["max_segment_duration"]))
        self.var_vad_threshold.set(str(DEFAULT_SETTINGS["vad_threshold"]))
        self.var_pause_duration.set(str(DEFAULT_SETTINGS["pause_duration"]))
        self.max_segment_duration = DEFAULT_SETTINGS["max_segment_duration"]
        self.silence_threshold = DEFAULT_SETTINGS["vad_threshold"]
        self.silence_duration = DEFAULT_SETTINGS["pause_duration"]
        self._on_lang_change(persist=False)
        self.apply_language()
        self.trigger_model_switch()
        self.save_settings()
        self.set_status("settings_reset", THEME["success"])

    def poll_ui_queue(self):
        try:
            while not self.ui_queue.empty():
                msg = self.ui_queue.get_nowait()
                mtype = msg[0]
                if mtype == "TEXT":
                    self.append_text(msg[1])
                elif mtype == "STATUS_KEY":
                    self.set_status(msg[1], msg[2], **(msg[3] if len(msg) > 3 else {}))
                elif mtype == "PROGRESS":
                    mode, val, action = msg[1], msg[2], msg[3]
                    if action == "start":
                        self.progress.config(mode=mode)
                        self.progress.start(val)
                    elif action == "stop":
                        self.progress.stop()
                        self.progress.config(mode=mode, value=val)
                elif mtype == "QUEUE_LABEL":
                    self.set_queue_status(msg[1])
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
        self.last_vu_level = level
        self.last_vu_active = is_active
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
                    self.lbl_vu_hint.config(text=self.t("recording_speaking"), foreground=THEME["success"])
                else:
                    self.lbl_vu_hint.config(text=self.t("ambient_silence"), foreground=THEME["fg_sub"])
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
        if self.model:
            try:
                close = getattr(self.model, "close", None)
                if close:
                    close()
            except Exception:
                pass
        self.root.destroy()

    def _on_ui_language_change(self, event=None):
        self.ui_language = normalize_ui_language(self.cb_ui_lang.get())
        self.apply_language()
        self.save_settings()
        logger.info(f"界面语言切换为: {self.ui_language}")

    def _on_lang_change(self, event=None, persist=True):
        self.current_lang = normalize_output_language(self.cb_lang.get())
        if persist:
            self.save_settings()
        logger.info(f"转录语言配置切换为: {self.current_lang}")

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
        for column in range(9):
            top.columnconfigure(column, weight=0)
        top.columnconfigure(7, weight=1)

        self.lbl_ui_language = ttk.Label(top, text=self.t("ui_language"), style="Sub.TLabel")
        self.lbl_ui_language.grid(row=0, column=0, sticky="w", padx=(6, 10))
        self.ui_widgets["ui_language"] = self.lbl_ui_language
        self.cb_ui_lang = ttk.Combobox(top, values=list(UI_LANGUAGE_OPTIONS.keys()), state="readonly", width=10)
        self.cb_ui_lang.grid(row=1, column=0, sticky="w", padx=(6, 10), pady=(3, 0))
        self.cb_ui_lang.bind("<<ComboboxSelected>>", self._on_ui_language_change)

        self.lbl_model = ttk.Label(top, text=self.t("model"), style="Sub.TLabel")
        self.lbl_model.grid(row=0, column=1, sticky="w", padx=10)
        self.ui_widgets["model"] = self.lbl_model
        self.cb_model = ttk.Combobox(top, values=self.model_values(), state="readonly", width=24)
        self.cb_model.grid(row=1, column=1, sticky="w", padx=10, pady=(3, 0))
        self.cb_model.bind("<<ComboboxSelected>>", self.trigger_model_switch)

        self.lbl_output_language = ttk.Label(top, text=self.t("output_language"), style="Sub.TLabel")
        self.lbl_output_language.grid(row=0, column=2, sticky="w", padx=10)
        self.ui_widgets["output_language"] = self.lbl_output_language
        self.cb_lang = ttk.Combobox(top, values=self.output_language_values(), state="readonly", width=10)
        self.cb_lang.grid(row=1, column=2, sticky="w", padx=10, pady=(3, 0))
        self.cb_lang.bind("<<ComboboxSelected>>", self._on_lang_change)

        self.lbl_max_lines = ttk.Label(top, text=self.t("max_lines"), style="Sub.TLabel")
        self.lbl_max_lines.grid(row=0, column=3, sticky="w", padx=10)
        self.ui_widgets["max_lines"] = self.lbl_max_lines
        self.entry_max_lines = ttk.Entry(top, textvariable=self.var_max_lines, width=7)
        self.entry_max_lines.grid(row=1, column=3, sticky="w", padx=10, pady=(3, 0))
        self.entry_max_lines.bind("<Return>", lambda e: self.apply_settings())

        self.lbl_max_duration = ttk.Label(top, text=self.t("max_segment_duration"), style="Sub.TLabel")
        self.lbl_max_duration.grid(row=0, column=4, sticky="w", padx=10)
        self.ui_widgets["max_segment_duration"] = self.lbl_max_duration
        self.entry_max_dur = ttk.Entry(top, textvariable=self.var_max_dur, width=7)
        self.entry_max_dur.grid(row=1, column=4, sticky="w", padx=10, pady=(3, 0))
        self.entry_max_dur.bind("<Return>", lambda e: self.apply_settings())

        self.lbl_vad = ttk.Label(top, text=self.t("vad_threshold"), style="Sub.TLabel")
        self.lbl_vad.grid(row=0, column=5, sticky="w", padx=10)
        self.ui_widgets["vad_threshold"] = self.lbl_vad
        self.entry_vad_thresh = ttk.Entry(top, textvariable=self.var_vad_threshold, width=7)
        self.entry_vad_thresh.grid(row=1, column=5, sticky="w", padx=10, pady=(3, 0))
        self.entry_vad_thresh.bind("<Return>", lambda e: self.apply_settings())

        self.lbl_pause = ttk.Label(top, text=self.t("pause_duration"), style="Sub.TLabel")
        self.lbl_pause.grid(row=0, column=6, sticky="w", padx=10)
        self.ui_widgets["pause_duration"] = self.lbl_pause
        self.entry_pause_dur = ttk.Entry(top, textvariable=self.var_pause_duration, width=7)
        self.entry_pause_dur.grid(row=1, column=6, sticky="w", padx=10, pady=(3, 0))
        self.entry_pause_dur.bind("<Return>", lambda e: self.apply_settings())
        f_btns = ttk.Frame(top, style="Card.TFrame")
        f_btns.grid(row=0, column=7, rowspan=2, sticky="e", padx=(10, 16))
        self.btn_reset_cfg = ttk.Button(f_btns, text=self.t("defaults"), style="Small.TButton", command=self.reset_to_default_settings)
        self.btn_reset_cfg.pack(fill=tk.X, pady=(0, 2))
        self.ui_widgets["defaults"] = self.btn_reset_cfg
        self.btn_apply_cfg = ttk.Button(f_btns, text=self.t("apply"), style="Action.TButton", command=self.apply_settings)
        self.btn_apply_cfg.pack(fill=tk.X, pady=(2, 0))
        self.ui_widgets["apply"] = self.btn_apply_cfg

        self.lbl_status = ttk.Label(top, text=self.t("initializing"), style="H1.TLabel", foreground=THEME["fg_sub"])
        self.lbl_status.grid(row=0, column=8, rowspan=2, sticky="e", padx=(10, 4))

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=THEME["bg_main"], sashwidth=2, bd=0)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

        left = ttk.Frame(paned, style="Card.TFrame")
        paned.add(left, width=380)

        self.lbl_rec_header, self.btn_open_record = self._create_header(left, "recordings", btn_key="open", btn_cmd=lambda: open_path(RECORD_DIR))
        self.lst_rec = self._create_listbox(left)
        self.lst_rec.pack(fill=tk.BOTH, expand=True, padx=12)
        self.btn_batch, self.btn_refresh = self._create_toolbar(left, "batch_transcribe", self.transcribe_sel, "refresh", self.on_manual_refresh)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=16, pady=8)

        self.lbl_res_header, self.btn_open_results = self._create_header(left, "results", btn_key="open", btn_cmd=lambda: open_path(RESULT_DIR))
        self.lst_res = self._create_listbox(left)
        self.lst_res.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        right = ttk.Frame(paned, style="Card.TFrame")
        paned.add(right)

        f_head_right = ttk.Frame(right, style="Card.TFrame")
        f_head_right.pack(fill=tk.X, padx=16, pady=(14, 6))
        self.lbl_live_header = ttk.Label(f_head_right, text=self.t("live_editor"), style="H1.TLabel")
        self.lbl_live_header.pack(side=tk.LEFT)
        self.ui_widgets["live_editor"] = self.lbl_live_header

        self.lbl_filename = ttk.Label(f_head_right, text=self.t("file_name"), style="Sub.TLabel")
        self.lbl_filename.pack(side=tk.LEFT, padx=(18, 5))
        self.ui_widgets["file_name"] = self.lbl_filename
        self.entry_filename = ttk.Entry(f_head_right, textvariable=self.var_current_filename, width=22)
        self.entry_filename.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_filename.bind("<Return>", lambda e: self.save_or_rename_filename())

        self.btn_save_filename = ttk.Button(f_head_right, text=self.t("save_name"), style="Action.TButton", command=self.save_or_rename_filename)
        self.btn_save_filename.pack(side=tk.LEFT, padx=(0, 12))
        self.ui_widgets["save_name"] = self.btn_save_filename

        f_indicators = ttk.Frame(f_head_right, style="Card.TFrame")
        f_indicators.pack(side=tk.RIGHT)

        self.lbl_queue = ttk.Label(f_indicators, text=self.t("queue_idle"), style="Badge.TLabel", foreground=THEME["success"])
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

        self.lbl_vu_hint = ttk.Label(f_vu, text=self.t("microphone_ready"), style="Sub.TLabel")
        self.lbl_vu_hint.pack(side=tk.RIGHT)

        f_actions = ttk.Frame(btm, style="Card.TFrame")
        f_actions.pack(fill=tk.X)

        self.btn_start = ttk.Button(f_actions, text=self.t("start_recording"), style="Accent.TButton", command=self.start_rec)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ui_widgets["start_recording"] = self.btn_start

        self.btn_pause = ttk.Button(f_actions, text=self.t("pause"), style="Normal.TButton", command=self.toggle_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.ui_widgets["pause"] = self.btn_pause

        self.btn_stop = ttk.Button(f_actions, text=self.t("stop_save"), style="Danger.TButton", command=self.stop_rec, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.ui_widgets["stop_save"] = self.btn_stop

        self.progress = ttk.Progressbar(self.root, style="Minimal.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(side=tk.BOTTOM, fill=tk.X)

    # === 辅助函数 ===
    def _create_header(self, p, title_key, btn_key=None, btn_cmd=None):
        f = ttk.Frame(p, style="Card.TFrame")
        f.pack(fill=tk.X, padx=15, pady=(15, 8))
        label = ttk.Label(f, text=self.t(title_key), style="H1.TLabel")
        label.pack(side=tk.LEFT)
        button = None
        if btn_key and btn_cmd:
            button = ttk.Button(f, text=self.t(btn_key), style="Normal.TButton", command=btn_cmd)
            button.pack(side=tk.RIGHT)
        return label, button

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

    def _create_toolbar(self, p, key1, c1, key2, c2):
        f = ttk.Frame(p, style="Card.TFrame", padding=(10, 10))
        f.pack(fill=tk.X)
        btn1 = ttk.Button(f, text=self.t(key1), style="Normal.TButton", command=c1)
        btn1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        btn2 = ttk.Button(f, text=self.t(key2), style="Normal.TButton", command=c2)
        btn2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        return btn1, btn2

    def setup_menus(self):
        self.m_file = Menu(self.root, tearoff=0)
        self.m_file.add_command(label=self.t("open_play"), command=self.menu_open)
        self.m_file.add_command(label=self.t("copy_file"), command=self.menu_copy_file)
        self.m_file.add_separator()
        self.m_file.add_command(label=self.t("show_in_finder"), command=self.menu_reveal)
        self.m_file.add_command(label=self.t("rename"), command=self.menu_rename)
        self.m_file.add_command(label=self.t("delete_selected"), command=self.menu_delete)
        self.m_txt = Menu(self.root, tearoff=0)
        self.m_txt.add_command(label=self.t("copy_selection"), command=self.copy_selection)
        self.m_txt.add_command(label=self.t("clear"), command=lambda: self.txt.delete("1.0", tk.END))

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
        self.current_model_key = self.model_key_from_value(self.cb_model.get())
        mid = model_identity(self.current_model_key)
        self.save_settings()
        if mid == self.current_model_id or mid == self.loading_model_id:
            return
        self.loading_model_id = mid
        self.root.after(0, lambda: [
            self.set_status("model_loading", THEME["warning"]),
            self.progress.config(mode='indeterminate'),
            self.progress.start(10)
        ])
        self.asr_queue.put(("LOAD_MODEL", self.current_model_key))

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
        if cur_input and cur_input not in {"Not started", "未开始录音"}:
            self.custom_session_name = cur_input
        else:
            self.custom_session_name = f"{self.t('recording_file_prefix')}_{self.current_session_ts}"

        self.var_current_filename.set(self.custom_session_name)
        self.active_selected_file = None # 开启录音时脱离左侧文件选中

        # 初始化实时草稿文件，每识别一句即刻追加，杜绝断电或崩溃导致内容丢失
        self.current_live_md = os.path.join(RESULT_DIR, f"实时草稿_{self.current_session_ts}.md")
        try:
            with open(self.current_live_md, "w", encoding="utf-8") as f:
                f.write(f"# {self.t('draft_title', timestamp=self.current_session_ts)}\n\n")
        except Exception as e:
            logger.warning(f"初始化实时草稿文件失败: {e}")

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL, text=self.t("pause"))

        status_color = THEME["danger"] if self.model else THEME["warning"]
        self.set_status("recording" if self.model else "recording_buffering", status_color)

        # 启动工作台计时器与重置字数
        self.record_start_time = time.time()
        self.var_rec_timer.set("00:00:00")
        self.total_chars_accumulated = 0
        self.var_char_count.set(self.t("characters", count=0))
        if hasattr(self, 'lbl_rec_dot'):
            self.lbl_rec_dot.config(foreground=THEME["danger"])
        if hasattr(self, 'lbl_vu_hint'):
            self.lbl_vu_hint.config(text=self.t("recording_listening"), foreground=THEME["fg_sub"])
        self.root.after(1000, self._timer_tick)

        logger.info("开始录音，初始化音频输入流...")
        try:
            self.stream = sd.InputStream(callback=self.audio_cb, channels=1, samplerate=16000)
            self.stream.start()
            threading.Thread(target=self.loop, daemon=True, name="AudioVADLoop").start()
            logger.info("音频流启动成功")
        except Exception as e:
            logger.error(f"启动麦克风输入流失败: {e}", exc_info=True)
            self.set_status("mic_start_failed", THEME["danger"])
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

    # === ASR 专属单一工作线程（模型加载与转录全生命周期共用同一线程） ===
    def asr_worker(self):
        logger.info("ASR 专属工作线程已启动（平台后端: %s）", PLATFORM_KEY)
        while True:
            try:
                task = self.asr_queue.get()
                action, payload = task[0], task[1]

                if action == "LOAD_MODEL":
                    model_key = normalize_model_key(payload)
                    spec = model_spec(model_key)
                    mid = model_identity(model_key)
                    logger.info(f"ASR 线程开始加载模型: {mid}")
                    self.ui_queue.put(("STATUS_KEY", "model_loading", THEME["warning"]))
                    self.ui_queue.put(("PROGRESS", "indeterminate", 10, "start"))

                    if self.model:
                        try:
                            close = getattr(self.model, "close", None)
                            if close:
                                close()
                        except Exception as e:
                            logger.warning(f"释放旧模型异常: {e}")
                        del self.model
                        self.model = None
                    gc.collect()
                    if spec["backend"] == "mlx":
                        try:
                            import mlx.core as mx
                            if hasattr(mx, "clear_cache"):
                                mx.clear_cache()
                            elif hasattr(mx, "metal") and mx.metal.is_available() and hasattr(mx.metal, "clear_cache"):
                                mx.metal.clear_cache()
                        except Exception as e:
                            logger.warning(f"清除 MLX 缓存异常: {e}")

                    try:
                        if spec["backend"] == "mlx":
                            from mlx_audio.stt.utils import load_model
                            self.model = load_model(spec["id"])
                        else:
                            from huggingface_hub import hf_hub_download
                            from crispasr import Session
                            model_path = hf_hub_download(
                                repo_id=spec["repo_id"],
                                filename=spec["filename"],
                                cache_dir=str(CACHE_ROOT / "huggingface"),
                            )
                            thread_count = max(1, min(8, (os.cpu_count() or 4) // 2))
                            self.model = Session(model_path, n_threads=thread_count, backend="qwen3")
                        self.model_backend = spec["backend"]
                        self.current_model_id = mid
                        self.loading_model_id = ""
                        logger.info(f"ASR 线程模型加载成功: {mid}")
                        self.ui_queue.put(("STATUS_KEY", "model_ready", THEME["success"]))
                        self.ui_queue.put(("PROGRESS", "determinate", 0, "stop"))
                    except Exception as e:
                        self.current_model_id = ""
                        self.model_backend = ""
                        self.loading_model_id = ""
                        logger.error(f"模型加载失败 [{mid}]: {e}", exc_info=True)
                        self.ui_queue.put(("STATUS_KEY", "model_load_failed", THEME["danger"]))
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
                    self.ui_queue.put(("QUEUE_LABEL", q_size))
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
                if arr.ndim > 1:
                    arr = np.mean(arr, axis=1)
                if sr != 16000:
                    import librosa
                    arr = librosa.resample(arr, orig_sr=sr, target_sr=16000)
                arr = arr.astype(np.float32)
            else:
                # 内存切片
                arr = item.astype(np.float32).flatten()

            if len(arr) == 0:
                return

            # 安全读取当前语言变量，并使用当前平台对应的 ASR API。
            lang = self.current_lang
            if self.model_backend == "crispasr":
                segments = self.model.transcribe(
                    arr,
                    sample_rate=16000,
                    language=lang,
                )
                txt = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            else:
                kwargs = {'language': lang} if lang else {}
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
                            f.write(
                                f"# {base}\n**{self.t('transcript_file')}**: {item}\n"
                                f"**{self.t('transcript_time')}**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n{formatted}\n"
                            )
                        logger.info(f"批量文件转录结果已保存: {file_md}")
                        self.root.after(0, self.refresh_files)
                    except Exception as ef:
                        logger.warning(f"保存批量转录文件异常: {ef}")

        except Exception as e:
            logger.error(f"转录执行异常: {e}", exc_info=True)
        finally:
            # macOS MLX 需要主动清理缓存；Windows CrispASR 使用原生模型生命周期管理。
            if 'res' in locals():
                del res
            if self.model_backend == "mlx":
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
        self.set_status("organizing", THEME["accent"])
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
        elif input_name and input_name not in {"Not started", "未开始录音"}:
            default_name = input_name
        else:
            default_name = f"{self.t('recording_file_prefix')}_{ts}"

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
                    f.write(
                        f"# {default_name}\n**{self.t('transcript_time')}**: {ts}\n\n---\n\n{formatted_text}\n"
                    )

                # 清理临时实时草稿
                if self.current_live_md and os.path.exists(self.current_live_md):
                    try:
                        os.remove(self.current_live_md)
                    except Exception:
                        pass
                self.current_live_md = None

                self.refresh_files()
                self.set_status("saved_name", THEME["success"], name=default_name)
                logger.info(f"录音与规整文本已保存: {final_md}")
            except Exception as e:
                logger.error(f"规整转录文本异常: {e}", exc_info=True)
                self.set_status("save_failed", THEME["danger"])
        else:
            self.set_status("recording_empty", THEME["fg_sub"])
            self.current_live_md = None

        # 复位电平表与指示灯
        if hasattr(self, 'lbl_rec_dot'):
            self.lbl_rec_dot.config(foreground=THEME["fg_subtle"])
        self.update_vu_meter(0.0, False)
        if hasattr(self, 'lbl_vu_hint'):
            self.lbl_vu_hint.config(text=self.t("microphone_ready"), foreground=THEME["fg_sub"])

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        txt = self.t("resume" if self.is_paused else "pause")
        self.btn_pause.config(text=txt)
        if self.is_paused:
            if hasattr(self, 'lbl_rec_dot'):
                self.lbl_rec_dot.config(foreground=THEME["warning"])
            if hasattr(self, 'lbl_vu_hint'):
                self.lbl_vu_hint.config(text=self.t("paused"), foreground=THEME["warning"])
            self.update_vu_meter(0.0, False)
        else:
            if hasattr(self, 'lbl_rec_dot'):
                self.lbl_rec_dot.config(foreground=THEME["danger"])
            if hasattr(self, 'lbl_vu_hint'):
                self.lbl_vu_hint.config(text=self.t("recording_listening"), foreground=THEME["success"])
        self.set_status("paused" if self.is_paused else "recording", THEME["warning"] if self.is_paused else THEME["danger"])

    def append_text(self, t):
        ts = time.strftime("%H:%M:%S")
        # 带有标签的高保真渲染：时间戳弱化代码字体，正文使用自然屏显正文字体
        self.txt.insert(tk.END, f"[{ts}] ", "timestamp")
        self.txt.insert(tk.END, f"{t}\n", "content")

        # 实时字数累计更新
        self.total_chars_accumulated += len(t.strip())
        if hasattr(self, 'var_char_count'):
            self.var_char_count.set(self.t("characters", count=self.total_chars_accumulated))

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
                cur_name = f"{self.t('recording_file_prefix')}_{ts}"
                self.custom_session_name = cur_name
            self.var_current_filename.set(cur_name)
            self.set_status("current_transcript", THEME["accent"], name=cur_name)
            logger.info(f"手动刷新列表：已清除选中并切回当前转录状态: {cur_name}")
        else:
            self.var_current_filename.set(self.t("not_started"))
            self.set_status("list_refreshed_no_selection", THEME["fg_sub"])
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
            self.set_status("file_name_required", THEME["warning"])
            return

        # 过滤非法字符
        for ch in r'/\:*?"<>|':
            new_name = new_name.replace(ch, "_")
        self.var_current_filename.set(new_name)

        # 场景 1：当前正在录音中 -> 设定本次录音的最终落盘名称
        if self.is_listening:
            self.custom_session_name = new_name
            self.set_status("filename_set", THEME["success"], name=new_name)
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
                    self.set_status("renamed", THEME["success"], name=new_name)
                    return
                except Exception as e:
                    logger.error(f"重命名文件失败: {e}", exc_info=True)
                    self.set_status("rename_failed", THEME["danger"])
                    return
            else:
                self.set_status("filename_unchanged", THEME["fg_sub"])
                return

        # 场景 3：未在录音且未选中具体文件 -> 预设下一次录音名称
        self.custom_session_name = new_name
        self.set_status("filename_preset", THEME["success"], name=new_name)

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
        for p in self.get_sel_paths(self.active_list):
            open_path(p)
    def dbl_click_open(self, e):
        self.active_list = e.widget
        self.menu_open()
    def menu_copy_file(self):
        ps = self.get_sel_paths(self.active_list)
        if ps:
            if sys.platform == "darwin":
                fl = ", ".join([f'POSIX file "{p}"' for p in ps])
                os.system(f"osascript -e 'set the clipboard to {{{fl}}}'")
            else:
                self.root.clipboard_clear()
                self.root.clipboard_append("\n".join(ps))
    def menu_reveal(self):
        ps = self.get_sel_paths(self.active_list)
        if ps:
            reveal_path(ps[0])
    def menu_delete(self):
        for p in self.get_sel_paths(self.active_list): os.remove(p)
        self.refresh_files()
    def menu_rename(self):
        ps = self.get_sel_paths(self.active_list)
        if ps:
            p = ps[0]
            new = simpledialog.askstring(self.t("rename_dialog_title"), self.t("rename_dialog_prompt"), initialvalue=os.path.basename(p))
            if new: os.rename(p, os.path.join(os.path.dirname(p), new)); self.refresh_files()
    def transcribe_sel(self):
        ps = self.get_sel_paths(self.lst_rec)
        for p in ps: self.asr_queue.put(("TRANSCRIBE_FILE", p))
        self.set_status("batch_queued", THEME["accent"])

if __name__ == "__main__":
    root = tk.Tk()
    app = UltimateASR(root)
    root.mainloop()
