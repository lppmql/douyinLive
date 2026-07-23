# 零食店避坑直播运营复盘系统

面向「开零食店如何避坑」知识科普直播的运营复盘系统。通过选址、预算、品牌、供应链、毛利损耗等话题吸引目标用户，用资料包引导站内私信留资。系统采集直播数据 → ASR 转写话术 → AI 复盘分析 → 知识库问答，形成完整的运营复盘闭环。

> 本项目仅用于已获授权的数据分析。请遵守平台规则与隐私法规。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3、TypeScript、Vite、SoybeanAdmin、Naive UI、ECharts |
| 后端 | FastAPI、SQLAlchemy、APScheduler、Playwright |
| 数据 | MySQL 8、Redis 7 |
| AI | DeepSeek API、FunASR、ffmpeg |
| 可视化 | DataEase（可选） |
| 监控 | Prometheus、Grafana（可选） |

## 环境要求

- macOS 或 Linux
- Docker Desktop
- Python 3.10+
- Node.js 20+ 与 pnpm
- ffmpeg

```bash
docker --version && python3 --version && node --version && pnpm --version && ffmpeg -version
```

## 快速开始

```bash
# 1. 创建配置（填写 DEEPSEEK_API_KEY）
cp .env.example .env

# 2. 安装后端依赖 + Playwright 浏览器
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cd ..

# 3. 安装前端依赖
cd frontend && pnpm install && cd ..

# 4. 一键启动
./start.sh
```

启动后访问：

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:9527 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| DataEase | http://localhost:8100（可选） |
| Prometheus | http://localhost:9090（可选） |
| Grafana | http://localhost:3000（可选） |

> 首次使用建议先看[新手图文教程](docs/beginner-guide.md)。

## 核心功能

- **扫码登录**：保存 Cookie + 浏览器指纹，登录态自动恢复
- **数据采集**：增量同步主播、直播场次、分钟指标、评论、观众画像、流地址
- **实时监控**：自动识别开播状态，直播中持续采集，下播后补齐详情
- **话术工作台**：FunASR 语音转写 → AI 评分 → 话术资产收录
- **AI 复盘工作台**：可信度评估、五维话术评分、证据提取、下一场动作建议
- **跨场对比**：同主播不同场次指标对比，曲线对齐开播后分钟
- **知识库问答**：基于真实话术/评论/指标的 AI 问答，每次回答可追溯到原场次
- **经营仪表盘**：日期筛选 + 总体指标 + 主播维度明细
- **主播排班**：从排班表导入，自动匹配实际场次，提示缺场/无效/加场
- **DataEase 大屏**：iframe 嵌入已发布大屏，通过只读语义视图保护业务数据

详细功能说明见各页面右上角「新手帮助」按钮，技术实现见[开发指南](docs/开发.md)。

## 目录结构

```
douyinLive/
├── backend/               FastAPI 后端（API、采集、AI、测试）
├── frontend/              SoybeanAdmin 前端
├── docs/                  架构、开发、部署、故障排查文档
├── scripts/               维护脚本
├── data/                  本地数据（不提交 Git）
├── observability/         Prometheus + Grafana 配置
├── .github/               CI/CD 工作流
├── Makefile               统一命令入口（make doctor/test/lint/build）
├── docker-compose.yml
└── start.sh               一键启动脚本
```

## 文档导航

| 文档 | 内容 |
|------|------|
| [开发指南](docs/开发.md) | 环境搭建、项目结构、开发流程、代码规范 |
| [部署指南](docs/部署.md) | 首次部署、发布流程、回滚、备份 |
| [故障排查](docs/故障排查.md) | 常见问题按症状→诊断→解决排查 |
| [架构决策 (ADR)](docs/adr/) | 关键技术方案选型与原因 |
| [架构文档](docs/架构/说明.md) | 架构导航与维护路线 |
| [验收测试](docs/验收测试/) | 功能验收规程与自检报告 |
| [新手教程](docs/beginner-guide.md) | 图文操作步骤 |
| [CHANGELOG](CHANGELOG.md) | 版本变更记录 |

## 数据安全

- `.env`、`data/`、`backend/storage_state/*.json` 已在 `.gitignore`，不提交 Git
- `DEBUG=false` 时，密码缺失/JWT 密钥不足 32 位会阻断启动
- DataEase 使用只读账号（`SELECT`/`SHOW VIEW`），不能修改业务数据
- MySQL/Redis/FunASR 端口默认只绑定 `127.0.0.1`
- 部署前必须替换 `JWT_SECRET_KEY`、数据库密码和所有默认密钥

## 常见问题

### 页面显示 500

先访问 http://localhost:8000/health。如果不是 `status: ok`，检查 Docker Desktop 和 MySQL 是否正常运行。

### DataEase 登录报错

通常是浏览器缓存了旧的 RSA 公钥。运行 `./start.sh` 会自动处理公钥兼容层，然后刷新登录页即可。

### 电脑卡顿

在采集页面关闭 ASR 开关释放模型内存（~1.8GB），或暂停实时监控。确认没有重复 Worker：`pgrep -af 'asr_worker'`（正常 0-1 个）。

更多问题见[故障排查手册](docs/故障排查.md)。
