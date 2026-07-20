# ADR 0001: 模块化单体 + 轻量可观测性

- **日期**: 2026-07-18
- **状态**: accepted
- **决策者**: 项目维护者

## 背景

项目需要在一台 8GB Mac 上运行完整的数据采集、ASR 转写、AI 分析、DataEase 可视化和 Prometheus/Grafana 监控。需要决定：架构是拆微服务、引入重型平台，还是在"模块化单体"内继续演进。

## 决策

1. **继续采用"模块化单体 + 独立重任务 Worker"**，不拆微服务。
   - API 负责参数和响应，业务服务负责规则
   - 采集器、Playwright、ffmpeg、Redis 和模型调用作为基础设施适配器逐步收口

2. **AI 调用追踪采用自建轻量表**（`ai_call_traces`），不引入完整 Langfuse。
   - 记录业务类型、场次 ID、模型、Prompt 版本、Token、耗时和脱敏错误
   - 不保存完整 Prompt 原文和模型输出

3. **Prometheus/Grafana 只做核心指标**：AI 成功率、P95 延迟、Token 速率，4 条告警规则。
   - DataEase 通过只读视图 `de_v_fact_ai_call_trace` 分析成功率和成本

4. **明确暂不引入**：RAGFlow、Milvus、Temporal、Langfuse、Dify、FastGPT、Taskiq、Chroma/pgvector（需 POC 先）

## 后果

- ✅ 部署简单：`./start.sh` 一键启动全栈
- ✅ 资源可控：ASR 1.8GB、DataEase 1.2GB、Prometheus/Grafana 各 512MB
- ⚠️ 没有分布式追踪（OpenTelemetry traces），目前只靠请求级 `X-Trace-ID`
- ⚠️ 没有 Outbox 模式保证事件不丢（Redis Streams 失败时可能漏发）
- ⚠️ AI Prompt 版本对比依赖自建表，没有 Langfuse 的可视化界面
