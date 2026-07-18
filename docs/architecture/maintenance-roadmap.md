# 模块化维护路线

## 当前原则

项目保持“模块化单体 + 独立重任务 Worker”，暂不拆微服务。API 负责参数和响应，业务服务负责规则，采集器、Playwright、ffmpeg、Redis 和模型调用作为基础设施适配器逐步收口。

## 已有边界

- `services/collector`：抖音登录、浏览器、采集、回放处理和调度。
- `services/asr`：转写控制、队列、分片和 Worker。
- `services/ai`：AI 客户端和零食店领域分析。
- `services/tasks`：任务标识、心跳与 Redis Streams 事件。
- `services/metrics`：指标定义与语义层。
- `services/sync`：知识库、DataEase 等下游同步。
- `views/live-session-detail/modules`：回放、统一时间轴、曲线、AI、跨场对比和话术资产组件。

## 本轮完成

- 场次详情以“视频回放 + 统一复盘分析”为主，时间轴整合告警、发现、评论、话术和指标。
- GitHub Actions 自动执行后端迁移与测试、前端类型、ESLint、Oxlint 和生产构建。
- `Makefile` 与 `scripts/doctor.sh` 提供统一的本地检查入口。
- 启动前校验关键配置，日志中的 Redis 地址自动脱敏。
- 核心链路新增可重复验收文档。
- AI 调用统一记录业务类型、真实场次、模型、Prompt 版本、Token、耗时与脱敏错误，不复制真实业务正文。
- Prometheus/Grafana 增加 AI 成功率、延迟、Token 面板及 4 条运行告警；DataEase 增加 AI 调用只读事实视图。

## 暂不一次性实施

### Transactional Outbox

当前任务状态在 MySQL 提交后写 Redis Streams，Redis 短暂失败不会阻断主业务，但仍存在事件漏发窗口。Outbox 需要新增表、发布器、重放、清理、消费幂等和迁移回滚，必须先为“采集完成 -> ASR -> AI -> 知识库 -> DataEase”补齐集成测试，再单独迁移。

### 全量目录搬迁

不在缺少回归测试时一次性把所有 API、模型和服务移动到 `modules/*`。后续按业务功能逐个迁移，每次只迁一个模块，保留公开接口并通过验收文档验证。

### ASR 重叠切片

重叠切片会改变分片索引、时间覆盖和全文去重规则，需要先准备真实脱敏边界样本与去重测试，不能直接修改生产积压任务。

### Taskiq、向量库与重型平台

现有任务已经具备 MySQL 状态、幂等键、心跳、重试和 Redis Streams 生命周期事件。没有独立压测和迁移收益数据前，不再叠加 Taskiq；Chroma/pgvector 先以真实问答召回基线做 POC；RAGFlow、Milvus、Temporal、完整 Langfuse、Dify 和 FastGPT 不进入 8GB 本机默认栈。

## 下一阶段进入条件

1. CI 连续通过。
2. 六类核心验收至少各完成一次真实数据记录。
3. Outbox 与 ASR 边界样本测试先于数据库和队列迁移。
4. 任何目录迁移都保持 API 响应兼容，并提供回滚提交。
5. AI Prompt 调整必须能按 Prompt 版本对比成功率、耗时、Token 和人工确认结果。
