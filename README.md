# 零食店直播运营系统

面向零食店开店避坑知识科普留资的抖音直播间。业务目标不是直播卖零食而是留资，是通过省份、预算、品牌、快招公司避坑等知识，帮助准备开店的人避坑，并通过（零食店行业调研报告,品牌避坑名单，选址评估表，回本周期计算表，还可以一对一免费分析）这些资料做钩子引导用户主动在抖音站内私信留资。系统采集直播数据 → ASR 转写话术 → AI 复盘分析 → 知识库问答，形成完整的运营复盘闭环。

> 本项目仅用于已获授权的数据分析。请遵守平台规则与隐私法规。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3、TypeScript、Vite、SoybeanAdmin、Naive UI、ECharts |
| 后端 | FastAPI、SQLAlchemy、APScheduler、Playwright |
| 数据 | MySQL 8、Redis 7 |
| AI | 本地 Ollama（Qwen3.5 9B）、FunASR、ffmpeg |
| 可视化 | SoybeanAdmin、Naive UI、ECharts 原生经营大屏 |
| 可观测性 | Trace ID、结构化日志、健康检查 |

## 环境要求

- macOS、Linux，或 64 位 Windows 10 22H2 / Windows 11
- Docker Desktop
- Python 3.12（项目通过 `.python-version` 固定）
- Node.js 22 与 pnpm 10.12.4（项目通过 `.nvmrc` 和 `packageManager` 固定）
- ffmpeg（AI 自动剪辑字幕烧录需带 libass 的版本，见 `docs/开发.md`）

```bash
docker --version && python3 --version && node --version && pnpm --version && ffmpeg -version
```

## macOS / Linux 快速开始

```bash
# 1. 首次部署：安装固定版本依赖并创建 .env
./setup.sh

# 2. 填写 .env 后，日常启动（推荐模式）
./start.sh standard

# 低资源电脑可使用：
# ./start.sh lite      # 核心业务，不自动启动 FunASR
```

启动后访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:9527 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

> 首次使用建议先看[新手上手指南](docs/beginner-guide.md)。

## Windows 原生部署（PowerShell 7）

Windows 使用原生 Python、Node.js、Ollama 和 PowerShell，MySQL、Redis、Qdrant、FunASR 仍由 Docker Desktop 的 Linux containers 运行，不需要进入 WSL 终端。建议至少 16GB 内存，运行本地 9B 模型和 ASR 时推荐 32GB；项目请放在不含中文和空格的短路径，例如 `C:\douyinLive`。

### 1. 安装系统依赖

先在 PowerShell 中安装 Git、PowerShell 7、Python 3.12、ffmpeg 和 Docker Desktop：

```powershell
winget install --id Git.Git --exact
winget install --id Microsoft.PowerShell --exact
winget install --id Python.Python.3.12 --exact
winget install --id Gyan.FFmpeg --exact
winget install --id Docker.DockerDesktop --exact
```

另外安装以下固定组件：

- 从 [Node.js 官方归档](https://nodejs.org/en/download/archive/v22.22.0)安装 Node.js 22.x，不要使用 24.x 等其他主版本。
- 从 [Ollama Windows 官网](https://ollama.com/download/windows)安装 Ollama；安装后会在本机后台提供 `http://127.0.0.1:11434`。
- 打开 Docker Desktop，确认使用 **Linux containers**。Docker 官方推荐大多数 Windows 电脑使用 WSL 2 后端，具体要求见 [Docker Desktop Windows 安装文档](https://docs.docker.com/desktop/setup/install/windows-install/)。

安装完成后关闭旧终端，从开始菜单打开 **PowerShell 7**，确认版本：

```powershell
$PSVersionTable.PSVersion
git --version
docker version
py -3.12 --version
node --version
ffmpeg -version
ollama --version
```

其中 PowerShell 必须是 7.x、Python 必须是 3.12.x、Node.js 必须是 22.x。

### 2. 克隆项目并安装依赖

以下命令全部在 PowerShell 7 中执行：

```powershell
Set-Location C:\
git clone https://github.com/lppmql/douyinLive.git
Set-Location C:\douyinLive

Copy-Item .env.example .env

py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\backend\.venv\Scripts\python.exe -m playwright install chromium

Push-Location frontend
corepack pnpm@10.12.4 install --frozen-lockfile
Pop-Location
```

打开 `.env`，至少修改 `MYSQL_ROOT_PASSWORD`、`DB_PASSWORD`、`REDIS_PASSWORD`、`REDIS_URL` 和 `JWT_SECRET_KEY`。`REDIS_URL` 中的密码必须与 `REDIS_PASSWORD` 完全一致，不要把 `DB_USER` 改成 `root`。

### 3. 初始化本地 AI 模型

确认 Windows 任务栏中的 Ollama 已运行，然后执行：

```powershell
ollama pull qwen3.5:9b
ollama create douyin-live-qwen -f .\deploy\ollama\Modelfile
ollama list
```

列表中出现 `douyin-live-qwen` 即表示初始化成功。模型约占 7GB，仅保存在本机，不需要 DeepSeek 等云端 API Key。

### 4. 启动项目

Windows 原生日常启动入口是：

```powershell
pwsh -File .\start.ps1 standard
```

低资源电脑可执行 `pwsh -File .\start.ps1 lite`，此模式不自动启动 FunASR。启动终端必须保持打开；按 `Ctrl+C` 停止前后端，MySQL、Redis、Qdrant 等 Docker 数据服务会继续运行，保证数据不会因退出终端而丢失。

启动后在 Windows 浏览器访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:9527 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

### 5. Windows 常见问题

- **脚本禁止运行**：确认使用的是 `pwsh` 而不是旧版 `powershell.exe`；必要时仅对当前进程执行 `Set-ExecutionPolicy -Scope Process Bypass` 后重试。
- **Docker 命令存在但启动失败**：打开 Docker Desktop，并从托盘菜单切换到 Linux containers。
- **端口 8000 或 9527 被占用**：先到原启动终端按 `Ctrl+C`；脚本不会强制结束其他软件的进程。
- **找不到 Node、ffmpeg 或 Ollama**：安装后重新打开 PowerShell 7，让新的 `PATH` 生效。
- **模型不存在**：重新执行上面的三条 Ollama 初始化命令；日常启动不会自动下载大模型。
- **AI 剪辑提示字幕能力缺失**：确认 `ffmpeg -filters` 输出中包含 `subtitles` 或 `ass` 滤镜。
- **采集 Cookie 或浏览器指纹异常**：重新在本机浏览器扫码登录并保存真实指纹，不要只修改 `.env` 中的平台名称来伪造指纹。

## 核心功能

- **扫码登录**：保存 Cookie + 浏览器指纹，登录态自动恢复
- **数据采集**：增量同步主播、直播场次、分钟指标、评论、观众画像、流地址
- **实时监控**：自动识别开播状态，直播中持续采集，下播后补齐详情
- **话术工作台**：FunASR 语音转写 → AI 评分 → 话术资产收录
- **AI 自动剪辑**：AI 从整场话术挑选主题片段，每场自动生成 5 条竖屏 9:16 短视频（大字幕+封面），自动产出抖音标题/文案/话题，一键复制人工发布，支持单条重剪
- **AI 复盘工作台**：可信度评估、五维话术评分、证据提取、下一场动作建议
- **跨场对比**：同主播不同场次指标对比，曲线对齐开播后分钟
- **知识库问答**：基于真实话术/评论/指标的 AI 问答，每次回答可追溯到原场次
- **经营仪表盘**：复用公共主播和日期筛选，原生展示总体指标、经营趋势、留资漏斗、主播排行和场次明细
- **主播排班**：从排班表导入，自动匹配实际场次，提示缺场/无效/加场

详细功能说明见各页面右上角「新手帮助」按钮，技术实现见[开发指南](docs/开发.md)。

## 目录结构

```
douyinLive/
├── backend/               FastAPI 后端（API、采集、AI、测试）
├── frontend/              SoybeanAdmin 前端
├── docs/                  架构、开发、部署、故障排查文档
├── scripts/               维护脚本
├── data/                  本地数据（不提交 Git）
├── .github/               CI/CD 工作流
├── Makefile               检查维护命令（make doctor/test/lint/build）
├── docker-compose.yml
├── setup.sh               首次安装/依赖升级
├── start.sh               macOS/Linux 日常启动脚本
└── start.ps1              Windows 原生日常启动脚本
```

## 文档导航

| 文档 | 内容 |
|------|------|
| [文档总入口](docs/README.md) | 新手、开发、部署、ADR、代码治理的统一导航 |
| [开发指南](docs/开发.md) | 环境搭建、项目结构、开发流程、代码规范 |
| [部署指南](docs/部署.md) | 首次部署、发布流程、回滚、备份 |
| [故障排查](docs/故障排查.md) | 常见问题按症状→诊断→解决排查 |
| [架构决策 (ADR)](docs/adr/README.md) | 关键技术方案选型与原因 |
| [架构文档](docs/架构/说明.md) | 架构导航与维护路线 |
| [验收手册](docs/验收手册.md) | 功能验收规程与自检要求 |
| [新手上手指南](docs/beginner-guide.md) | 启动、登录、采集和排错的第一条路线 |
| [CHANGELOG](CHANGELOG.md) | 版本变更记录 |

## 数据安全

- `.env`、`data/`、`backend/storage_state/*.json` 已在 `.gitignore`，不提交 Git
- `DEBUG=false` 时，密码缺失/JWT 密钥不足 32 位会阻断启动
- MySQL/Redis/FunASR 端口默认只绑定 `127.0.0.1`
- 部署前必须替换 `JWT_SECRET_KEY`、数据库密码和所有默认密钥

## 常见问题

### 页面显示 500

先访问 http://localhost:8000/health。如果不是 `status: ok`，检查 Docker Desktop 和 MySQL 是否正常运行。

### 电脑卡顿

在采集页面关闭 ASR 开关释放模型内存（~1.8GB），或暂停实时监控。确认没有重复 Worker：`pgrep -af 'asr_worker'`（正常 0-1 个）。

更多问题见[故障排查手册](docs/故障排查.md)。
