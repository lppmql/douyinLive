# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 用户要求

1. 所有回答用中文
2. 我是编程新手，解释要简单
3. 每次开发前先列计划，不要直接改代码
4. 每次只开发一个阶段
5. 修改完成后必须输出：修改文件、新增文件、启动方式、测试方式、验收清单
6. 不要删除已有功能，除非我明确要求
7. 前端页面开发要遵守 soybean-admin 官方要求（Elegant Router、pnpm、ESLint、Pinia）
8. 数据采集保存数据库要遵守 dataease 的官方要求

## 项目简介

抖音留资直播数据分析系统 — 面向留资型直播间的数据复盘工具。

## 启动方式

```bash
# 一键启动全部（数据库 + 后端 + 前端）
cd /Users/lpp/douyinLive && ./start.sh

# 或者分开启动：
# 启动数据库
cd /Users/lpp/douyinLive && docker compose up -d mysql redis

# 启动后端
cd /Users/lpp/douyinLive/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs

# 启动前端
cd /Users/lpp/douyinLive/frontend
pnpm dev
# → http://localhost:5173
```

## 项目结构

```
backend/
  app/
    main.py              # FastAPI 入口
    core/                # 配置、数据库、日志
    models/              # SQLAlchemy 模型
    schemas/             # Pydantic 数据模型
    api/v1/              # API 路由
    services/            # 业务服务
      collector/         # Playwright 采集
      asr/               # FunASR 语音转文字
      sync/              # DataEase 同步
      ai/                # DeepSeek AI 分析
  workers/               # 独立 Worker 进程
frontend/                # Soybean Admin (Vue3+NaiveUI)
docs/                    # 文档
```

## 8 个开发阶段

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | 项目初始化（骨架 + Docker + 前端模板） | ✅ 完成 |
| 1 | 核心业务数据库 + CRUD API | ✅ 完成 |
| 2 | 前端 6 个页面（Mock 版） | ✅ 完成 |
| 3 | Playwright 授权登录 + 采集任务框架 | ✅ 完成 |
| 4 | 直播数据采集 | ✅ 完成 |
| 5 | m3u8 + FunASR 话术转写 | ✅ 完成 |
| 6 | DataEase 大屏表 + 同步 + 嵌入 | ⏳ |
| 7 | DeepSeek AI 分析 + 知识库问答 | ⏳ |

## 完整开发计划

详见 `/Users/lpp/.claude/plans/cheeky-zooming-flute.md`
