# LocalVoiceFlow — Local Live Transcription

[![Latest release](https://img.shields.io/github/v/release/jyu-zhou/localvoiceflow-live-transcription?display_name=tag)](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/latest)
[![License](https://img.shields.io/github/license/jyu-zhou/localvoiceflow-live-transcription)](LICENSE)

**A quiet, local-first desktop workspace for turning live speech into editable text.**

[中文说明](README.zh-CN.md)

## Install with an AI agent — recommended

Send the matching prompt to an agent that can run commands on your computer. The agent should use the repository's own installer, preserve existing files, create a Desktop shortcut, and launch the app once.

### Windows

```text
Please install LocalVoiceFlow on this Windows PC.

Repository:
https://github.com/jyu-zhou/localvoiceflow-live-transcription.git

Install it at:
%USERPROFILE%\Applications\LocalVoiceFlow

Please:
1. Verify Windows x64 and Python 3.11 or 3.12. If Python is missing, explain what is missing and stop.
2. Clone the repository if the target directory does not exist. If it is already a Git checkout, run `git status --porcelain`; if there are uncommitted changes, do not overwrite them and stop with a report. Otherwise run `git pull --ff-only`.
3. From the project directory, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DesktopShortcut`.
4. Confirm that a Desktop shortcut named `LocalVoiceFlow.lnk` exists and points to this checkout. If that name is already occupied, keep the existing file and report the alternate shortcut created by the installer.
5. Do not use Administrator privileges unless Windows itself requires them. Do not delete recordings, model caches, user data, or unrelated files. Do not change microphone privacy settings; tell me if Windows asks for permission.
6. Launch the Desktop shortcut once and report the project path, shortcut path, and any model-download prompt.
```

### macOS

```text
Please install LocalVoiceFlow on this Apple Silicon Mac.

Repository:
https://github.com/jyu-zhou/localvoiceflow-live-transcription.git

Install it at:
~/Applications/LocalVoiceFlow

Please:
1. Verify Apple Silicon macOS and Python 3.11 or 3.12 with Tk support. If either is missing, explain what is missing and stop.
2. Clone the repository if the target directory does not exist. If it is already a Git checkout, run `git status --porcelain`; if there are uncommitted changes, do not overwrite them and stop with a report. Otherwise run `git pull --ff-only`.
3. From the project directory, run `./scripts/install.sh --desktop-shortcut`.
4. Confirm that a Desktop shortcut named `LocalVoiceFlow.command` exists and points to this checkout. If that name is already occupied, keep the existing file and report the alternate shortcut created by the installer.
5. Do not use sudo. Do not delete recordings, model caches, user data, or unrelated files. Do not change macOS privacy settings; tell me if microphone permission is requested.
6. Launch the Desktop shortcut once and report the project path, shortcut path, and any model-download prompt.
```

These prompts are intentionally conservative: they do not pipe an unreviewed remote script into a shell and they stop before touching a working checkout with uncommitted changes.

## What LocalVoiceFlow is

LocalVoiceFlow is a focused desktop app for people who want to speak first and shape the text immediately afterward. The transcript appears while you talk, stays editable during the session, and can be saved together with the original audio as a Markdown file.

It is intentionally one thing: a dependable local workspace for live transcription.

## What it does

- **Live transcription** — turns short audio segments into text as you speak.
- **Instant editing** — keeps the transcript in an editable workspace instead of a read-only result page.
- **One clear flow** — start, pause, resume, stop, name, and save.
- **Batch transcription** — queue existing recordings from the same window.
- **Local-first storage** — recordings, drafts, transcripts, and model caches stay on your computer.
- **Platform-native model paths** — MLX on Apple Silicon macOS; Qwen3-ASR GGUF through CrispASR on Windows.
- **Bilingual interface** — English by default, with Chinese available from the control bar.
- **Minimal by design** — one window, one job, no decorative noise.

## Requirements

### Windows

- Windows 10 or later, x64
- Python 3.11 or 3.12 with Tk support
- Microphone permission for LocalVoiceFlow
- Internet access on first launch to download the selected Qwen3-ASR GGUF model from Hugging Face

### macOS

- Apple Silicon (`arm64`) macOS
- Python 3.11 or 3.12 with Tk support
- Microphone permission for LocalVoiceFlow
- Internet access on first launch to download the selected MLX model from Hugging Face

Intel Macs are not supported by the current MLX runtime.

## Install manually

### Windows

From PowerShell in the project directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DesktopShortcut
.\LocalVoiceFlow.cmd
```

The installer creates an isolated `.venv`, installs the Windows dependencies, prepares local data and model-cache directories, and creates a Desktop shortcut. The first launch downloads a Qwen3-ASR GGUF model; later launches reuse the local cache.

### macOS

1. Double-click `Install LocalVoiceFlow.command`, or run the commands below.

```bash
./scripts/install.sh --desktop-shortcut
./scripts/run.sh
```

The macOS installer creates an isolated `.venv`, checks Python and Tk compatibility, installs the MLX dependencies, prepares local data and model-cache directories, and creates a Desktop shortcut.

The older `MacVoiceFlow.command` and `Install MacVoiceFlow.command` remain as compatibility launchers for existing installations.

## Data and cache

User data is kept outside the repository:

```text
Documents/LocalVoiceFlow/
├── Record/        # WAV recordings
├── Transcripts/   # Markdown transcripts
└── TempChunks/    # temporary real-time chunks
```

Model caches are stored in the platform's local cache directory:

- Windows: `%LOCALAPPDATA%\LocalVoiceFlow\huggingface\`
- macOS: `~/Library/Caches/LocalVoiceFlow/huggingface/`

Existing macOS installations using `MacVoiceFlow/` or `转录结果/` continue to work. The transcript folder is migrated to `Transcripts/` without overwriting existing files.

To move either location, set `LOCALVOICEFLOW_DATA_DIR` and `LOCALVOICEFLOW_CACHE_DIR`. The older `MACVOICEFLOW_*` variable names remain accepted for compatibility.

## Typical workflow

1. Choose the interface language, model, and transcription language.
2. Press **Start recording**.
3. Edit the live transcript whenever needed.
4. Press **Pause** or **Stop & save**.
5. The WAV recording and cleaned Markdown transcript are saved together.

Existing recordings can be sent to the batch transcription queue. Renaming a paired recording or transcript keeps the matching file in sync.

## Models

### Windows — Qwen3-ASR GGUF

Windows uses [CrispASR](https://github.com/CrispStrobe/CrispASR) with GGUF models from Hugging Face:

- [Qwen3-ASR 1.7B GGUF](https://huggingface.co/cstr/qwen3-asr-1.7b-GGUF) — Q4_K recommended; Q8_0 available for higher precision.
- [Qwen3-ASR 0.6B GGUF](https://huggingface.co/cstr/qwen3-asr-0.6b-GGUF) — compact Q4_K option for lighter machines.

### macOS — Qwen3-ASR MLX

macOS uses the MLX community builds:

- `Qwen3-ASR-1.7B-4bit` — recommended default
- `Qwen3-ASR-1.7B-8bit` — higher precision
- `Qwen3-ASR-0.6B-8bit` — lighter and faster

Model files are not committed to Git. They are downloaded on demand and cached locally.

## Release history

### [v0.3.0 — Windows + macOS local transcription](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.3.0)

LocalVoiceFlow is now a two-platform project. Windows gets an Agent-first PowerShell installer, Desktop shortcut support, and Qwen3-ASR GGUF through CrispASR. macOS keeps the existing MLX workflow, while the product name and documentation now describe the shared local-first experience instead of a single operating system.

### [v0.2.1 — English storage paths](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.2.1)

The data folders now use consistent English names, including `Transcripts/`. Existing installations migrate the former `转录结果/` folder safely, so old work remains available.

### [v0.2.0 — Bilingual live transcription](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.2.0)

The first polished public release: English-first UI with instant Chinese switching, portable data and cache paths, safer model switching, improved audio resampling compatibility, Apache-2.0 licensing, and bilingual documentation.

### [v0.1.0 — Public preview](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.1.0)

The initial public preview established the core workflow: real-time speech-to-text, live editing, pause/resume, local WAV and Markdown export, batch transcription, file renaming, and a double-click installer for Apple Silicon Macs.

## Troubleshooting

### The app cannot record

Allow microphone access for LocalVoiceFlow, Terminal, or the application that launched it. On macOS, open **System Settings → Privacy & Security → Microphone**. On Windows, check **Settings → Privacy & security → Microphone**.

### The model does not load

Check the `app.log` file in the LocalVoiceFlow data directory. Confirm that the first-run model download completed and that the selected model fits available memory.

### Installation picked the wrong Python

Windows: set `PYTHON_BIN` or pass `-PythonPath` to `scripts/install.ps1`. macOS:

```bash
PYTHON_BIN="/path/to/python3" ./scripts/install.sh
```

## Development

The desktop workflow stays intentionally compact: Tkinter for the UI, sounddevice for microphone input, and a platform-specific local ASR backend. Model weights stay outside Git and are downloaded only when selected.

## License

Licensed under the [Apache License 2.0](LICENSE).
