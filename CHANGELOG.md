# CHANGELOG

本文件按时间倒序记录项目重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [2026-07-21]

### Fixed
- **M1 Schema 字段修复**：
  - `KnowledgeTimeSliceStatusResponse`：5 个错误字段 → 11 个真实字段（修复 response_model 过滤导致全零数据）
  - `DataEaseSyncResponse`：新增 `selected_count`/`errors`/`removed_stale_row_count`，移除不存在的 `skipped_count`
  - `AiKbSaveResponse`/`AiKbSyncRecentResponse`/`AiPipelineResponse`：新增 `review_saved` 字段
  - 重新生成前端类型 `generated.d.ts`
- **M3 URL 常量统一**：
  - 新增 `backend/app/services/collector/constants.py`：`LEADS_BASE`/`LIVE_SCREEN_URL`/`COMMENT_URL`/`DEFAULT_FINGERPRINT`
  - 8 个文件改为从 constants 导入，URL 修改只需改 1 处
  - 修复 5 个 E402/unused-import lint 问题
- **M8 核心链路集成测试**：
  - 新增 `backend/tests/conftest.py`：SQLite 内存数据库 + FastAPI TestClient + 自动建表/删表
  - 新增 `test_integration_auth.py`（9 个测试）：登录/获取用户信息/刷新 Token 全场景覆盖
  - 新增 `test_integration_collector.py`（11 个测试）：采集状态/账号 CRUD/日志/任务
  - 新增 `test_integration_dashboard.py`（8 个测试）：汇总/日期筛选/按主播分组
  - 28 个集成测试全部通过，补充项目首个端到端 API 测试覆盖
  - LONGTEXT→TEXT SQLite 兼容适配（保存/恢复原始类型，不影响其他测试）
- **M10 全项目 Lint 清零**：
  - 后端 ruff：`--fix` 自动修复 48 个 + 手动修复 13 个（含 `l`→`lead` 变量名、`== True`→`.is_(True)`、未使用变量删除等）
  - 前端 ESLint：修复 6 个未使用变量/函数/import（analysis/transcripts/collector/knowledge 页面）
  - 47 个文件净删 73 行无用代码，ruff 0 错误 / ESLint 0 错误
- **M9 Alembic 列注释迁移**：
  - `alembic check` 检测到 45 个列注释缺失（模型已定义但数据库未同步），涉及 6 张表：`ai_call_traces`/`anchor_schedules`/`compliance_rules`/`review_action_items`/`review_findings`/`script_assets`
  - 新增迁移 `27d9dc5d2b31_phase_31_fix_missing_column_comments.py`：45 条 `ALTER TABLE ... MODIFY COLUMN ... COMMENT` + 完整 downgrade
  - 根因：3 个历史迁移（phase_23/phase_28/phase_30）创建表时漏写 `comment=` 参数
  - 修复后 `alembic check` 通过，185 测试全量通过，覆盖率 51% 不变
- **M7 .env.example 补齐 5 个缺项**：
  - 补齐 `FUNASR_HOST` / `FUNASR_PORT` / `ASR_SAMPLE_RATE` / `ASR_WORKER_MODE`（ASR 段）
  - 补齐 `JWT_ALGORITHM`（JWT 段）
- **M6 Docker Redis 硬编码密码修复**：
  - `docker-compose.yml`：Redis `--requirepass` 从硬编码密码改为 `${REDIS_PASSWORD:?...}` 环境变量
  - `.env`：新增 `REDIS_PASSWORD` 独立变量（与 `REDIS_URL` 中的密码保持同步）
  - `.env.example`：补齐 `REDIS_PASSWORD` 和带密码的 `REDIS_URL` 模板
- **M5 browser.py 冗余 .value 移除 + 缺失 import 补充**：
  - 移除 2 处 `TaskStatus.COMPLETED.value` 的冗余 `.value`（TaskStatus 继承 str，直接用即可）
  - 补充缺失的 `touch_task` / `publish_task_event` import（此前扫码登录成功后调用会 NameError）
- **M4 response_model 补齐（11 个端点）**：
  - 新增通用 `MessageResponse`（8 个 DELETE 端点复用）
  - 新增 `AccountDeleteResponse`/`LogsClearResponse`（collector 专用）
  - 复用已有 `LoginQRResponse`（登录二维码端点）
  - 3 个二进制流端点（avatar/video/playback）跳过，加 response_model 会导致 JSON 序列化崩溃
  - 前端类型从 `unknown` 变为具体类型

### Changed
- **统一任务状态枚举**（零数据库迁移）：
  - 新增 `core/status.py`：`TaskStatus` / `ReviewFindingStatus` / `ReviewActionStatus` / `ScriptAssetStatus`（str+Enum 双重继承）
  - 新增 `core/response.py`：`ok_response()` 消除 auth/user_mgmt 重复的 `_ok()` 函数
  - 66 处硬编码状态字符串（`"running"`, `"pending"`, `"failed"` 等）替换为枚举值
  - 15 个 API/Service/Schema 文件引入统一枚举
  - 新增 22 个枚举+响应包装单元测试
- **README.md 重构**（433 行 → 120 行）：
  - 精简为项目门面：项目简介 / 技术栈 / 快速开始 / 核心功能要点 / 文档导航 / 安全问题
  - 详细功能说明、UI/UX 优化记录、ASR 说明、知识库详情等分流到 `docs/开发.md`、`docs/部署.md`、`docs/故障排查.md`
  - 新增 [ADR 0007](docs/adr/0007-README重构与文档职责划分.md)：README 与 docs/ 的职责划分
- **`manual_collect.py` 模块化拆分**（2,827 行 → 8 个模块，最大 674 行）：
  - 新增 `utils.py`（231 行）— 通用工具：数值/时间解析、去重标识、Cookie 读取
  - 新增 `session.py`（225 行）— 场次 CRUD、重复场次合并修复、主播资料写入
  - 新增 `comments.py`（210 行）— 评论页抓取、增量/全量入库、DOM 兜底解析
  - 新增 `metrics.py`（226 行）— 实时/趋势指标入库、画像解析、摘要映射
  - 新增 `room.py`（674 行）— 大屏页数据捕获、主页直播卡片、流地址抓取
  - 新增 `enterprise.py`（370 行）— 企业员工接口、主播场次映射、直播发现
  - 新增 `history.py`（427 行）— 历史场次同步、详情补齐、实时快照
  - `manual_collect.py`（667 行）— 精简为编排器 + 进度报告 + 错误处理
  - 4 个测试文件导入路径同步更新
  - 消除未使用函数 `_is_context_closed_error`（与 `_is_context_closed_message` 重复）
  - 消除 `_comment_belongs_to_session` 对 LiveSession 模型的冗余依赖
  - `_fetch_enterprise_post` 从 manual_collect 分离到 room，enterprise 反向导入

### Added
- **项目维护体系建立**：
  - 打首个版本标签 `v0.9.0`
  - 新增 `docs/开发.md` 开发指南（含目录结构、开发流程、代码红线、职责分层）
  - 新增 `docs/部署.md` 部署指南（含首次部署、发布流程、回滚方案、备份策略）
  - 新增 `docs/故障排查.md` 故障排查手册（按症状→诊断→解决的结构）
  - 新增 `docs/adr/0006-项目维护标准与红线.md`
- **docs 英文文件名改为中文**：
  - `deployment.md` → `部署.md`、`development.md` → `开发.md`、`troubleshooting.md` → `故障排查.md`
  - `acceptance/` → `验收测试/`、`architecture/` → `架构/`、`audits/` → `审计/`
  - 同步更新 README / CHANGELOG / 架构 README 中的引用路径
- **Makefile 扩展**：
  - 新增 `check` 目标：一键运行测试 + lint + 构建 + 数据库迁移检查
  - 新增 `lint-backend`（ruff）、`db-check`（alembic check）、`docker-check`（docker compose config）
  - 新增 `lint` 目标现在同时检查前后端

---

## [2026-07-20]

### Added
- **首页重做为经营仪表盘**：
  - 日期筛选：今天（默认）/ 本周 / 上周 / 本月 / 上月 + 自定义日期范围选择器
  - 8 张总体经营指标卡片：总场次、总观看、总评论、总私信/线索、广告花费、平均线索成本、待办复盘、活跃主播
  - 主播数据明细表：按主播分组展示场次/观看/评论/私信/线索/新增粉丝/互动/广告花费
  - 后端 `GET /dashboard/summary` 新增 `start_date` / `end_date` 日期参数
  - 后端新增 `GET /dashboard/summary/by-anchor` 按主播分组端点
  - 快捷入口改为：直播场次、话术转写、AI 复盘、知识库
  - 将面向运维的采集状态卡片移出首页

### Removed
- `frontend/src/views/home/modules/` — 6 个 SoybeanAdmin 模板 mock 组件（硬编码假数据，从未被使用）

### Changed
- **播放器整场进度条 + 复盘时间轴联动**：
  - 去掉原生 video controls，改为自定义控制栏
  - 进度条宽度 = 整场直播时长（非仅视频缓冲），点击直接跳转
  - 进度条上标记复盘发现（红/黄/蓝小竖线），hover 显示标题
  - 视频播放进度实时同步到右侧复盘时间轴（高亮当前节点）
  - 点击时间轴节点 → 视频同步跳转
  - 键盘 ← → 控制快退/快进 10 秒
- **播放器卡顿优化**：
  - timeupdate 节流到 250ms（~4fps），Pinia store 更新频率降低 60-75%
  - 进度条 width → transform: scaleX()，GPU 合成层，避免 Layout Reflow
  - 去掉进度条 CSS transition，避免 200ms 动画与高频更新互相冲突导致抖动
  - isPlaying 只在状态真正变化时更新，避免无谓重渲染

### Fixed
- **直播场次详情页 `Cannot read properties of undefined (reading 'map')` 崩溃**：
  - 根因：`ReviewComparisonResponse` Pydantic schema 字段名（`primary`/`baseline`）与 `compare_sessions()` 实际返回（`current`/`baseline`/`dimensions`/`current_series`/`baseline_series`/`comparison_note`）不匹配
  - FastAPI `response_model` 过滤掉未声明字段 → 前端 `comparison.value.current_series` 为 `undefined` → `.map()` 崩溃
  - 修复：schema 字段改为匹配实际返回值，前端添加防御性 `|| []` 保护
  - 新增全局 Vue 错误处理器（`main.ts`）：捕获 `.map()` 错误并输出精确堆栈

### Added
- 根 `.env` 新增 `CORS_ORIGINS` / `BACKEND_RELOAD` 变量
- `config.py` 新增 `extra="ignore"`，兼容 docker-compose / start.sh 专用变量
- 前端 `VITE_ICONIFY_URL` 待配置注释
- 后端 ~40 个端点补齐 Pydantic `response_model`（`schemas/ai.py`, `transcript.py`, `dashboard.py`, `knowledge.py`）
- **契约强制**：`openapi-typescript` 自动从后端 OpenAPI schema 生成前端 TypeScript 类型（`pnpm gen-api`）
- CI 新增 `check-api-types` job：后端改 Pydantic 字段 → 前端类型不同步 → 构建变红
- `frontend/scripts/generate-api-types.ts`：支持本地和 CI 两种模式
- `frontend/src/typings/api/generated.d.ts`：7910 行自动生成的 API 类型定义
- Dependabot groups：npm/pip 的 patch 和 minor 各合并为一个 PR（不再 10 个分散 PR）
- pytest-cov + CI 覆盖率红线（初始阈值 50%）
- `docs/adr/` 目录：5 个架构决策记录（只增不改）
- `docs/架构/README.md`：架构文档导航
- `docs/adr/0002-*`：绞杀者迁移模板（7 步标准流程）
- `CHANGELOG.md`：按时间倒序的版本变更记录

### Changed
- CORS `allow_origins` 从 `main.py` 硬编码改为读取 `settings.CORS_ORIGINS`
- docker-compose `DATAEASE_ORIGIN_LIST` 改为 `${CORS_ORIGINS:-...}`
- 前后端 `.env` 分离：根 `.env` 纯后端变量，`frontend/.env` 纯 VITE_* 变量
- `.gitignore`: `.env` → `/.env`（只忽略根目录含密钥的 .env）
- 部分架构文档从 `docs/架构/` 迁移为 ADR 格式

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
