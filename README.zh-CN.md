# MacVoiceFlow — macOS 实时转录

**面向 Apple Silicon Mac 的实时语音转文字、即时编辑与本地优先工作流。**

[English README](README.md)

MacVoiceFlow 是一个专注于单一任务的 macOS 桌面程序：把正在说的话即时变成可用文字。打开后直接录音，转录内容会持续进入编辑区；你可以边说边改，结束时把音频和 Markdown 转录稿一起保存。

## 它能做什么

- **实时转录** — 说话过程中持续处理短音频片段。
- **即时编辑** — 转录内容直接出现在可编辑工作区，而不是只读结果页。
- **一条主流程** — 开始、暂停、继续、停止、命名、保存。
- **批量转录** — 从同一个工作区选择已有录音并加入队列。
- **本地优先** — 录音、草稿和转录稿默认留在本机。
- **Qwen3-ASR + MLX** — 根据速度和精度需要选择 0.6B 或 1.7B 模型。
- **双语界面** — 默认英文，也可以在顶部控制栏切换中文。
- **极简视觉语言** — 一个工作区，只服务一个任务，不加入装饰性噪音。

## 兼容性

- Apple Silicon（`arm64`）macOS
- 支持 Tk 的 Python 3.11 或 3.12
- 为启动 MacVoiceFlow 的应用或终端授予麦克风权限
- 首次启动需要联网，从 Hugging Face 下载所选模型

当前 MLX 运行时不支持 Intel Mac。

## 安装

### 双击安装

1. 下载或克隆本仓库。
2. 双击 `Install MacVoiceFlow.command`。
3. 安装完成后双击 `MacVoiceFlow.command`。

### 终端安装

```bash
./scripts/install.sh --desktop-shortcut
./scripts/run.sh
```

安装脚本会创建隔离的 `.venv`，检查 Python/Tk 兼容性，校验依赖，准备本地数据与模型缓存目录，并在桌面创建 `MacVoiceFlow.command` 快捷方式。如果只需要本地运行环境，可以省略 `--desktop-shortcut`。第一次启动会下载模型，后续启动会复用缓存。

### 使用 Agent 一键安装

如果你的 Agent 可以在 macOS 上执行终端命令，把下面这段 Prompt 直接发给它。Agent 会克隆或安全更新项目、安装依赖、创建桌面快捷方式并启动一次程序。如果目标目录有未提交修改，它必须停止，不能覆盖用户工作。

```text
请在这台 Apple Silicon Mac 上安装 MacVoiceFlow。

仓库地址：
https://github.com/jyu-zhou/macvoiceflow-live-transcription.git

安装到：
~/Applications/MacVoiceFlow

请执行以下步骤：
1. 检查当前系统是否为 Apple Silicon macOS，并确认存在带 Tk 支持的 Python 3.11 或 3.12。如果缺少，请明确说明缺少什么并停止。
2. 如果 ~/Applications/MacVoiceFlow 不存在，就把仓库克隆到该目录。如果它已经是 Git 仓库，先执行 `git status --porcelain`；如果存在未提交修改，不要覆盖并停止报告。否则执行 `git pull --ff-only` 安全更新。
3. 进入项目目录，执行 `./scripts/install.sh --desktop-shortcut`。
4. 确认 `~/Desktop/MacVoiceFlow.command` 存在，并且指向项目里的 `MacVoiceFlow.command` 启动器。如果这个文件名已经被其他文件占用，保留原文件，并报告安装器创建的备用快捷方式路径。
5. 不要使用 sudo；不要删除用户数据、已有录音、模型缓存或无关文件；不要修改 macOS 麦克风隐私设置。如果系统请求权限，告诉我由用户手动确认。
6. 安装成功后启动一次桌面快捷方式，并报告最终项目路径、快捷方式路径，以及可能出现的权限或模型下载提示。
```

这段 Prompt 调用的是仓库自带安装器，不会把未经检查的远程脚本直接通过管道交给 shell 执行。

## 数据与缓存位置

默认情况下，用户数据不会写入项目目录：

```text
~/Documents/MacVoiceFlow/
├── Record/        # 保存的 WAV 录音
├── Transcripts/    # Markdown 转录稿
└── TempChunks/    # 实时转录临时片段
```

模型缓存位于 `~/Library/Caches/MacVoiceFlow/huggingface/`。

旧版本使用的 `转录结果/` 会自动迁移为 `Transcripts/`；如果新旧目录同时存在，程序会保留两边文件并避免覆盖。

如需迁移位置：

```bash
MACVOICEFLOW_DATA_DIR="/path/to/data" \
MACVOICEFLOW_CACHE_DIR="/path/to/cache" \
./scripts/run.sh
```

## 使用流程

1. 选择界面语言、模型和转录语言。
2. 点击 **Start recording / 开始录音**。
3. 在右侧编辑区即时修订文字。
4. 点击 **Pause / 暂停** 或 **Stop & save / 停止并保存**。
5. 程序会一起保存 WAV 录音和整理后的 Markdown 转录稿。

已有录音可以在左侧选中后加入批量转录队列。重命名成对的录音或转录稿时，匹配文件也会同步更新。

## 模型选项

默认模型是 `Qwen3-ASR-1.7B-4bit`，界面还提供：

- `1.7B-8bit`：更高精度
- `0.6B-8bit`：更轻、更快

模型文件不会提交到 Git，而是在需要时下载并保存在本地缓存中。

## 排查问题

### 无法录音

打开 **系统设置 → 隐私与安全性 → 麦克风**，允许 Terminal 或启动 MacVoiceFlow 的应用访问麦克风。

### 模型无法加载

检查 `~/Documents/MacVoiceFlow/app.log`，确认 Mac 使用 Apple Silicon，并确认首次下载已经完成。

### 安装时选错 Python

可以显式指定 Python 3.11 或 3.12：

```bash
PYTHON_BIN="/path/to/python3" ./scripts/install.sh
```

## 开发检查

安装依赖后运行：

```bash
./.venv/bin/python tests/test_transcript_formatting.py
```

项目刻意把核心桌面工作流保持在一套清晰的源码结构中，便于检查、安装和继续修改。

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源。
