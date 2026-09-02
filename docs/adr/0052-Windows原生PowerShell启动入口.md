# ADR 0052：Windows 原生 PowerShell 启动入口

- 状态：已接受
- 日期：2026-09-02
- 取代：ADR 0051 中“全项目只有一个日常启动脚本”的跨平台限制

## 背景

项目原有 `start.sh` 依赖 Bash、Unix 进程信号和 `.venv/bin` 目录，不能在 Windows 原生 PowerShell 中运行。要求 Windows 用户进入 WSL2 虽然改动较少，但会把 Windows Ollama、Docker Desktop、浏览器文件和项目目录分隔到两个环境，增加新手部署和排障成本。

## 决策

1. 每个受支持的宿主系统只保留一个日常启动入口：macOS/Linux 使用 `./start.sh`，Windows 使用 PowerShell 7 的 `pwsh -File .\start.ps1 standard`。
2. Windows 后端和前端直接运行在宿主机；MySQL、Redis、Qdrant 和 FunASR 继续使用 Docker Desktop 的 Linux containers。
3. Windows 复用原生 Ollama 的回环接口和 GPU 支持，不引入云端模型密钥，也不在日常启动时下载大模型。
4. `start.ps1` 与 Bash 入口保持相同的核心顺序：环境检查、本地模型检查、基础容器、数据库迁移、单进程后端、可选 FunASR、前端和健康检查。
5. Windows 脚本发现 8000 或 9527 端口占用时直接停止并提示，不强制结束未知进程；避免误杀 Docker Desktop 或其他 Windows 软件。
6. Windows 首次安装仍是显式步骤，不把系统软件、Python 包、前端依赖或模型下载塞入日常启动脚本。

## 结果

- Windows 用户无需进入 WSL 终端即可完成部署和日常运行，本地模型、浏览器与文件均位于同一宿主环境。
- 仓库重新拥有两个操作系统专用启动脚本，但单台电脑仍只有一个明确入口，不恢复 `make start` 等跨层别名。
- CI 当前不具备 Windows Docker Desktop、Ollama 和真实采集环境；通过静态契约测试覆盖编排边界，首次真实 Windows 部署仍需按 README 完成人工验收。
