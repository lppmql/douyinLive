# ADR 0020：ASR 转写失败修复——FunASR 自动恢复 + 流刷新优化

**日期**：2026-07-25
**状态**：已采纳
**决策者**：lppmql

---

## 背景

ASR 话术转写在 2026-07-22 至 2026-07-25 期间频繁失败，通过分析 ASR Worker 日志（5.4MB 日志文件），发现 6 种失败模式：

| 模式 | 占比 | 根因 |
|------|------|------|
| FunASR 容器崩溃 | ~95% | Docker 容器 OOM（8GB Mac 上同时跑 Paraformer 大模型 + DataEase + MySQL + Redis 等） |
| 流地址过期 (403/404) | ~3% | 抖音 m3u8 临时 URL 几小时后失效 |
| 所有分片无人声 | ~1% | 流可能无音频轨道 |
| 数据库连接丢失 | <1% | Worker 长时间运行后 MySQL 超时 |
| 全文 TEXT 溢出 | <1% | 已修复（`_save_full_text` 有防御代码） |

**核心问题**：
1. **FunASR 崩溃后 Worker 傻等 300 秒**——`ASR_ENGINE_READY_TIMEOUT_SECONDS=300`，等待期间不做任何恢复操作
2. **流刷新失败后仍用过期 URL 硬转**——`_auto_refresh_stream_if_expired` 第 3 步，刷新失败时回退到原过期 URL，必然再次失败
3. **FunASR 容器内存上限偏高**——`mem_limit: 1800m`，接近 8GB Mac 的可用上限

## 决策

**三层修复，由急到缓：**

### 1. FunASR 崩溃自动重启（治本）

在 `AsrWorker` 中新增 `_ensure_funasr_alive()` 方法：
- 转写前执行 `docker ps` 检查容器是否在运行
- 容器挂了 → 自动执行 `docker restart douyin_live_funasr`
- 成功 → 日志记录，`_process_chunk` 的等待循环处理连接（60 秒超时，不是 300 秒）
- 失败 → 立即抛 `RuntimeError`，给出手动排查指引

同时把 FunASR 连接等待从 **300 秒降到 60 秒**，配合容器自动重启机制，总等待时间从"傻等 5 分钟"变成"重启 + 最多 1 分钟"。

### 2. 流刷新失败不再硬转

`_auto_refresh_stream_if_expired` 第 3 步改为分情况处理：
- **明确过期**（探测到 403/404/410）且刷新失败 → 直接抛 `RuntimeError`，不浪费队列资源
- **探测不明确**（网络波动/超时）→ 保留原容错逻辑，用原 URL 继续尝试

### 3. FunASR 内存上限收紧

`docker-compose.yml` 中 `mem_limit: 1800m` → `1600m`，给系统留更多余量。实测 Paraformer 模型加载后约占用 1.2-1.4GB，1.6GB 仍有余量。

### 关键设计决策

| 决策 | 理由 |
|------|------|
| 用 `subprocess` 调 `docker` CLI 而不是 Docker SDK | 省去额外 Python 依赖，Worker 环境已有 Docker CLI |
| 容器名和超时秒数抽为类常量 (`_FUNASR_CONTAINER`, `_FUNASR_CONNECT_TIMEOUT`) | 若容器名变化或模型变大，只改一处 |
| `pool_pre_ping=True` 已在 `database.py` | 无需额外修改数据库连接池配置 |
| 不把 60 秒超时写回 `settings.ASR_ENGINE_READY_TIMEOUT_SECONDS` | 那个配置项 300 秒仍用于其他场景（如首次启动等模型下载），Worker 级别用更短的类常量覆盖 |

### 备选方案

| 方案 | 优点 | 缺点 | 为何不选 |
|------|------|------|----------|
| 用 prometheus + alertmanager 监控 FunASR | 正规监控方案 | 过重，8GB 电脑再跑监控更吃内存 | 简单直接更合适 |
| ASR Worker 内嵌 Playwright 替代 HTTP API 刷新流 | 减少依赖 | 两个进程各维护浏览器，Cookie 状态冲突 | ADR 0019 已决策分离 |

## 影响

- **修改文件**：`backend/workers/asr_worker.py`（+62 行）、`docker-compose.yml`（1 行）
- **不需要改**：`backend/app/core/database.py`（`pool_pre_ping=True` 已就位）
- **外部依赖**：Docker CLI（已有）、asyncio（已有）
- **用户体验**：转写失败后不用人工重启 FunASR，Worker 会自动恢复；流过期后不会反复失败占队列
