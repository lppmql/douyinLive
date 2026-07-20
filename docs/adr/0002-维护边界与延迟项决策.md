# ADR 0002: 维护边界与延迟项

- **日期**: 2026-07-18
- **状态**: accepted
- **决策者**: 项目维护者

## 背景

项目已有 6 个服务域（collector/asr/ai/tasks/metrics/sync）和 23 个前端视图。需要决定哪些改造立刻做、哪些延后、以及目录搬迁的策略。

## 决策

### 当前服务边界

| 服务 | 职责 |
|---|---|
| `services/collector` | 抖音登录、浏览器管理、采集、回放处理、调度 |
| `services/asr` | 转写控制、FunASR 队列、分片、Worker |
| `services/ai` | DeepSeek 客户端、评分、复盘、知识库、时间片 |
| `services/tasks` | 任务标识、心跳、Redis Streams 事件 |
| `services/metrics` | 指标定义与语义层 |
| `services/sync` | 知识库同步、DataEase 宽表写入 |

### 本轮已完成

- 场次详情重构（视频回放 + 复盘分析）
- CI 完整流水线（后端迁移测试 + 前端 typecheck/lint/build）
- `Makefile` + `scripts/doctor.sh` 统一检查入口
- 启动前配置校验（密钥强度、端口冲突）
- AI 调用元数据记录（`ai_call_traces`）

### 明确延迟

| 项目 | 原因 | 进入条件 |
|---|---|---|
| Transactional Outbox | 需要新增表、发布器、重放机制 | 补齐"采集→ASR→AI→知识库→DataEase"集成测试 |
| 全量目录搬迁 | 缺少回归测试，一次性搬迁风险大 | 按绞杀者模式逐模块迁移 |
| ASR 重叠切片 | 会改变分片索引和去重规则 | 准备脱敏边界样本和去重测试 |
| Taskiq / 向量库 / 重型平台 | 8GB 本机资源不足，无独立压测数据 | POC 先过 |

### 下一阶段进入条件

1. CI 连续通过
2. 六类核心验收各至少完成一次真实数据记录
3. Outbox 与 ASR 边界样本测试先于数据库迁移
4. 任何目录搬迁保持 API 兼容并提供回滚
5. AI Prompt 变更必须能按版本对比效果

## 后果

- ✅ 方向明确：知道哪些东西"不做"比"做"更难
- ⚠️ 延迟项积压可能导致技术债务，需要定期回顾
- ⚠️ 服务间通过裸 dict 通信（当前），建议后续引入 Pydantic 模型
