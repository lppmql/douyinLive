# 可观测性验收

## 前置条件

- MySQL、Redis 和后端正在运行。
- 使用 `./start.sh` 启动全栈，并设置独立 Grafana 密码。

## 操作步骤

1. 请求 `/health`，检查数据库、Redis、监控和配置状态。
2. 请求任一 API，确认响应头包含 `X-Trace-ID`。
3. 请求 `/metrics`，确认 HTTP、任务、AI 和运行时指标可读取。
4. 执行一次真实知识库问答，确认 `ai_call_traces` 记录 operation、Prompt 版本、Token 和耗时，但不存在输入输出原文字段。
5. 使用 `promtool check config` 验证 Prometheus 配置和 4 条告警规则。
6. 人为触发一个可恢复失败，确认采集日志、任务记录和结构化日志使用同一 Trace ID。
7. 运行 `make doctor`，核对依赖、容器、Playwright、健康接口、磁盘和弱配置提醒。

## 预期结果

- 错误可以通过 Trace ID 从前端追踪到任务和后端日志。
- 健康接口不返回 Cookie、Token、数据库密码或 Redis 密码。
- 配置错误会阻断启动，弱安全配置会显示明确代码和处理建议。
- Prometheus 和 Grafana 由一键启动默认拉起，且必须分别通过 readiness/health 检查后才报告启动完成。
- 首次拉取监控镜像发生在后端启动前，避免与 FunASR 模型加载争抢内存。
- AI 观测失败只产生告警，不改变原模型调用结果；JSON 解析失败计入失败调用。
- DataEase 仅从 `de_v_fact_ai_call_trace` 读取脱敏调用元数据，不接触 Prompt 和模型输出原文。

## 失败与恢复

- `/health` degraded：分别检查 MySQL、Redis 和配置问题代码。
- Worker 无心跳：回收超时任务后只续跑可恢复部分。
- 磁盘不足 10GB：先清理回放缓存和无用日志，再启动长场次转写。
- DataEase 出现 `InvocationTargetException` 且底层为 `BadPaddingException`：先运行 `make doctor` 验证当前 RSA 公钥；服务端正常时只清除 `localhost:8100` 的 `DataEaseKey`，不要重建数据库。
