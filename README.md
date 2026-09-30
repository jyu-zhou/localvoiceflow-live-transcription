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
./scripts/install.sh
./scripts/run.sh
```

The installer creates an isolated `.venv`, checks Python/Tk compatibility, verifies installed dependencies, and prepares the local data and model-cache directories. The first launch downloads the selected model; later launches reuse the cache.

## Data and cache

By default, user data is kept outside the repository:

```text
~/Documents/MacVoiceFlow/
├── Record/        # saved WAV recordings
├── 转录结果/        # Markdown transcripts
└── TempChunks/    # temporary real-time chunks
```

The model cache is stored under `~/Library/Caches/MacVoiceFlow/huggingface/`.

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
