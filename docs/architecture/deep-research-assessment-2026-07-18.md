# 2026-07-18 深度调研落地评估

## 决策原则

本项目继续采用“模块化单体 + 独立重任务 Worker”。优先借鉴成熟项目的接口、状态和观测设计，不为了功能数量把第二套重型平台塞进 8GB 本机，也不替换已经稳定运行的 MySQL、Redis、Playwright、FunASR 和 DataEase 主链路。

## 本轮采用

| 调研建议 | 项目决策 | 落地结果 |
| --- | --- | --- |
| Langfuse 风格 AI 追踪 | 采用轻量自研元数据表 | 记录模型、Prompt 版本、Token、耗时、状态和 Trace ID，不保存业务原文 |
| OpenTelemetry 追踪思想 | 复用已有请求 Trace ID | HTTP、任务与 AI 调用可使用同一 Trace ID，暂不增加 Collector 容器 |
| Prometheus/Grafana 三层指标 | 增强现有栈 | 新增 AI 成功率、P95 延迟、Token 速率和 4 条告警 |
| DataEase 语义层 | 继续作为主 BI | 新增 `de_v_fact_ai_call_trace` 只读视图和 3 个 AI 指标定义 |
| Prompt 版本化 | 完善已有能力 | 所有主要 DeepSeek 调用记录实际 Prompt 类型和版本 |

## 已有能力，不重复建设

- 可靠任务：采集和 ASR 已有状态、幂等键、Trace ID、心跳、重试、优先级与恢复逻辑。
- 事件生命周期：Redis Streams 已保存任务事件，当前不需要为形式统一立即引入 Taskiq。
- 知识切片：MySQL 已有 5 分钟真实时间片、来源哈希、评论时间约束和可追溯证据。
- BI：DataEase 已使用 `de_v_*` 语义视图，现阶段不并行维护 Superset。

## 分阶段验证

| 候选能力 | 当前决定 | 进入条件 |
| --- | --- | --- |
| Transactional Outbox | 下一独立阶段 | 先补采集完成到知识库/DataEase的跨阶段集成测试和消费幂等测试 |
| ASR 重叠切片、VAD | 暂缓生产迁移 | 准备真实边界丢词样本、去重算法和积压任务兼容方案 |
| 采集 Provider/事件契约 | P1 渐进改造 | 先冻结评论、指标、房间状态的数据契约，不改现有 API |
| Chroma 或 pgvector | 仅做 POC | 先建立真实问答召回率、误召率和延迟基线，再决定是否增加 sidecar |
| WhisperLive/WhisperX | 仅高价值场次实验 | 有独立机器或可证明精度收益，且不影响默认单并发 FunASR |

## 不进入本机默认栈

RAGFlow、Milvus、Temporal、完整 Langfuse、Dify、FastGPT 和 Superset 都会引入额外数据库、服务或较高内存占用。只有进入多人协作、服务器化部署，且现有链路出现明确瓶颈时才单独做原型，不直接合并到主系统。

## 验收基线

1. AI 观测异常不得改变原模型调用结果。
2. JSON 格式错误必须计为失败调用。
3. 追踪表不得保存评论、完整话术、知识正文、Prompt 或模型输出原文。
4. 每次 Prompt 调整可以按版本比较成功率、耗时和 Token。
5. 新迁移必须同时通过正式数据库升级和隔离空库全量升级。
6. Prometheus 规则必须通过官方 `promtool` 校验。
