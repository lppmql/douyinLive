# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 用户要求

1. 所有回答用中文
2. 我是编程新手，解释要清楚
3. 每次开发前先列计划，不要直接改代码
4.
5. 修改完成后必须输出：修改文件、新增文件、启动方式、测试方式、验收清单
6. 不要删除已有功能，除非我明确要求
7. 前端页面开发要遵守 soybean-admin 官方要求（Elegant Router、pnpm、ESLint、Pinia）
8. 数据采集保存数据库要遵守 dataease 的官方要求
9. 每次任务完成后用Playwright跑一遍测试发现问题并修复

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
# → http://localhost:9527（Vite 配置端口 9527，--mode test 加载 .env.test）
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

## 开发记录

详见 `docs/development-record.md`
