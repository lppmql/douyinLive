# 抖音直播运营分析系统

面向直播运营团队的一体化中台：使用已扫码登录的采集账号同步主播、直播场次、分钟指标和用户评论；使用受控的 FunASR 队列生成直播话术；调用 DeepSeek 完成话术评分、异常分析和优化建议；最后把直播数据、评论、话术与 AI 报告统一写入知识库进行问答。

> 本项目仅用于已获授权的数据分析。请遵守平台规则、隐私要求和当地法律，不要采集或传播无权处理的数据。

## 核心能力

- **扫码登录**：保存 Cookie、StorageState 和浏览器指纹，后续采集复用登录环境；连续两次探测失败才判定登录过期，减少平台临时跳转误报。
- **刷新数据采集**：增量补齐全部主播、历史直播场次、场次指标、评论、观众画像和流地址。
- **实时直播监控**：定时识别开播状态，直播中持续采集指标和评论，下播后补齐场次详情。
- **话术转写**：采集后自动为真实回放排队，本地 FunASR 默认开启，限制单任务并发和 5 个排队任务。
- **视频下载**：场次详情显示 m3u8 地址，可选择本地位置并以原码流低开销封装为 MP4。
- **AI 分析**：话术评分、趋势分析、异常检测、高意向用户识别和运营优化建议。
- **知识库问答**：统一检索直播数据、用户评论、完整话术和 AI 分析，并返回关联场次来源。

## 数据链路

```mermaid
flowchart LR
    A[扫码登录] --> B[Cookie 与浏览器指纹]
    B --> C[刷新采集 / 实时监控]
    C --> D[主播与直播场次]
    C --> E[分钟指标与评论]
    C --> F[直播流地址]
    F --> G[FunASR 话术转写]
    D --> H[DeepSeek AI 分析]
    E --> H
    G --> H
    D --> I[知识库]
    E --> I
    G --> I
    H --> I
    I --> J[知识库 AI 问答]
```

## 技术栈

- 前端：Vue 3、TypeScript、Vite、SoybeanAdmin、Naive UI、ECharts
- 后端：FastAPI、SQLAlchemy、APScheduler、Playwright
- 数据：MySQL 8、Redis 7
- AI：DeepSeek API、FunASR、ffmpeg
- 可视化：DataEase（可选）

## 环境要求

- macOS 或 Linux
- Docker Desktop
- Python 3.10
- Node.js 20+ 与 pnpm
- ffmpeg

macOS 可检查依赖：

```bash
docker --version
python3 --version
node --version
pnpm --version
ffmpeg -version
```

## 首次安装

1. 创建本地配置，填写自己的 DeepSeek 密钥：

```bash
cp .env.example .env
```

2. 安装后端依赖和 Playwright Chromium：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cd ..
```

3. 安装前端依赖：

```bash
cd frontend
pnpm install
cd ..
```

4. 一键启动：

```bash
./start.sh
```

启动后访问：

- 前端：<http://localhost:9527>
- 后端健康检查：<http://localhost:8000/health>
- API 文档：<http://localhost:8000/docs>
- DataEase（可选）：<http://localhost:8100>

`start.sh` 启动 MySQL、Redis、后端和前端，后端会自动启动 FunASR。采集调度器由后端统一管理，不再额外启动第二个采集 Worker；FunASR 限制 2 核、1.8GB 内存，ffmpeg 单线程，ASR Worker 单任务并发且最多排队 5 场。

DataEase 只读 MySQL 中的 `de_*` 分析宽表。数据采集完成后会自动增量同步，也可以在“数据采集”页面查看覆盖率并手动补同步；后端状态接口为 `GET /api/v1/dataease/status`。

## 推荐操作顺序

1. 打开“数据采集”页面，扫码登录采集账号。
2. 确认账号状态为“已登录”，并使用“检查存活”验证 Cookie。
3. 实时监控运行时先停止监控，再执行“刷新数据采集”，避免共用浏览器冲突。
4. 等待采集进度完成，查看已同步主播数、场次数、详情数和失败原因。
5. 在“直播场次”查看详情、分钟趋势、按用户归组的评论、m3u8 地址和视频下载。
6. ASR 默认自动生成话术；电脑负载较高时，可在采集页关闭 ASR 释放模型内存。
7. 在“知识库”点击“同步最近 20 场”，然后使用问答输入业务问题。

## ASR 安全说明

FunASR 首次启动会下载并加载模型，可能需要数分钟。项目为 8GB 内存电脑设置了容器资源限制、低优先级 Worker、单任务并发和 5 个任务队列上限：

- 自动队列优先处理短场次，正在直播的无限流不会进入离线转写。
- 无语音或失效回放失败后不会自动反复重试。
- 页面显示“处理中 0”后再关闭 ASR，关闭会释放模型内存。
- “未识别到有效语音”通常表示回放没有人声、流已过期或音频过短，不会写入模拟话术。

手动启停 FunASR（一般直接使用页面开关即可）：

```bash
docker compose --profile funasr up -d funasr
docker stop douyin_live_funasr
```

## 知识库内容

每个场次可幂等同步以下来源：

| 来源 | `source_type` | 内容 |
| --- | --- | --- |
| 直播数据 | `live_data` | 汇总指标、转化率、分钟趋势、观众画像 |
| 互动评论 | `comments` | 评论时间、昵称、内容和高意向标记 |
| 话术 | `transcript` | FunASR 识别后的完整话术 |
| AI 分析 | `ai_analysis` | 评分、异常、趋势和优化建议 |

知识库同步是增量且幂等的：再次同步会更新同一场次内容，不会重复生成直播数据或评论条目。

## 常用检查

后端测试：

```bash
cd backend
source .venv/bin/activate
pytest -q
```

前端类型和构建检查：

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm build
```

服务状态：

```bash
curl http://localhost:8000/health
docker compose ps
```

## 目录结构

```text
douyinLive/
├── backend/          FastAPI、采集、ASR、AI 与测试
├── frontend/         SoybeanAdmin 前端
├── data/             本地数据库、模型、日志（不提交 Git）
├── docs/             开发记录
├── docker-compose.yml
└── start.sh          本地一键启动脚本
```

## 数据安全

- `.env`、`data/`、`backend/storage_state/*.json` 已加入 `.gitignore`。
- Cookie、Token、浏览器指纹和 AI 密钥只能保存在本机，不得提交远程仓库。
- 删除采集账号会清除本地登录环境，需要重新扫码，请确认后操作。
- 正式部署前必须替换 `JWT_SECRET_KEY` 和数据库默认密码。

## 常见问题

### 页面显示 500

先打开 <http://localhost:8000/health>。如果不是 `status: ok`，检查 Docker Desktop、MySQL 和后端终端日志。

### 浏览器被关闭或 `Target page ... has been closed`

不要同时运行实时监控和刷新数据采集。停止当前任务后重新检查账号存活，再执行采集。

### 电脑明显卡顿

先在采集页面关闭 ASR，并停止实时监控。确认没有重复 Worker：

```bash
pgrep -af 'workers.scraper_worker|workers.asr_worker'
```

正常情况下，默认一键启动不会出现独立 `scraper_worker`，但会有且仅有 1 个 `asr_worker`；在页面关闭 ASR 后不应存在 `asr_worker`。

### 评论对应错场次

评论以平台真实 `roomId` 绑定场次，并受直播起止时间保护。不要用主播昵称推断归属；如发现旧数据异常，重新执行刷新采集以补齐映射。
