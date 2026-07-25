# ADR 0019：m3u8 流地址自动刷新

**日期**：2026-07-25
**状态**：已采纳
**决策者**：lppmql

---

## 背景

抖音 m3u8 流地址是临时生成的，通常只有几小时到一天的有效期。系统在采集直播数据时会把 m3u8 URL 存入 `stream_sources` 表和 `live_sessions.stream_url` 字段，但后续 ASR 转写或视频回放可能在几小时甚至几天后才进行——此时流地址可能已过期，导致：

1. **视频播放黑屏**：后端 ffmpeg 拉不到流，前端播放器报错
2. **ASR 话术转写返回空结果**：FunASR 收不到音频数据

之前唯一的处理方式是把 `stream_sources.status` 标记为 `expired`（下播时），用户需要手动重新采集。体验很差。

## 决策

**实现自动刷新机制**：当检测到 m3u8 过期时，自动用已保存的 Cookie（`storage_state` 文件）打开抖音企业后台大屏页面，重新抓取新的流地址，全程无需人工操作。

### 架构设计

```
ASR Worker / 前端播放器
        │
        ▼
  probe_stream_url()  ← ffmpeg 快速探测（2-3 秒）
        │
   ┌────┴────┐
   │ alive   │ expired
   ▼         ▼
 正常处理   POST /api/v1/.../refresh-stream
              │
              ▼
         refresh_session_stream_url()
              │
         ┌────┴────┐
         │ 成功     │ 失败
         ▼          ▼
    用新 URL   明确报错原因
    继续处理   （Cookie 过期/回放已删/页面变动）
```

### 关键设计决策

| 决策 | 理由 |
|------|------|
| 刷新 API 放 `stream_router`（无需 JWT） | ASR Worker 是独立进程，不经过 FastAPI 的认证中间件；和视频流端点一致，都无需认证 |
| ASR Worker 通过 HTTP 调 API 而不是直接操作浏览器 | 浏览器实例（Playwright + Cookie）在 FastAPI 进程中；ASR Worker 是独立进程，共享浏览器会有状态竞争问题 |
| 探测用 ffmpeg 拉 2 秒流而不是 HEAD 请求 | HEAD 请求只能验证 m3u8 文件可访问，不能验证 ts 分片实际可拉；ffmpeg 真实拉流更可靠 |
| 探测失败不阻断转写 | ffmpeg 探测可能误判（网络波动），失败后仍用原 URL 尝试，万一误判还能转成功 |

### 备选方案

| 方案 | 优点 | 缺点 | 为何不选 |
|------|------|------|----------|
| ASR Worker 内嵌 Playwright | 不依赖 HTTP 调用 | 两个进程各维护一套浏览器，资源浪费 + Cookie 状态可能冲突 | 架构不干净 |
| 定时刷新（cron） | 实现简单 | 不知道什么时候过期，定时太频繁浪费资源，太稀疏可能错过 | 不精确 |
| 只检测不刷新 | 实现最简单 | 用户还是要手动操作，体验差 | 用户要求自动 |

## 影响

- **新文件**：`backend/app/services/collector/stream_health.py`（健康探测）、`backend/app/services/collector/stream_refresh.py`（自动刷新）
- **修改文件**：`live_sessions.py`（刷新 API）、`asr_worker.py`（转写前探测+刷新）、前端播放器和转写卡片
- **外部依赖**：ffmpeg（已有）、httpx（已有）、Playwright + Cookie（已有）
- **性能**：每次 ASR 转写前多 2-3 秒探测时间（仅探测时），刷新时多 10-30 秒（打开页面+抓取）
