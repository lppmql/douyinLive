# ADR 0044：本地 Ollama 与人工 AI 剪辑

- 日期：2026-08-27
- 状态：已采纳（用户确认方案 A）
- 取代：ADR 0038 的云端模型选择及 ADR 0042 的新终稿自动剪辑规则；其他剪辑与 ASR 契约保持不变。

## 背景与选择

用户要求用本地模型替代云端 AI 密钥，并删除 DeepSeek 相关设置。当前电脑为 Apple M1 Pro、10 核 CPU、32GB 内存，另有 FunASR、MySQL、Redis 等服务共用资源。

采纳方案 A：Ollama + 官方 `qwen3.5:9b`。不选机器上已有的社区 27B 修改模型，避免更大的内存占用和自定义模板风险；也不保留云端自动回退。

## 决策

1. 所有文本 AI 入口统一使用 `services/ai/llm_client.py`：对话、话术评分、统一复盘、高意向识别、趋势/异常、知识库问答、提示词测试及剪辑选段。ASR 继续使用 FunASR，向量检索继续使用现有本地 embedding，不混为同一种模型。
2. 删除旧客户端、`DEEPSEEK_*` 配置和本机密钥。OpenAI SDK 仅作为兼容协议客户端，固定的 `ollama-local` 是 SDK 占位值，不是真密钥。只允许本机 HTTP `/v1` 地址，忽略代理、禁止 HTTP 重定向，不回退云端。
3. 用 `deploy/ollama/Modelfile` 创建 `douyin-live-qwen`，上下文为 65536 Token；关闭思考输出，保留 JSON 契约、真实证据引用和程序侧校验。格式错误、空输出或输出截断明确失败，不补造结果。
4. 长请求超时默认 900 秒。脚本自启 Ollama 时限制一个加载模型、一个并行推理，并设置 `OLLAMA_NO_CLOUD=1`；若用户已启动 Ollama，则复用，不修改全局配置或停止其他应用的服务。
5. ASR 离线终稿不再自动排队剪辑；删除自动开关与自动排队模块。运营从“AI手动剪辑”页面主动发起，仍保留选段、成片、字幕、重剪和发布审核能力。
6. `start.sh` 检查配置的服务和模型，缺模型时明确提示初始化；不在日常启动时下载大模型。`make doctor` 与 `/health` 同步展示模型可用性。
7. 知识库流式链路使用异步 HTTP；响应结束时显式关闭上下游生成器，取消阶段保护必要的连接清理。浏览器断开不能继续占着本地模型等待首 Token。

## 数据和兼容

迁移 `f7a8b9c0d1e2` 只把 `ai_call_traces.provider` 新记录默认值改为 `ollama`。历史云端调用、历史复盘、话术、成片都保留真实来源，不改写为本地结果。历史 ADR 和 CHANGELOG 中的旧设置只作为历史记录，不是当前配置说明。

本机 `.env` 不进入 Git；删除本机密钥不会自动撤销供应商平台上已经签发的密钥。如需完全作废，由用户到原供应商控制台撤销。

## 启动和验收

```bash
# 首次：安装并打开 Ollama，然后在项目根目录执行
./scripts/setup_ollama_model.sh
# 日常：自动应用数据库迁移
./start.sh standard
# 提交前
make check
```

验收覆盖本地普通回答、JSON、流式输出、真实话术选段与真实互动复盘，检查新增追踪使用 `ollama`，ASR 不再创建剪辑任务。测试结果见 CHANGELOG；模型生成质量仍需人工复核，不承诺与云端模型完全等价或固定提速。

## 官方依据

- [Ollama OpenAI 兼容协议](https://docs.ollama.com/api/openai-compatibility)：流式、JSON、关闭思考及兼容客户端配置。
- [Ollama FAQ](https://docs.ollama.com/faq)：本机监听、并发和关闭云端功能。
- [官方 Qwen3.5 模型](https://ollama.com/library/qwen3.5)：所选 9B 模型。
