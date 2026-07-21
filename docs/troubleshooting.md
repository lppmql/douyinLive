# 故障排查手册

> 常见问题的诊断步骤和解决方案。遇到问题时按「症状 → 诊断 → 解决」的顺序来，不要跳过诊断直接改。

## 快速诊断入口

遇到任何问题先跑：

```bash
make doctor                                    # 环境诊断
curl http://localhost:8000/health               # 后端健康
docker compose ps                               # 容器状态
tail -50 /opt/douyinLive/data/logs/app.log     # 最近日志（如果配置了文件日志）
```

---

## 后端

### 后端启动失败

**症状：** `./start.sh` 报错，或 8000 端口无响应

**诊断：**
```bash
# 检查端口占用
lsof -i :8000

# 检查 Python 环境
cd backend && source .venv/bin/activate && python -c "from app.main import app"

# 检查 .env 中的数据库密码
grep DB_PASSWORD ../.env
```

**常见原因：**
- MySQL 没启动：`docker compose up -d mysql`
- 数据库密码不对：检查 `.env` 的 `DB_PASSWORD` 是否与 docker-compose 一致
- Python 依赖缺失：`pip install -r requirements.txt`
- 端口被占用：`kill` 旧进程后重启

### API 返回 500

**症状：** 页面报 500，或 `/health` 不是 `status: ok`

**诊断：**
```bash
# 1. 看后端终端输出的 Trace ID
# 2. 用 Trace ID 在日志中定位
# 3. 检查数据库连接
docker compose exec mysql mysql -u root -p -e "SELECT 1"
```

**常见原因：**
- 数据库表不存在：执行 `alembic upgrade head`
- 数据库连接超时：重启 MySQL
- 外键约束：检查迁移是否按顺序执行

### API 返回数据与预期不符

**症状：** 前端显示的数据不对、缺失、或字段为 null

**诊断流程：**
1. 用浏览器 DevTools → Network → 找到对应 API 请求，看 Response
2. 对比 Swagger 文档 (`/docs`) 中的 response_model 定义
3. 如果 Swagger 与实际返回不一致 → Schema 与代码不同步，执行 `pnpm gen-api`

### 采集任务卡住

**症状：** 采集进度不动，日志不再更新

**诊断：**
```bash
# 查看 Redis 任务事件
docker compose exec redis redis-cli -a <密码> XRANGE douyin:task-events - + COUNT 20

# 查看采集日志
curl http://localhost:8000/api/v1/collector/logs?limit=50

# 检查 Playwright 浏览器进程
ps aux | grep chrom
```

**常见原因：**
- 浏览器崩溃：重启后端会自动重建浏览器上下文
- Cookie 过期：重新扫码登录
- 抖音限流：等待 10-30 分钟后重试

### ASR 转写不工作

**症状：** 话术一直显示"处理中"或不生成

**诊断：**
```bash
# FunASR 容器状态
docker ps | grep funasr

# FunASR 日志
docker logs douyin_live_funasr --tail 50

# 检查 WebSocket 连接
curl http://localhost:8000/api/v1/collector/asr-control
```

**常见原因：**
- FunASR 容器没启动：`docker compose --profile funasr up -d funasr`
- 模型下载失败：检查网络，手动删除 `data/funasr/models/` 后重启
- 内存不足：关闭其他容器释放内存
- 回放流过期：抖音回放有时效性

---

## 前端

### 页面白屏

**症状：** 访问 localhost:9527 显示空白

**诊断：**
```bash
# 浏览器控制台（F12）看报错
# 常见错误：
# - "Cannot read properties of undefined (reading 'map')" → API 数据结构不匹配
# - "Failed to fetch" → 后端没启动
# - "CORS error" → CORS 配置问题
```

**解决：**
1. `Cannot read properties of undefined` → 检查该 API 的 Swagger 文档与实际返回是否一致，执行 `pnpm gen-api` 重新生成类型
2. `Failed to fetch` → 启动后端
3. CORS → 检查 `.env` 的 `CORS_ORIGINS` 是否包含前端地址

### 前端构建失败

**症状：** `pnpm build` 报错

**诊断：**
```bash
pnpm typecheck    # 先检查类型
pnpm lint         # 再检查语法
```

**常见原因：**
- 后端 Schema 改了但前端类型没更新 → `pnpm gen-api`
- 引入了未安装的依赖 → `pnpm install`
- TypeScript 类型错误 → 根据报错修复

### 数据不更新

**症状：** 页面上数据是旧的，刷新后不变

**诊断：**
- F12 → Network → 看 API 请求是否发出
- 看 API 返回的数据是否真的是旧的
- 切换到其他页面再切回来

**常见原因：**
- KeepAlive 缓存：被缓存的页面切换后不会重新请求，手动点刷新按钮
- 浏览器缓存：Ctrl+Shift+R 强制刷新
- 后端没有新数据：检查采集是否在运行

---

## 数据库

### 迁移冲突

**症状：** `alembic upgrade head` 报错，提示多个分支

**诊断：**
```bash
cd backend && source .venv/bin/activate
alembic heads    # 查看所有分支头
alembic history  # 查看迁移历史
```

**解决：**
```bash
# 创建合并迁移
alembic merge <head1> <head2> -m "merge branches"
alembic upgrade head
```

### 迁移失败

**症状：** `alembic upgrade head` 报错

**诊断：**
```bash
alembic current    # 当前在哪个版本
alembic history    # 哪些版本待执行
```

**解决：**
1. 如果是表已存在 → 手动删除表后重试（开发环境）或跳过该迁移
2. 如果是外键冲突 → 先解决数据问题再迁移
3. 如果是 SQL 语法 → 手动修改迁移文件

**禁止：**
- 修改已合并到 main 的迁移文件
- 跳过迁移检查直接 `create_all()`

---

## Docker

### 容器无法启动

**症状：** `docker compose up -d` 报错

**诊断：**
```bash
docker compose ps -a     # 看所有容器状态
docker compose logs mysql --tail 30
```

**常见原因：**
- 端口冲突：其他程序占用了 3306/6379
- 磁盘空间不足：`df -h` 检查，清理 `docker system prune`
- 权限问题：确保 Docker Desktop 正在运行

### DataEase 无法访问

**症状：** localhost:8100 打不开

**诊断：**
```bash
docker ps | grep dataease
docker logs douyin_live_dataease --tail 30
curl -I http://localhost:8100/
```

**常见原因：**
- 首次启动需要 3-10 分钟初始化
- 内存不足：DataEase 需要至少 1.2GB
- RSA 公钥过期：参考 README 中的 DataEase 排错章节

### Prometheus/Grafana 没启动

```bash
docker compose --profile observability up -d prometheus grafana
curl http://localhost:9090/-/ready
curl http://localhost:3000/api/health
```

---

## 性能

### 电脑卡顿

**症状：** 运行项目时电脑风扇狂转、操作卡顿

**诊断：**
```bash
# 检查资源占用
docker stats --no-stream
top -o mem            # macOS
```

**解决：**
1. 在采集页面关闭 ASR（释放 FunASR 模型内存）
2. 停止实时监控
3. 关闭不需要的 Docker 容器：`docker stop douyin_live_dataease`
4. 检查是否有重复 Worker：`pgrep -af 'asr_worker'`（正常只有 0-1 个）

### 数据库慢查询

**症状：** 页面加载很慢

**诊断：**
```bash
# 查看慢查询
docker compose exec mysql mysql -u root -p -e "SHOW FULL PROCESSLIST"

# 查看表大小
docker compose exec mysql mysql -u root -p -e "
  SELECT table_name,
         ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
  FROM information_schema.tables
  WHERE table_schema = 'douyin_live'
  ORDER BY (data_length + index_length) DESC
  LIMIT 10"
```

**常见慢表：** `live_sessions`、`comments`、`transcripts`

---

## 日志定位

### 怎么用 Trace ID 定位问题

每个 HTTP 请求的响应头都有 `X-Trace-ID`。浏览器 F12 → Network → 找到报错的请求 → Response Headers → 复制 `X-Trace-ID`。

然后在后端日志中搜索这个 ID 就能看到完整请求链路。

### 结构化日志格式

```json
{
  "level": "ERROR",
  "event": "asr_task_failed",
  "task_id": 123,
  "session_id": 456,
  "error_code": "AUDIO_DOWNLOAD_FAILED",
  "trace_id": "abc-123",
  "attempt": 2
}
```

每条日志应该能回答：
- 哪个主播？（session_id → anchor_name）
- 哪一场？（session_id）
- 哪个任务？（task_id）
- 第几次重试？（attempt）
- 失败在哪个阶段？（event）
- 能不能重试？（error_code → retryable）

### 日志轮转

注意长直播可能产生大量日志。确认日志有大小限制和轮转策略，避免占满磁盘。

---

## 联系支持

如果以上步骤都无法解决问题，收集以下信息：

1. `make doctor` 输出
2. `docker compose ps` 输出
3. 后端最近的错误日志（带 Trace ID）
4. 浏览器控制台（F12）的报错截图
5. 出问题的具体操作步骤
