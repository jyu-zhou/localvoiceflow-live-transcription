# MacVoiceFlow — Live Transcription for macOS

**Real-time speech-to-text, instant editing, and local-first workflow for Apple Silicon Macs.**

[中文说明](README.zh-CN.md)

MacVoiceFlow is a focused macOS desktop app for turning live speech into usable text. Speak naturally, watch the transcript arrive in real time, edit it while the session is still running, then save the audio and Markdown transcript together.

## What it does

- **Real-time transcription** — converts short audio segments while you speak.
- **Instant editing** — keeps the live transcript in an editable workspace.
- **One focused workflow** — start, pause, continue, stop, name, and save.
- **Batch transcription** — queue existing recordings from the same workspace.
- **Local-first storage** — recordings, drafts, and transcripts stay on your Mac.
- **Qwen3-ASR on MLX** — choose a 0.6B or 1.7B model according to your speed/accuracy needs.
- **Bilingual interface** — English is the default; switch to Chinese from the control bar.
- **Minimal visual language** — one workspace, one job, no decorative noise.

## Compatibility

- macOS on Apple Silicon (`arm64`)
- Python 3.11 or 3.12 with Tk support
- Microphone permission for the app or terminal that launches it
- Internet access on first launch to download the selected model from Hugging Face

Intel Macs are not supported by the current MLX runtime.

## Install

### Double-click

1. Download or clone this repository.
2. Double-click `Install MacVoiceFlow.command`.
3. When installation finishes, double-click `MacVoiceFlow.command`.

### Terminal

```bash
./scripts/install.sh --desktop-shortcut
./scripts/run.sh
```

The installer creates an isolated `.venv`, checks Python/Tk compatibility, verifies installed dependencies, prepares the local data and model-cache directories, and adds a Desktop shortcut named `MacVoiceFlow.command`. Omit `--desktop-shortcut` if you only want the local environment. The first launch downloads the selected model; later launches reuse the cache.

### Install with an AI agent

If your AI agent can run terminal commands on macOS, paste the following prompt into it. The agent will clone or safely update the project, install the dependencies, create the Desktop shortcut, and launch the app once. It must stop instead of overwriting a directory that contains uncommitted work.

```text
Install MacVoiceFlow on this Apple Silicon Mac.

Repository:
https://github.com/jyu-zhou/macvoiceflow-live-transcription.git

Use this target directory:
~/Applications/MacVoiceFlow

Do the following:
1. Verify that this is macOS on Apple Silicon and that Python 3.11 or 3.12 with Tk support is available. If not, explain exactly what is missing and stop.
2. If ~/Applications/MacVoiceFlow does not exist, clone the repository there. If it already is a Git checkout, inspect `git status --porcelain`; if it contains uncommitted changes, do not overwrite them and stop with a report. Otherwise update it with `git pull --ff-only`.
3. Run `./scripts/install.sh --desktop-shortcut` from the project directory.
4. Confirm that `~/Desktop/MacVoiceFlow.command` exists and points to the project's `MacVoiceFlow.command` launcher. If that name is already occupied by another file, keep the existing file and report the alternate shortcut path created by the installer.
5. Do not use sudo. Do not delete user data, existing recordings, model caches, or unrelated files. Do not change macOS microphone privacy settings; tell me if macOS asks for permission.
6. After installation succeeds, launch the Desktop shortcut once and report the final project path, shortcut path, and any permission or model-download prompt.
```

This prompt uses the repository's own installer; it does not pipe an unreviewed remote script into a shell.

## Data and cache

By default, user data is kept outside the repository:

```text
~/Documents/MacVoiceFlow/
├── Record/        # saved WAV recordings
├── Transcripts/    # Markdown transcripts
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

## Workflow

1. Choose the interface language, model, and transcription language.
2. Press **Start recording**.
3. Edit the live transcript whenever needed.
4. Press **Pause** or **Stop & save**.
5. The WAV recording and cleaned Markdown transcript are saved together.

Existing recordings can be selected and sent to the batch transcription queue. Renaming a paired recording or transcript keeps the matching file in sync.

## Model options

The default is `Qwen3-ASR-1.7B-4bit`. The interface also exposes:

- `1.7B-8bit` for higher precision
- `0.6B-8bit` for a lighter, faster option

Model files are not committed to Git; they are downloaded on demand and cached locally.

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

The project also keeps the core UI flow in one source file so the desktop app remains easy to inspect, install, and modify.

## License

Licensed under the [Apache License 2.0](LICENSE).
