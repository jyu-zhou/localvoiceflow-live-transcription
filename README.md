# MacVoiceFlow

## Real-time speech-to-text and instant editing for macOS

MacVoiceFlow turns your Mac microphone into a focused writing surface: speak naturally, watch the transcript arrive in real time, and edit the result while the session is still in progress.

它是一个为 Apple Silicon 优化的本地实时语音转文字工具：打开即录，边说边转，随时编辑，最后把音频和 Markdown 转录稿一起保存下来。

## Why MacVoiceFlow

- **Real-time transcription** — audio is processed in short segments while you speak.
- **Instant editing** — the live transcript stays in an editable workspace instead of a read-only result page.
- **One simple workflow** — start, pause, continue, stop, name, save.
- **Local-first storage** — recordings, drafts, and Markdown results remain on your Mac.
- **Qwen3-ASR on MLX** — choose between 0.6B and 1.7B model variants for speed or accuracy.
- **Batch transcription** — select existing recordings and add them to the transcription queue.
- **Minimal interface** — the product stays focused on one job: turning speech into usable text.

## Requirements

- macOS on Apple Silicon (`arm64`)
- Python 3.11 or 3.12
- Microphone access for the application
- Internet access on first launch to download the selected model from Hugging Face

Intel Macs are not supported by the current MLX runtime.

## Install

### Double-click installation

1. Download or clone this repository.
2. Double-click `Install MacVoiceFlow.command`.
3. When installation finishes, double-click `MacVoiceFlow.command`.

### Terminal installation

```bash
./scripts/install.sh
./scripts/run.sh
```

The first launch creates the local Python environment, downloads the model, and may trigger the macOS microphone permission prompt. The initial model download can take time; later launches reuse the local cache.

## Data locations

By default, MacVoiceFlow keeps user data outside the repository:

```text
~/Documents/MacVoiceFlow/
├── Record/       # saved WAV recordings
├── 转录结果/       # Markdown transcripts
└── TempChunks/   # temporary real-time chunks
```

The model cache is stored under `~/Library/Caches/MacVoiceFlow/huggingface/`.

To move application data or model cache:

```bash
MACVOICEFLOW_DATA_DIR="/path/to/data" \
MACVOICEFLOW_CACHE_DIR="/path/to/cache" \
./scripts/run.sh
```

## Workflow

1. Choose the model and output language.
2. Press **开始录音**.
3. Edit the live transcript whenever needed.
4. Press **暂停** or **停止并保存**.
5. The WAV recording and cleaned Markdown transcript are saved together.

Existing recordings can be selected from the left panel and sent to the batch transcription queue. File names can be renamed from the same workspace, with paired recordings and transcripts kept in sync.

## Model options

The default model is `Qwen3-ASR-1.7B-4bit`. The interface also exposes:

- `1.7B-8bit` for higher precision
- `0.6B-8bit` for a lighter, faster option

The model files are not included in Git. They are downloaded on demand and cached locally.

## Troubleshooting

### The app cannot record

Open **System Settings → Privacy & Security → Microphone** and allow Terminal or the application that launched MacVoiceFlow to access the microphone.

### The model does not load

Check the log at:

```text
~/Documents/MacVoiceFlow/app.log
```

Confirm that the Mac is Apple Silicon and that the first-run model download completed successfully.

### Installation picked the wrong Python

Specify a Python 3.11 or 3.12 interpreter explicitly:

```bash
PYTHON_BIN="/path/to/python3" ./scripts/install.sh
```

## Development check

After installing the dependencies, run the small regression check:

```bash
./.venv/bin/python tests/test_transcript_formatting.py
```

## Project status

MacVoiceFlow is an early public release built from a working local application. The core recording, transcription, editing, batch queue, renaming, and Markdown export flow is intentionally kept together in one focused desktop workflow.

## License

License selection is intentionally left open for the project owner before the first formal public release.
