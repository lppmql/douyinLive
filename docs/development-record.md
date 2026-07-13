# 抖音留资直播数据分析系统 — 开发记录

## 项目简介

面向留资型直播间的数据复盘工具。Playwright 采集授权后台数据 → FunASR 话术转写 → DeepSeek AI 分析 → DataEase 数据大屏。

---

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + MySQL + Redis |
| 前端 | Soybean Admin (Vue3 + NaiveUI + ECharts) |
| 采集 | Playwright (Chromium) |
| 语音 | FunASR 2pass WebSocket |
| AI | DeepSeek (OpenAI 兼容 SDK) |
| 大屏 | DataEase v2.10.25 |
| 容器 | Docker Compose |

---

## 启动方式

```bash
# 一键启动全部
cd /Users/lpp/douyinLive && ./start.sh

# 或分开启动
docker compose up -d mysql redis
docker compose --profile dataease up -d dataease
docker compose --profile funasr up -d funasr
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && pnpm dev
```

---

## 各阶段开发记录

### Phase 8 — 用户认证 + Soybean Admin 内置功能 + 用户管理

**目标：** 建立完整的用户认证体系，激活 Soybean Admin 的 7 个内置功能。

**后端改动：**
- `requirements.txt` — 添加 `pyjwt`、`passlib[bcrypt]`、`bcrypt`
- `app/core/config.py` — 新增 JWT 配置项（SECRET_KEY、ALGORITHM、过期时间）
- `app/core/security.py` — JWT 签发/验证 + bcrypt 密码哈希 + `get_current_user` 依赖
- `app/models/user.py` — User 模型（id, username, password_hash, nickname, email, phone, avatar, roles, status）
- `app/schemas/auth.py` — 登录/用户信息的 Pydantic Schema
- `app/api/v1/auth.py` — 认证 API：`POST /login`、`GET /getUserInfo`、`POST /refreshToken`
- `app/api/v1/user_mgmt.py` — 用户管理 CRUD（分页列表、新建、编辑、删除）
- Alembic 迁移 `g1d2e3f4a5b6` — 创建 `users` 表 + 插入默认 admin/user

**前端改动：**
- `service/api/auth.ts` — 从 `request`(Mock) 切换为 `backendRequest`(真实后端)
- `service/request/index.ts` — `backendRequest` 适配 Soybean Admin 的 `{code, data, msg}` 响应格式
- `service/api/user.ts` — 用户管理 API 服务
- `views/user-management/index.vue` — 用户管理页面（NDataTable + 新增/编辑对话框 + 删除确认）
- `views/dashboard/index.vue` — KPI 卡片改用 CountTo 数字动画组件
- `views/live-sessions/index.vue` — 表格增加 `TableHeaderOperation` 组件
- `router/elegant/routes.ts` — 注册用户管理路由（图标 mdi:account-group，order: 8，仅 R_SUPER 可访问）
- i18n — 添加 `route.user-management` 中英文翻译

**详情：** Soybean Admin 的登录页、Iframe 页面、CountTo、TableHeaderOperation/TableColumnSetting、锁屏功能、403/404/500 页面均为框架内置，本次主要工作是后端提供认证 API + 前端切换为真实后端。

### Phase 0 — 项目初始化
- FastAPI 骨架 + Soybean Admin 模板
- Docker Compose (MySQL + Redis)
- 基础配置、数据库连接、日志

### Phase 1 — 核心业务数据库 + CRUD API
- 10 张业务表（live_rooms、live_sessions、live_metrics、comments、leads 等）
- Alembic 迁移 + 基础 CRUD API

### Phase 2 — 前端 6 个页面（Mock 版）
- 数据大屏、采集、直播场次、话术、AI 分析、知识库

### Phase 3 — Playwright 授权登录 + 采集任务框架
- 扫码登录 cluerich（有头浏览器 → 持久化 Cookie + StorageState）
- 浏览器管理器单例（指纹固定、反检测、上下文复用）
- 采集任务表 + 日志表 + 登录状态 API

### Phase 4 — 直播数据采集
- 开播检测（定时轮询）→ 自动采集指标/评论/画像/留资 → 入库
- 下播检测自动结束场次 + 触发同步

### Phase 5 — FunASR 话术转写
- FunASR 2pass WebSocket 服务 (docker, ws://localhost:10096)
- ffmpeg pipe 拉 m3u8 流 → 16kHz PCM → FunASR 转写
- 转写结果写入 transcript_segments + WebSocket 实时推送

### Phase 6 — DataEase 大屏
- 7 张 de_ 汇总宽表 + 同步服务（INSERT ... ON DUPLICATE KEY UPDATE）
- DataEase v2.10.25 容器部署（端口 8100，复用业务 MySQL）
- 下播自动触发同步

### Phase 7 — DeepSeek AI 分析 + 知识库问答
- DeepSeek API 客户端（chat / chat_json / chat_stream）
- 提示词模板管理（6 类模板，数据库存储）
- 话术评分（完整性/互动性/留资引导/亲和力）
- 趋势分析（多场对比）、异常检测、优化建议
- 高意向用户识别（AI 从评论中识别 → high_intent_users 表）
- 知识库问答（搜索 + 拼接上下文 → DeepSeek 回答）
- 前端分析页 + 知识库聊天窗对接

---

## 数据库表

| 组 | 数量 | 说明 |
|----|------|------|
| 业务表 | 12 张 | live_rooms、live_sessions、live_metrics、comments、leads、transcript_segments、transcript_full_texts、high_intent_users、analysis_reports、knowledge_base、prompt_templates、stream_sources |
| 采集表 | 3 张 | scraper_accounts、scraper_tasks、scraper_logs |
| ASR 表 | 1 张 | asr_tasks |
| 大屏表 | 7 张 | de_live_session_anchor_summary、de_anchor_realtime_metrics、de_anchor_conversion_funnel、de_anchor_audience_profile、de_anchor_comment_summary、de_anchor_transcript_summary、de_anchor_ai_analysis_summary |

---

## 服务端口

| 服务 | 端口 | 访问 |
|------|------|------|
| MySQL | 3306 | 内部 |
| Redis | 6379 | 内部 |
| FastAPI | 8000 | http://localhost:8000/docs |
| Soybean Admin | 9527 | http://localhost:9527 |
| DataEase | 8100 | http://localhost:8100 (admin / DataEase@123456) |
| FunASR | 10096 | ws://localhost:10096 |

---

## 已知问题

1. FunASR 首次启动需下载模型（约 1.5GB），耗时 3-5 分钟
2. DataEase 在 Mac Docker 上访问需**无痕窗口**清除旧 token 缓存
3. Playwright 扫码登录依赖 cluerich.com 页面结构，变化时需更新选择器
4. ASR 并发默认限制 1 路，生产环境需调整 `MAX_REALTIME_ASR_TASKS`
