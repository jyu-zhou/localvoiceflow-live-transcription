# LocalVoiceFlow — 本地实时转录

[![最新版本](https://img.shields.io/github/v/release/jyu-zhou/localvoiceflow-live-transcription?display_name=tag)](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/latest)
[![许可证](https://img.shields.io/github/license/jyu-zhou/localvoiceflow-live-transcription)](LICENSE)

**一个安静、本地优先的桌面工作区：把正在说的话即时变成可编辑文字。**

[English README](README.md)

## 使用 Agent 一键安装（推荐）

把对应系统的 Prompt 发给一个能够在你的电脑上执行命令的 Agent。它会调用仓库自带安装器、保留已有文件、创建桌面快捷方式，并启动一次程序。

### Windows

```text
请在这台 Windows 电脑上安装 LocalVoiceFlow。

仓库地址：
https://github.com/jyu-zhou/localvoiceflow-live-transcription.git

安装到：
%USERPROFILE%\Applications\LocalVoiceFlow

请执行以下步骤：
1. 检查系统是否为 Windows x64，并确认存在 Python 3.11 或 3.12。如果缺少 Python，请说明缺少什么并停止。
2. 如果目标目录不存在，就把仓库克隆到那里。如果它已经是 Git 仓库，先执行 `git status --porcelain`；如果存在未提交修改，不要覆盖并停止报告。否则执行 `git pull --ff-only`。
3. 进入项目目录，执行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DesktopShortcut`。
4. 确认桌面上存在 `LocalVoiceFlow.lnk`，并且它指向当前项目。如果这个名称已被其他文件占用，保留原文件，并报告安装器创建的备用快捷方式路径。
5. 不要主动使用管理员权限；不要删除录音、模型缓存、用户数据或无关文件；不要修改麦克风隐私设置。如果 Windows 请求权限，提醒我手动确认。
6. 安装完成后启动一次桌面快捷方式，并报告项目路径、快捷方式路径，以及模型下载提示。
```

### macOS

```text
请在这台 Apple Silicon Mac 上安装 LocalVoiceFlow。

仓库地址：
https://github.com/jyu-zhou/localvoiceflow-live-transcription.git

安装到：
~/Applications/LocalVoiceFlow

请执行以下步骤：
1. 检查当前系统是否为 Apple Silicon macOS，并确认存在带 Tk 支持的 Python 3.11 或 3.12。如果缺少，请说明缺少什么并停止。
2. 如果目标目录不存在，就把仓库克隆到那里。如果它已经是 Git 仓库，先执行 `git status --porcelain`；如果存在未提交修改，不要覆盖并停止报告。否则执行 `git pull --ff-only`。
3. 进入项目目录，执行 `./scripts/install.sh --desktop-shortcut`。
4. 确认桌面上存在 `LocalVoiceFlow.command`，并且它指向当前项目。如果这个名称已被其他文件占用，保留原文件，并报告安装器创建的备用快捷方式路径。
5. 不要使用 sudo；不要删除录音、模型缓存、用户数据或无关文件；不要修改 macOS 隐私设置。如果系统请求麦克风权限，提醒我手动确认。
6. 安装完成后启动一次桌面快捷方式，并报告项目路径、快捷方式路径，以及模型下载提示。
```

这些 Prompt 刻意保持保守：不会把未经检查的远程脚本直接通过管道交给 shell，也不会覆盖含有未提交修改的工作目录。

## LocalVoiceFlow 是什么

LocalVoiceFlow 是一个专注于单一任务的桌面程序：让你先说，文字在说话过程中持续出现，然后直接在同一个工作区里修改、命名和保存。原始音频会和 Markdown 转录稿一起留在本机。

它刻意保持简单：一个窗口，一个任务，不让工具本身打扰你。

## 它能做什么

- **实时转录** — 说话过程中持续处理短音频片段。
- **即时编辑** — 转录内容直接出现在可编辑工作区。
- **一条主流程** — 开始、暂停、继续、停止、命名、保存。
- **批量转录** — 从同一个窗口选择已有录音并加入队列。
- **本地优先** — 录音、草稿、转录稿和模型缓存默认留在本机。
- **平台原生模型路径** — Apple Silicon macOS 使用 MLX，Windows 使用 CrispASR + Qwen3-ASR GGUF。
- **双语界面** — 默认英文，也可以在控制栏切换中文。
- **极简设计** — 一个窗口，只服务一个任务。

## 兼容性

### Windows

- Windows 10 或更高版本，x64
- 支持 Tk 的 Python 3.11 或 3.12
- 为 LocalVoiceFlow 授予麦克风权限
- 首次启动需要联网，从 Hugging Face 下载所选 Qwen3-ASR GGUF 模型

### macOS

- Apple Silicon（`arm64`）macOS
- 支持 Tk 的 Python 3.11 或 3.12
- 为 LocalVoiceFlow 授予麦克风权限
- 首次启动需要联网，从 Hugging Face 下载所选 MLX 模型

当前 MLX 运行时不支持 Intel Mac。

## 手动安装

### Windows

在项目目录打开 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DesktopShortcut
.\LocalVoiceFlow.cmd
```

安装器会创建隔离的 `.venv`、安装 Windows 依赖、准备本地数据与模型缓存目录，并创建桌面快捷方式。第一次启动会下载 Qwen3-ASR GGUF 模型，后续启动会复用本地缓存。

### macOS

1. 双击 `Install LocalVoiceFlow.command`，或运行下面的命令：

```bash
./scripts/install.sh --desktop-shortcut
./scripts/run.sh
```

macOS 安装器会创建隔离的 `.venv`，检查 Python/Tk 兼容性，安装 MLX 依赖，准备本地数据与模型缓存目录，并创建桌面快捷方式。

旧版本的 `MacVoiceFlow.command` 和 `Install MacVoiceFlow.command` 仍然保留，作为已有安装的兼容启动入口。

## 数据与缓存位置

用户数据默认保存在项目目录之外：

```text
Documents/LocalVoiceFlow/
├── Record/        # WAV 录音
├── Transcripts/   # Markdown 转录稿
└── TempChunks/    # 实时转录临时片段
```

模型缓存位于：

- Windows：`%LOCALAPPDATA%\LocalVoiceFlow\huggingface\`
- macOS：`~/Library/Caches/LocalVoiceFlow/huggingface/`

已有 macOS 安装使用的 `MacVoiceFlow/` 或 `转录结果/` 仍然可以继续使用。旧转录目录会安全迁移为 `Transcripts/`，不会覆盖已有文件。

如需迁移数据或缓存位置，可设置 `LOCALVOICEFLOW_DATA_DIR` 和 `LOCALVOICEFLOW_CACHE_DIR`。旧的 `MACVOICEFLOW_*` 环境变量仍然兼容。

## 常用流程

1. 选择界面语言、模型和转录语言。
2. 点击 **Start recording / 开始录音**。
3. 在编辑区即时修订文字。
4. 点击 **Pause / 暂停** 或 **Stop & save / 停止并保存**。
5. 程序会一起保存 WAV 录音和整理后的 Markdown 转录稿。

已有录音可以在左侧选中后加入批量转录队列。重命名成对的录音或转录稿时，匹配文件也会同步更新。

## 模型选项

### Windows — Qwen3-ASR GGUF

Windows 使用 [CrispASR](https://github.com/CrispStrobe/CrispASR) 加载 Hugging Face 上的 GGUF 模型：

- [Qwen3-ASR 1.7B GGUF](https://huggingface.co/cstr/qwen3-asr-1.7b-GGUF) — 默认使用 Q4_K，也提供更高精度的 Q8_0。
- [Qwen3-ASR 0.6B GGUF](https://huggingface.co/cstr/qwen3-asr-0.6b-GGUF) — 更适合资源有限设备的轻量 Q4_K。

### macOS — Qwen3-ASR MLX

macOS 使用 MLX 社区模型：

- `Qwen3-ASR-1.7B-4bit` — 默认推荐
- `Qwen3-ASR-1.7B-8bit` — 更高精度
- `Qwen3-ASR-0.6B-8bit` — 更轻、更快

模型文件不会提交到 Git，而是在需要时下载并保存在本地缓存中。

## 版本记录

### [v0.3.0 — Windows + macOS 本地转录](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.3.0)

LocalVoiceFlow 现在是一个双平台项目：Windows 增加了以 Agent 为首选的 PowerShell 安装器、桌面快捷方式和基于 CrispASR 的 Qwen3-ASR GGUF；macOS 保留原有 MLX 流程。产品名和文档也改为描述共同的本地优先体验，不再绑定某一个操作系统。

### [v0.2.1 — 英文存储路径](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.2.1)

统一用户数据目录命名，使用 `Transcripts/` 替代原来的 `转录结果/`。旧安装会自动迁移，不覆盖已有文件。

### [v0.2.0 — 双语实时转录](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.2.0)

完成第一版面向公众的产品化整理：英文默认界面、即时中文切换、可迁移的数据与缓存路径、更安全的模型切换、更好的音频重采样兼容性、Apache-2.0 许可证和双语文档。

### [v0.1.0 — Public Preview](https://github.com/jyu-zhou/localvoiceflow-live-transcription/releases/tag/v0.1.0)

首个公开预览版本，建立了实时语音转文字、实时编辑、暂停/继续、WAV 与 Markdown 保存、批量转录、文件重命名和 Apple Silicon 双击安装等核心流程。

## 排查问题

### 无法录音

为 LocalVoiceFlow、Terminal 或启动它的应用授予麦克风权限。macOS 打开 **系统设置 → 隐私与安全性 → 麦克风**；Windows 检查 **设置 → 隐私和安全 → 麦克风**。

### 模型无法加载

检查 LocalVoiceFlow 数据目录中的 `app.log`，确认首次下载已经完成，并确认所选模型适合当前可用内存。

### 安装时选错 Python

Windows 可以设置 `PYTHON_BIN`，或向 `scripts/install.ps1` 传入 `-PythonPath`。macOS 可以显式指定：

```bash
PYTHON_BIN="/path/to/python3" ./scripts/install.sh
```

## 开发说明

核心桌面流程刻意保持紧凑：Tkinter 负责界面，sounddevice 负责麦克风输入，再按平台选择本地 ASR 后端。模型权重不进入 Git，只在用户选择时下载。

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源。
