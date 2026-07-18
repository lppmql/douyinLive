# 2026-07-18 DataEase 与监控恢复验收

## 问题结论

- DataEase 容器持续为 `healthy`，`InvocationTargetException` 发生在登录请求的 RSA 解密阶段。
- `core_rsa` 只有一条完整密钥记录；使用当前 `/de2api/dekey` 返回的公钥执行真实登录，HTTP 200、业务码 0，并返回登录令牌（令牌未落盘、未输出）。
- 浏览器缓存键 `DataEaseKey` 来自旧数据库公钥，和当前私钥不匹配时会触发 `BadPaddingException`。恢复动作是清除该站点缓存，不是删除 DataEase 数据库。
- Prometheus/Grafana 配置存在但旧版 `start.sh` 没有启动 `observability` profile，因此容器从未创建。

## 修复内容

- 一键启动默认拉起 Prometheus 和 Grafana，并分别等待 `/-/ready` 与 `/api/health`。
- 为两个监控容器增加 Docker healthcheck，Grafana 等待 Prometheus 健康后再启动。
- 监控组件安排在后端和 FunASR 之前启动，降低 8GB 电脑首次下载、解压镜像时的内存峰值。
- 增加 DataEase 公钥链路检查，验证 AES 包装、公钥格式和 RSA 2048 位要求，不打印任何密钥。
- 增加 DataEase 静态登录兼容层：先淘汰旧 `DataEaseKey`，再读取当前公钥并按官方 `web-storage-cache` 格式写回，最后加载官方 JAR 前端资源，避免旧页面与官方预取请求竞争。
- DataEase 冷启动等待上限由 240 秒调整为 600 秒；启动和 `make doctor` 都会校验兼容层标记，避免容器健康但修复页面未生效。
- `make doctor` 同时检查五个基础容器、三个 HTTP 健康接口，并识别近期 DataEase 旧公钥错误。
- 账号存活检查不再因实时监控开启而返回 409，而是和监控页面共用串行浏览器队列；刷新采集或扫码登录运行时仍保留冲突保护。

## 真实验收记录

- DataEase：容器 `healthy`，外部兼容首页由 Spring 正确加载；使用项目本机真实管理员账号从登录页进入工作台，未输出密码或令牌。
- Prometheus：`/-/ready` 返回 ready，`douyin-live-api` target 为 `up` 且无抓取错误。
- Grafana：`/api/health` 返回 `database: ok`，版本 12.4.0。
- FunASR：首次并发拉取 Grafana 镜像时曾因内存压力退出；按新顺序恢复后容器运行，且不再与镜像拉取并发。
- 账号存活：实时监控保持运行，账号 6 使用已保存 Cookie 与浏览器指纹检查成功，返回 `valid=true`、`logged_in`。
- 真实数据：1 个直播间、2,028 场直播、9,858 条评论、11,230 条话术片段、90 份 AI 分析报告；未写入模拟业务数据。
- 资源快照：MySQL 约 440MB、DataEase 约 622MB、FunASR 约 1.0GB、Prometheus 约 45MB、Grafana 约 114MB。
- 错误复核：16:13 首版按版本清理策略仍复现两次旧公钥请求，因而继续按官方缓存格式强化；16:31 独立浏览器真实登录成功，此后未再出现 `InvocationTargetException` 或 `BadPaddingException`。
- 登录旁路复核：独立浏览器首次加载发现一个 7 月 15 日已过期令牌，DataEase 正常退回登录页；该提示与 RSA 解密错误不同，新登录成功后未再影响工作台。
- Quartz 复核：冷启动时处理一次历史 misfire，随后 `qrtz_triggers=2`、`qrtz_job_details=2`、孤儿 trigger 为 0，无需删除调度数据。
- 数据安全：未删除或重建 MySQL/DataEase 数据，未输出 Cookie、指纹、私钥、密码和令牌。

## 重复验收命令

```bash
make doctor
curl http://localhost:8000/health
curl http://localhost:9090/-/ready
curl http://localhost:3000/api/health
curl http://localhost:9090/api/v1/targets
docker compose --profile dataease --profile observability ps
```
