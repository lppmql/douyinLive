# CHANGELOG

本文件按时间倒序记录项目重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [2026-07-20]

### Added
- 根 `.env` 新增 `CORS_ORIGINS` / `BACKEND_RELOAD` 变量
- `config.py` 新增 `extra="ignore"`，兼容 docker-compose / start.sh 专用变量
- 前端 `VITE_ICONIFY_URL` 待配置注释
- 后端 ~40 个端点补齐 Pydantic `response_model`（`schemas/ai.py`, `transcript.py`, `dashboard.py`, `knowledge.py`）

### Changed
- CORS `allow_origins` 从 `main.py` 硬编码改为读取 `settings.CORS_ORIGINS`
- docker-compose `DATAEASE_ORIGIN_LIST` 改为 `${CORS_ORIGINS:-...}`
- 前后端 `.env` 分离：根 `.env` 纯后端变量，`frontend/.env` 纯 VITE_* 变量
- `.gitignore`: `.env` → `/.env`（只忽略根目录含密钥的 .env）

### Removed
- `packages/alova/` — 未使用的 HTTP 客户端包（项目用 `@sa/axios`）
- `frontend/.env.prod`, `frontend/.env.test` — SoybeanAdmin 模板 mock 地址
- `.env.production`, `.env.test` — 多余的 Vite mode 文件

### Fixed
- 全站 UI/UX 优化：无障碍（aria-label、44px 触控目标）、8px 间距节奏、暗色模式对比度、图标统一 mdi:
- 安全区域适配（刘海屏/灵动岛）
- `business-focus-ring` / `business-active-press` 通用样式类

---

## [2026-07-18]

### Added
- DataEase 数据大屏 iframe 嵌入
- 内网穿透支持（ngrok）
- 采集刷新全部待补场次
- 前端全站体验优化：响应式栅格、加载状态、失败重试、轮询暂停
- 后端 `settings.runtime_configuration_issues()` 启动前校验
- Prometheus/Grafana 4 条告警规则
- DataEase 只读语义视图（`de_v_*`）
- `ai_call_traces` 表（轻量 Langfuse 风格追踪）
- 主播排班 `de_v_fact_anchor_schedule` 视图
- 复盘发现、整改任务、话术资产接口

### Changed
- 直播场次列表性能优化（数据库分页、轻量字段、索引）
- 长场次可靠性（`LONGTEXT` 保存，Worker 异常回滚）
- 话术工作台：默认最新场次、自动队列、活跃任务 5s 刷新
- 场次详情重构：视频回放 + 统一复盘分析
- 前后端协调验收

### Fixed
- DataEase 登录旧密钥异常
- 采集日志清空二次确认
- ASR 空状态不再误报 404

---

## 模板

后续版本按此格式追加：

```markdown
## [YYYY-MM-DD]

### Added
- 新增的功能

### Changed
- 行为变更

### Fixed
- 已修复的 bug

### Removed
- 已删除的功能
```
