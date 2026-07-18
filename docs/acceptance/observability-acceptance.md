# 可观测性验收

## 前置条件

- MySQL、Redis 和后端正在运行。
- 如需大盘，启动 `observability` profile 并设置独立 Grafana 密码。

## 操作步骤

1. 请求 `/health`，检查数据库、Redis、监控和配置状态。
2. 请求任一 API，确认响应头包含 `X-Trace-ID`。
3. 请求 `/metrics`，确认 HTTP、任务和运行时指标可读取。
4. 人为触发一个可恢复失败，确认采集日志、任务记录和结构化日志使用同一 Trace ID。
5. 运行 `make doctor`，核对依赖、容器、Playwright、健康接口、磁盘和弱配置提醒。

## 预期结果

- 错误可以通过 Trace ID 从前端追踪到任务和后端日志。
- 健康接口不返回 Cookie、Token、数据库密码或 Redis 密码。
- 配置错误会阻断启动，弱安全配置会显示明确代码和处理建议。
- Prometheus 和 Grafana 默认不启动，避免占用低配电脑资源。

## 失败与恢复

- `/health` degraded：分别检查 MySQL、Redis 和配置问题代码。
- Worker 无心跳：回收超时任务后只续跑可恢复部分。
- 磁盘不足 10GB：先清理回放缓存和无用日志，再启动长场次转写。
