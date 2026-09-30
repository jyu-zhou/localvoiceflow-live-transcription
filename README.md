# MacVoiceFlow — Live Transcription for macOS

[![Latest release](https://img.shields.io/github/v/release/jyu-zhou/macvoiceflow-live-transcription?display_name=tag)](https://github.com/jyu-zhou/macvoiceflow-live-transcription/releases/latest)
[![License](https://img.shields.io/github/license/jyu-zhou/macvoiceflow-live-transcription)](LICENSE)

**A small, local-first Mac app for turning live speech into editable text.**

[中文说明](README.zh-CN.md)

## Install with an AI agent

If your agent can run terminal commands on macOS, send it the prompt below. It installs MacVoiceFlow, creates a Desktop shortcut, and launches the app once. The instructions are deliberately conservative: an existing folder with uncommitted work is never overwritten.

```text
Please install MacVoiceFlow on this Apple Silicon Mac.

Repository:
https://github.com/jyu-zhou/macvoiceflow-live-transcription.git

Install it at:
~/Applications/MacVoiceFlow

Please:
1. Verify macOS on Apple Silicon and Python 3.11 or 3.12 with Tk support. If either is missing, explain what is missing and stop.
2. Clone the repository if the target directory does not exist. If it is already a Git checkout, run `git status --porcelain`; if there are uncommitted changes, do not overwrite them and stop with a report. Otherwise run `git pull --ff-only`.
3. From the project directory, run `./scripts/install.sh --desktop-shortcut`.
4. Confirm that the Desktop shortcut exists and points to the project's `MacVoiceFlow.command`. If `~/Desktop/MacVoiceFlow.command` is already owned by another file, keep it and report the alternate shortcut created by the installer.
5. Do not use sudo. Do not delete recordings, model caches, user data, or unrelated files. Do not change macOS privacy settings; tell me if microphone permission is requested.
6. Launch the Desktop shortcut once and report the project path, shortcut path, and any permission or model-download prompt.
```

The prompt uses the repository's own installer. It does not pipe an unreviewed remote script into a shell.

## What MacVoiceFlow is

MacVoiceFlow is a focused macOS desktop app for people who want to speak first and shape the text immediately afterward. The transcript appears while you talk, stays editable during the session, and can be saved together with the original audio as a Markdown file.

It is intentionally one thing: a quiet, dependable workspace for live transcription.

## What it does

- **Live transcription** — turns short audio segments into text as you speak.
- **Instant editing** — keeps the transcript in an editable workspace instead of a read-only result page.
- **A single clear flow** — start, pause, resume, stop, name, and save.
- **Batch transcription** — queue existing recordings from the same window.
- **Local-first storage** — recordings, drafts, and transcripts stay on your Mac.
- **Qwen3-ASR on MLX** — choose a faster 0.6B model or a more capable 1.7B model.
- **Bilingual interface** — English by default, with Chinese available from the control bar.
- **Minimal by design** — one window, one job, no decorative noise.

## Requirements

- macOS on Apple Silicon (`arm64`)
- Python 3.11 or 3.12 with Tk support
- Microphone permission for the app or terminal that launches MacVoiceFlow
- Internet access on first launch to download the selected model from Hugging Face

Intel Macs are not supported by the current MLX runtime.

## Install manually

### Double-click

1. Download or clone this repository.
2. Double-click `Install MacVoiceFlow.command`.
3. When installation finishes, double-click `MacVoiceFlow.command` or use the Desktop shortcut it created.

### Terminal

```bash
./scripts/install.sh --desktop-shortcut
./scripts/run.sh
```

The installer creates an isolated `.venv`, checks Python and Tk compatibility, verifies dependencies, prepares the data and model-cache directories, and adds `MacVoiceFlow.command` to the Desktop. Omit `--desktop-shortcut` if you only need the local environment.

The first launch downloads the selected model. Later launches reuse the local cache.

## Data and cache

User data is kept outside the repository:

```text
~/Documents/MacVoiceFlow/
├── Record/        # WAV recordings
├── Transcripts/   # Markdown transcripts
└── TempChunks/    # temporary real-time chunks
```

The model cache is stored under `~/Library/Caches/MacVoiceFlow/huggingface/`.

Older installations using `转录结果/` are migrated to `Transcripts/` automatically without overwriting existing files.

To move either location:

```bash
MACVOICEFLOW_DATA_DIR="/path/to/data" \
MACVOICEFLOW_CACHE_DIR="/path/to/cache" \
./scripts/run.sh
```

## Typical workflow

1. Choose the interface language, model, and transcription language.
2. Press **Start recording**.
3. Edit the live transcript whenever needed.
4. Press **Pause** or **Stop & save**.
5. The WAV recording and cleaned Markdown transcript are saved together.

Existing recordings can be sent to the batch transcription queue. Renaming a paired recording or transcript keeps the matching file in sync.

## Models

The default model is `Qwen3-ASR-1.7B-4bit`.

- `1.7B-8bit` — higher precision
- `0.6B-8bit` — lighter and faster

Model files are not committed to Git. They are downloaded on demand and cached locally.

## Release history

### [v0.2.1 — English storage paths](https://github.com/jyu-zhou/macvoiceflow-live-transcription/releases/tag/v0.2.1)

The data folders now use consistent English names, including `Transcripts/`. Existing installations migrate the former `转录结果/` folder safely, so old work remains available. This release also documents the Agent installer and Desktop shortcut flow in both languages.

### [v0.2.0 — Bilingual live transcription](https://github.com/jyu-zhou/macvoiceflow-live-transcription/releases/tag/v0.2.0)

The first polished public release: English-first UI with instant Chinese switching, portable data and cache paths, safer model switching, improved audio resampling compatibility, Apache-2.0 licensing, and bilingual documentation.

### [v0.1.0 — Public preview](https://github.com/jyu-zhou/macvoiceflow-live-transcription/releases/tag/v0.1.0)

The initial public preview established the core workflow: real-time speech-to-text, live editing, pause/resume, local WAV and Markdown export, batch transcription, file renaming, and a double-click installer for Apple Silicon Macs.

## Troubleshooting

### The app cannot record

Open **System Settings → Privacy & Security → Microphone** and allow Terminal or the application that launched MacVoiceFlow to access the microphone.

### The model does not load

Check `~/Documents/MacVoiceFlow/app.log`. Confirm that the Mac is Apple Silicon and that the first-run model download completed successfully.

### Installation picked the wrong Python

Specify a Python 3.11 or 3.12 interpreter explicitly:

```bash
PYTHON_BIN="/path/to/python3" ./scripts/install.sh
```

## Development check

After installing dependencies, run:

```bash
./.venv/bin/python tests/test_transcript_formatting.py
```

The core desktop workflow intentionally stays compact and easy to inspect.

## License

Licensed under the [Apache License 2.0](LICENSE).
