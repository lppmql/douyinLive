# ADR 0003: DataEase 公钥兼容与监控恢复

- **日期**: 2026-07-18
- **状态**: accepted
- **决策者**: 项目维护者

## 背景

DataEase 登录页出现 `InvocationTargetException`（底层 `BadPaddingException`），导致无法通过前端直接登录。同时 Prometheus/Grafana 未随 `start.sh` 默认启动，可观测性组件不可用。

## 决策

### DataEase 公钥兼容

**根因**：DataEase 数据库恢复或重建后，浏览器仍缓存旧的 `DataEaseKey` 公钥，与当前私钥不匹配。

**方案**：在 DataEase 登录首页增加公钥兼容层：
- 页面打开时先淘汰浏览器缓存的旧值
- 读取当前 `/de2api/dekey` 获取最新公钥
- 按 DataEase 官方 `web-storage-cache` 格式写入当前公钥后加载官方前端
- 避免官方预取请求与旧页面缓存竞争

### Prometheus/Grafana 默认启动

- `start.sh` 改为默认启动 Prometheus 和 Grafana（`--profile observability`）
- `make doctor` 同时检查容器状态和接口响应
- 资源限制：Prometheus 0.5 核/512MB、Grafana 0.5 核/512MB
- Grafana 密码必须通过 `.env` 的 `GRAFANA_ADMIN_PASSWORD` 设置

## 后果

- ✅ DataEase 登录页兼容浏览器旧缓存，无需手动清除
- ✅ Prometheus/Grafana 随一键启动自动运行
- ⚠️ DataEase 升级后需确认公钥兼容层是否仍有效
- ⚠️ 部署到非 localhost 域名时，必须同步修改 `VITE_DATAEASE_URL` 与 `dataease.origin-list`
