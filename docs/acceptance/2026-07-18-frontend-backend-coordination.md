# 2026-07-18 前后端协调验收

## 核对范围

- 前端 `backendRequest` 的 API 路径、HTTP 方法、查询参数和响应类型。
- FastAPI OpenAPI 路由、REST 真实响应和 ASR WebSocket 消息。
- 一键启动中的 MySQL、Redis、FastAPI、前端、FunASR 与 DataEase 生命周期。
- 项目已保存 Cookie 和浏览器指纹的真实恢复结果。

## 已修复问题

1. 采集日志和任务筛选原先使用 `taskId/taskType`，后端实际要求 `task_id/task_type`，导致筛选条件被忽略。
2. 前端残留 3 个后端不存在且无人调用的模板接口，契约测试现会阻止此类 404 再次进入主分支。
3. 通用请求层残留固定 Apifox Token，现已移除，浏览器构建不再携带该值。
4. 话术页面 WebSocket 原先读取 Apifox 的默认服务地址，现统一读取真实后端地址；Vite 代理已开启 WebSocket 转发。
5. 后端原先为每个场次连接创建一个 Redis 订阅，多人或多场同时查看时可能重复广播；现改为单进程共享一个订阅。
6. 转写分段缺少前端已声明的 `session_id`，实时采集任务类型缺少 `live_detail`，现已前后端同步补齐。
7. `start.sh` 原先不等待 FastAPI 健康状态，后端退出后仍提示启动完成；现必须通过健康检查。
8. `start.sh` 原先没有启动 DataEase；现启动 `dataease` profile 并等待容器健康后才提示系统启动成功。

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 后端完整测试 | 108 passed |
| 前端 TypeScript | 通过 |
| 前端 Oxlint | 0 warning / 0 error |
| 前端 ESLint | 通过 |
| 前端生产构建 | 通过 |
| 前端 API 与 FastAPI OpenAPI 契约 | 通过，无缺失路径或方法 |
| Bash 启动脚本语法 | 通过 |

## 真实运行验收

- 后端 `/health` 返回 `status=ok`，MySQL 与 Redis 均为 `ok`。
- 项目保存的采集账号成功恢复，接口返回 `cookie_saved=true`、`fingerprint_saved=true`、`login_status=logged_in`。
- 实时监控正常运行，验收时识别到 2 个真实活跃场次 `13287`、`13288`，`last_error=null`。
- 后端直连 `ws://127.0.0.1:8000/ws/transcript/13288` 收到真实协议响应 `{"type":"pong"}`。
- 前端代理 `ws://127.0.0.1:9527/proxy-backend/ws/transcript/13288` 同样收到 `{"type":"pong"}`。
- 同时连接两个真实场次时，Redis `asr:transcript` 订阅数为 1，确认不会按场次重复订阅和重复广播。
- DataEase 容器状态为 `healthy`，`http://127.0.0.1:8100/` 返回 HTTP 200。
- DataEase 真实宽表状态：源场次 540 场、已同步 103 场、待同步 437 场、覆盖率 19.1%，未伪造完成率。
- DataEase 首次初始化约 162 秒，实测内存约 712MB，低于 1.2GB 容器上限。

## 说明

- 删除的 3 个前端函数没有任何页面调用且后端从未提供对应路由，不属于可用功能；真实 AI 评分、异常分析和报告接口保持不变。
- 本机现使用 `DEBUG=true` 兼容已有本地数据库密码，`.env` 被 Git 忽略，不会上传。模拟数据仍由 `ALLOW_SYNTHETIC_DATA=false` 保持关闭。
- 当前仍有本地安全提醒：MySQL 使用 root、Redis 未启用密码、DataEase 只读密码需要后续轮换；服务仅绑定 `127.0.0.1`，不应直接暴露公网。
