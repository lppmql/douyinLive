# 开发指南

> 面向新加入项目的开发者。读完本文后你应该能够在本机启动项目、理解代码结构、完成一次完整的开发流程。

## 环境要求

| 依赖 | 最低版本 | 检查命令 |
|------|---------|---------|
| Docker Desktop | 最新稳定版 | `docker --version` |
| Python | 3.10+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| pnpm | 8+ | `pnpm --version` |
| ffmpeg | 5+ | `ffmpeg -version` |

## 首次安装（5 步）

```bash
# 1. 创建本地配置
cp .env.example .env
# 编辑 .env，至少填写 DEEPSEEK_API_KEY

# 2. 安装后端依赖
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cd ..

# 3. 安装前端依赖
cd frontend
pnpm install
cd ..

# 4. 启动全部服务
./start.sh

# 5. 初始化数据库
cd backend && source .venv/bin/activate && alembic upgrade head
```

启动后访问：
- 前端：http://localhost:9527
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 日常开发命令

所有命令都封装在 Makefile 中，从项目根目录执行：

```bash
make doctor       # 检查环境是否正常（依赖、容器、磁盘、端口）
make test         # 运行后端测试 + 前端类型检查
make test-backend # 只跑后端 pytest
make test-frontend# 只跑前端类型检查
make lint         # 前端 ESLint + Oxlint
make build        # 前端生产构建
make migrate      # 数据库升级到最新版本
make start        # 一键启动全栈
```

## 项目结构速览

```
douyinLive/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # 19 个路由文件（按业务域命名）
│   │   ├── models/           # 24 个 SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── services/         # 业务逻辑层
│   │   │   ├── ai/           # DeepSeek 调用、评分、复盘、知识库
│   │   │   ├── asr/          # FunASR 转写、队列、WebSocket
│   │   │   ├── collector/    # Playwright 采集、浏览器管理、视频下载
│   │   │   ├── metrics/      # 指标语义层
│   │   │   ├── sync/         # DataEase 同步
│   │   │   └── tasks/        # 任务运行时
│   │   ├── core/             # 配置、数据库、安全、日志、可观测性
│   │   └── main.py           # FastAPI 入口
│   ├── alembic/              # 数据库迁移（31 个版本）
│   └── tests/                # 27 个测试文件
├── frontend/
│   └── src/
│       ├── views/            # 页面组件（按业务域命名）
│       ├── service/api/      # API 调用函数
│       ├── typings/api/      # TypeScript 类型定义
│       ├── store/            # Pinia 状态管理
│       └── router/           # Elegant Router 路由
├── docs/                     # 架构、验收、开发文档
├── docker-compose.yml        # MySQL、Redis、FunASR、DataEase、监控
├── start.sh                  # 本地一键启动
├── Makefile                  # 统一命令入口
└── .env                      # 后端配置（密钥、数据库密码）
```

## 开发流程（每次改代码都按这个来）

### 1. 开始前

```bash
git pull origin main          # 拉最新代码
make doctor                   # 确认环境正常
```

### 2. 修改代码

**一次只改一个明确目标。** 比如"给首页加导出按钮"是一个目标，"同时优化导出和修复采集 bug"是两个目标——应该分两次提交。

**后端改动：**

- API 接口必须写 `response_model`（已有 40+ 接口这样做）
- 新接口/改字段 → 同步更新 `schemas/` 下的 Pydantic 模型
- 数据库结构变更 → 必须走 Alembic（见下方）
- 新业务逻辑放 `services/`，不要在 `api/` 里写复杂逻辑

**前端改动：**

- 页面组件放 `views/`，可复用组件抽到 `components/`
- API 调用放 `service/api/douyin.ts`
- TypeScript 类型放 `typings/api/douyin.d.ts`
- **禁止手写后端已有的响应类型**——改后端 Schema 后执行 `pnpm gen-api` 自动生成

### 3. 后端 Schema 改了之后（必须做）

```bash
cd frontend
pnpm gen-api         # 从 OpenAPI 重新生成 TypeScript 类型
pnpm typecheck       # 确保前端类型与后端一致
```

**前后端类型不同步会导致线上运行时崩溃。** CI 会拦截这种情况，但本地先跑一遍更快。

### 4. 数据库改了之后（必须做）

```bash
# 1. 修改 ORM 模型（backend/app/models/）
# 2. 生成迁移
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "描述你的改动"

# 3. 人工检查生成的迁移文件（backend/alembic/versions/）
#    确保它只包含你想要的变更，没有误删字段或表

# 4. 本地测试升级 + 降级 + 再升级
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 5. 确认没问题后提交迁移文件
```

**禁止：**
- 手动直接改数据库表
- 修改已经合并到 main 的迁移文件
- 用 `create_all()` 替代迁移
- 删除字段前不做数据备份

### 5. 提交前检查

```bash
make test    # 后端 pytest + 前端 typecheck
make lint    # 前端 ESLint + Oxlint
make build   # 前端生产构建（确认能构建成功）
```

全部通过后才能提交。

### 6. 提交规范

```bash
git add <文件>
git commit -m "类型: 日期 简短描述"
```

类型用这些：
- `feat:` 新功能
- `fix:` 修复 bug
- `perf:` 性能优化
- `refactor:` 重构（不改变功能）
- `docs:` 文档
- `chore:` 工具链、配置

示例：`feat: 2026-07-21 首页新增导出按钮`

### 7. 更新 CHANGELOG

在 `CHANGELOG.md` 顶部对应日期下添加变更记录。按 Added / Changed / Fixed / Removed 分类。

如果改动了架构决策（比如换了一个关键技术方案），在 `docs/adr/` 新增 ADR。

### 8. 推送

```bash
git push origin main
```

## 代码红线

这些不是硬规定，但每次评审都会检查：

```
Python 文件超过 500 行 → 评估拆分
Vue 文件超过 400 行    → 评估拆分
单个函数超过 80 行     → 优先拆分
函数参数超过 6 个      → 考虑用对象
```

当前最需要关注的超大文件：

| 文件 | 行数 | 优先级 |
|------|------|--------|
| `services/collector/manual_collect.py` | 2,826 | 🔴 最高 |
| `views/collector/index.vue` | 1,506 | 🔴 最高 |
| `views/analysis/index.vue` | 1,020 | 🟡 高 |
| `services/collector/browser.py` | 819 | 🟡 高 |
| `views/transcripts/index.vue` | 811 | 🟡 高 |

## 职责分层（后端）

```
api.py         → 只处理请求参数和返回响应
schemas.py     → 只定义接口数据结构
service.py     → 只处理业务逻辑
repository.py  → 只操作数据库（未来引入）
models.py      → 只定义 ORM 模型
```

目前 services 层部分文件直接写 SQLAlchemy 查询。长期方向是引入 repository 层，但这不是当前最紧急的事。

**一个 service 不应该同时做：** Playwright + MySQL + Redis + AI + ffmpeg。这些外部能力应该通过 `infrastructure/` 或独立 service 调用。

## 测试分层

```
单元测试   → 纯业务逻辑（线索判断、指标计算、AI 输出解析）
集成测试   → API + MySQL、任务状态流转、Alembic 迁移
核心链路   → 创建模拟场次 → AI 复盘 → 首页统计（端到端）
```

## 环境变量规范

```
根 .env       → 后端、Docker、密钥（不进入浏览器）
frontend/.env → 只放 VITE_* 前缀的公共配置
```

每个变量应标注：用途、默认值、是否必填、是否敏感、修改后需不需要重启。

## 任务状态规范（待统一）

所有后台任务（采集、ASR、AI 分析）使用同一套状态：

```
pending   → 已创建，等待执行
queued    → 已入队
running   → 执行中
retrying  → 失败后重试中
succeeded → 成功
failed    → 失败
cancelled → 已取消
```

## 相关文档

- [架构决策记录 (ADR)](adr/) — 为什么这样设计
- [部署指南](deployment.md) — 部署到服务器
- [故障排查](troubleshooting.md) — 常见问题及解决方案
- [CHANGELOG](../CHANGELOG.md) — 版本变更记录
- [README](../README.md) — 项目概述
