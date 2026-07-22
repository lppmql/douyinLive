# CHANGELOG

本文件按时间倒序记录项目重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [2026-07-22]

### Security
- **P0-01：所有业务 API 统一登录鉴权**（影响 16 个子路由）：
  - `v1_router` 新增全局 `dependencies=[Depends(get_current_user)]`
  - auth 路由单独注册（login/refreshToken 保持公开）
  - 之前采集、复盘、场次、话术、知识库等接口无需登录即可访问
- **P0-06：保护最后一个超级管理员**：
  - 不能删除/降级最后一个 R_SUPER 管理员

### Fixed
- **P0-02：修复 ReviewFindingOut Schema 字段错配**：
  - 补回 9 个缺失字段（finding_type、description、severity、evidence 系列等）
  - 删除 2 个不存在的字段（evidence_summary、recommendation）
  - `_row_dict` 增加 datetime→ISO 字符串转换
  - 修复后更新 finding 状态不会丢失证据数据
- **P0-03：修复 ComplianceRuleOut Schema 字段错配**：
  - title/description → name/guidance/pattern（和数据库模型一致）

### Added
- **P0-04：Review API 响应契约测试**（`test_review_contracts.py`，12 个测试）：
  - workbench / finding update / compliance rules 返回值 Schema 校验
  - 所有复盘端点未登录 → 401 验证
- **P0-05：Playwright 前端冒烟测试框架**：
  - 10 个核心页面基础检查（登录→每页标题+非白屏+控制台无致命错误）
  - `pnpm e2e` 命令，`make test-frontend-e2e` 入口

### Changed
- **采集页二轮瘦身**（`index.vue` 752→204 行，-73%）：
  - 新增 `useCollectorLogin` composable：扫码登录流程独立管理（发起→轮询→成功/失败→清理）
  - 新增 `useCollectorData` composable：所有状态+数据加载+监控/采集/ASR/DataEase/日志/账号操作
  - `CollectorLogTable` 内置 logColumns 列定义（不再从父组件传入），新增 `openDetail` 事件
  - `index.vue` 精简为纯编排器：只负责组合子组件+生命周期
- **用户管理页方案 A 重构**（`index.vue` 408→108 行，-74%）：
  - 新增 `useUserManagement` composable：表格配置+搜索+CRUD+表单验证规则
  - 新增 `UserDrawer` 子组件：创建/编辑从 NModal 改为 NDrawer（侧边滑出，体验更流畅）
  - 删除确认从 `dialog.warning()` 改为 `NPopconfirm`（内联确认，不用弹窗打断操作）
  - 表单验证从手动 if 检查改为 `NForm :rules` 声明式规则
- **知识库页方案 A 重构**（`index.vue` 718→43 行，-94%）：
  - 新增 `useKnowledgeChat` composable：聊天状态+发送问题+清空对话+复制文本
  - 新增 `ChatPanel` 子组件：手写 HTML 全部替换为 Naive UI（NButton/NInput/NAlert/NSkeleton）
  - 新增 `SourcePanel` 子组件：来源卡片用 NCard+NTag 统一风格
  - 新增 `knowledge-adapter`：来源类型中文映射（话术/评论/指标/知识）
  - 新增推荐问题列表（4 个预设问题，点击即发送）
  - 打字中状态从 CSS 手写动画改为 NSkeleton 骨架屏
- **后端无改动**，三个任务全是纯前端重构

---
## [2026-07-21]

### Fixed
- **主播排班页空白修复**：后端 `AnchorScheduleDashboardResponse` Schema 只定义了 6 个旧字段（`completions`/`details`），但 `build_schedule_dashboard()` 实际返回 `summary`/`anchors`/`rows`/`reminders`/`rule` 等完整字段，被 Pydantic `response_model` 全部过滤掉，导致前端拿到的数据全是 `undefined`、页面显示空白。修复：Schema 新增 10 个字段对齐 Service 返回结构。
- **P0 生产就绪修复**（7 项）：
  - **部署文档 Worker 数量**：`docs/部署.md` 中 uvicorn `--workers 4` → `--workers 1`，加注释说明原因（BrowserManager/SchedulerManager/登录会话在进程内存中，多 Worker 会状态不一致）
  - **部署文档数据库地址**：宿主机部署时 `DB_HOST=mysql` → `127.0.0.1`、`REDIS_URL` 中 `redis` → `127.0.0.1`，加注释区分 Docker 内/外两种场景
  - **Grafana 访问方式**：从 `http://服务器IP:3000` 改为 SSH 隧道 + Nginx 反向代理两种安全方式（Compose 绑定 127.0.0.1）
  - **统一 APP_VERSION**：`config.py` 中 `0.1.0` → `0.9.0`，与版本标签一致
  - **PLAYWRIGHT_HEADLESS 生效**：`browser.py` 2 处 `headless=True` 硬编码 → `headless=settings.PLAYWRIGHT_HEADLESS`，现在可通过 `.env` 控制
  - **补齐 CI 检查**：CI 新增 ruff check + alembic check 步骤，新增 docker-check job；Makefile `check` 目标补上 `docker-check` 依赖
  - **过期文档更新**：`开发.md` 更新文件行数/任务状态/断链；`ADR 0006` 更新待办状态/文件名/行数；`验收测试/README.md` 修复 6 个英文断链

### Changed
- **主播排班页方案 A 重构**（`index.vue` 646 行 → 147 行，-77%）：
  - 新增 `utils/anchorScheduleHelpers.ts`：10 个纯工具函数（状态映射表、时间格式化、缺场/无效/加场摘要格式化）
  - 新增 `adapters/anchor-schedule-adapter.ts`：表格列定义适配器（用 h() 渲染复杂列内容）
  - 新增 `views/anchor-schedule/composables/useAnchorSchedule.ts`：排班状态管理（全部 ref + computed + 异步操作 + 生命周期）
  - 新增 4 个子组件：`AnchorScheduleStatCards`（KPI 统计卡片）、`AnchorScheduleAnchorCards`（主播完成度卡片网格）、`AnchorScheduleTable`（班次明细表格）、`AnchorScheduleReminderDrawer`（提醒抽屉）
  - `index.vue` 精简为纯编排器：只负责日期控件 + 错误提示 + 组合子组件
  - 后端无改动，纯前端重构
- **主播话术页方案 A 重构**（`index.vue` 796 行 → 154 行，-81%）：
  - 新增 `utils/transcriptHelpers.ts`：7 个纯工具函数（时间格式化、状态文案/类型映射）
  - 新增 `adapters/transcript-adapter.ts`：数据适配器（分类统计、任务卡片配置、场次下拉选项构建）
  - 新增 `views/transcripts/composables/useTranscriptWorkbench.ts`：话术工作台状态管理（全部 ref + computed + 异步操作）
  - 新增 `views/transcripts/composables/useTranscriptRealtime.ts`：WebSocket 实时话术连接管理
  - 新增 5 个子组件：`TranscriptTaskCards`（任务状态卡片）、`TranscriptSessionControl`（场次选择+工具栏）、`TranscriptStatCards`（统计卡片）、`TranscriptContentPanel`（话术内容+侧边栏）、`TranscriptTaskDrawer`（任务抽屉）
  - `index.vue` 精简为纯编排器：只负责组合子组件，所有逻辑委托 composable
  - 后端无改动，纯前端重构
- **采集页方案 A 重构**（`index.vue` 1438 行 → 752 行，模板 547 行 → 128 行）：
  - 新增 `utils/collectorHelpers.ts`：6 个纯工具函数（时间解析/格式化、日志摘要拼接）
  - 新增 `composables/useCollectorPolling.ts`：轮询 + 时钟逻辑抽离
  - 新增 7 个子组件：`CollectorStatCards`（统计卡片）、`CollectorRefreshCard`（刷新采集）、`CollectorMonitorCard`（监控）、`CollectorDataEaseCard`（DataEase）、`CollectorAccountTable`（账号表格）、`CollectorTaskDrawer`（任务抽屉）、`CollectorLogDetailModal`（日志详情）
  - `index.vue` 精简为编排器：只保留状态管理 + 数据加载 + 扫码登录流程，UI 全部委托子组件
  - 后端无改动，纯前端重构
- **AI 复盘页方案 A 重构**（`index.vue` 1000 行 → 187 行，-81%）：
  - 新增 `utils/analysisHelpers.ts`：14 个纯工具函数（日期格式化、分数判定、报告元数据、数据安全工具）
  - 新增 `adapters/review-report-adapter.ts`：报告解析适配器（原始 JSON → 类型安全 AiScoreResult/AiOptimizationResult）
  - 新增 `views/analysis/composables/useReviewWorkbench.ts`：复盘工作台状态管理（所有 ref + computed + 异步操作集中管理）
  - 新增 5 个子组件：`AnalysisSessionControl`（场次选择+启动面板）、`AnalysisStatCards`（4 张统计卡片）、`AnalysisScoreOverview`（复盘总览 Tab）、`AnalysisEvidence`（证据与发现 Tab）、`AnalysisReportHistory`（历史报告 Tab）
  - `index.vue` 精简为编排器：只负责布局 + 传递 props，所有业务逻辑交给 composable
  - 后端无改动，纯前端重构

### Added
- **Matt Pocock 工程技能体系配置**：
  - 新增 `docs/agents/issue-tracker.md`：GitHub Issues 作为问题追踪器，含 `gh` CLI 常用操作手册
  - 新增 `docs/agents/triage-labels.md`：5 标签分类体系（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）
  - 新增 `docs/agents/domain.md`：单上下文领域文档消费者规则（先读 CONTEXT.md + ADR，再探索代码）
  - 新增 `docs/agents/skill技能使用示例.md`：~25 个技能的详细中文使用示例 + 3 套组合拳场景
  - CLAUDE.md 新增 `## Agent skills` 块，注册三个配置入口
  - 新增 [ADR 0008](docs/adr/0008-引入Matt-Pocock工程技能体系.md)

### Fixed
- **采集日志不显示**：
  - 根因：`CollectorLogTable.vue` 子组件中的 `NDataTable` 使用 `flex-height` 模式，需要 CSS 设定高度才能可见。父组件 `index.vue` 的 scoped CSS 无法穿透 Vue 3 的 scoped 边界（`data-v-xxx` 只加到子组件根元素 `NCard`，不加到内部 `NDataTable`），子组件自身又没有 `<style>` 块 → 表格高度为 0 → 不可见
  - 修复：`CollectorLogTable.vue` 新增 `<style scoped>`，设置 `height: 420px`（移动端 `360px`），同时清理父组件中已失效的同名 CSS
- **scheduler.py 遗漏 import**：M5 拆分 `manual_collect.py` 时 `discover_enterprise_live_sessions` 和 `collect_live_session_snapshot` 的 import 路径未更新，导致监控器运行时 ImportError
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
