# 核心链路验收

这里记录项目关键能力的可重复验收方法。自动化测试可以使用脱敏固定样本，但业务验收必须选择数据库中已经采集到的真实账号、主播和直播场次，不允许为了"通过"而补写模拟数据。

## 文档导航

- [数据采集验收](collector-acceptance.md)
- [ASR 话术验收](asr-acceptance.md)
- [场次复盘验收](review-acceptance.md)
- [知识库验收](knowledge-acceptance.md)
- [主播排班验收](schedule-acceptance.md)
- [可观测性验收](observability-acceptance.md)

历史验收结论已归档至 [ADR 目录](../adr/) 和 [CHANGELOG.md](../../CHANGELOG.md)。

## 统一记录要求

每次验收至少记录日期、操作者、真实账号 ID、真实场次 ID、Git 提交、Trace ID、成功项、失败项和恢复结果。Cookie、Token、浏览器指纹、完整私信内容及 AI 密钥不得写入文档或截图。

常规自检入口：

```bash
make doctor
make test
make lint
make build
```
