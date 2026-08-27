# CHANGELOG

本文件按时间倒序记录项目重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [2026-08-27]

### Changed
- 文本 AI 统一迁移为本地 Ollama + 官方 Qwen3.5 9B，项目模型 `douyin-live-qwen` 使用 64K 上下文；保留评分、复盘、问答、提示词测试、高意向识别和剪辑选段。
- 删除 DeepSeek 客户端、密钥/地址/模型配置；本地客户端忽略系统代理、拒绝重定向，不提供云端回退。
- AI 剪辑改为人工发起，移除离线终稿自动排队和自动开关；既有成片、字幕与重剪能力保留。
- 新增模型初始化、自检与健康状态；一键启动仅检查和启动本地服务，不自动下载大模型。
- 知识库 SSE 改为可取消的异步模型流，浏览器在首 Token 前断开、发送阻塞或发送失败时都会关闭上游连接。

### Migration
- 新增 `f7a8b9c0d1e2`，仅调整 AI 调用追踪的新记录默认供应商为 `ollama`，历史调用及业务数据保持不变。

### Verification
- 完整 `make check` 通过：458 项 pytest、前端类型检查、Ruff、Oxlint/ESLint、Vite 构建、Alembic 和 Docker 配置检查。审查发现的 SSE 取消问题修复后，补跑 22 项受影响测试及 Ruff，全部通过；未重复全量检查。
- 真实场次 #2494：JSON、流式输出和统一复盘成功，复盘分析 2 位用户，耗时约 74.88 秒。异步改造后真实流式再次通过，短问题在长上下文切换后耗时 56.48 秒，不能承诺秒回。
- 真实长场次 #2479：835 段抽样至 500 段，68198 输入字符、45321 输入 Token，选段耗时 390.89 秒，1 条返回方案通过真实行号和时长校验；未额外生成或发布视频。
- `make doctor` 0 失败，6 个提醒均为 standard 模式未启用的 DataEase/监控组件。浏览器验证登录、首页与“AI手动剪辑”入口正常，未发现页面错误遮罩。
- 最终恢复本地 AI、监控和 ASR，Worker 心跳正常；本次新增云端调用为 0。另观察到过期回放重试和 Naive UI 弹层事件错误，未纳入此次模型迁移修复，见 `docs/本地AI切换验收-2026-08-27.md`。

---

## [2026-08-26]

### Changed
- ASR 自动范围从“当天已下播”扩展为上海时区“昨天与今天已下播”，所有正在直播场次仍始终自动入队；前天及更早场次继续只支持人工转写。
- FunASR Docker 资源与解码、模型、IO 线程改为根 `.env` 可配置；当前 M1 Pro 32GB 本机采用 4 核、3GB、8/2/2 线程，业务层仍保持单模型连接与现有断点调度。
- 主播话术页的批量操作文案同步调整为“补排昨日与今日自动任务”。

### Verification
- 2026-08-26 14:52（上海时间）冻结部署前 14 天真实数据基线：离线终稿 2965 个分片、97.71 小时音频，加权 RTF 0.715、中位 RTF 0.200；实时初稿 563 个分片、18.76 小时音频，加权 RTF 1.208、中位 RTF 1.058。固定 UTC 窗口和筛选口径记录在 ADR 0043，部署后按相同口径复核吞吐、内存和完整度。
- 已安全重建并核验本机 FunASR 实际使用 4 核、3GB、8/2/2 线程。早期真实冒烟样本的 9 个离线分片加权 RTF 为 0.481、无完成分片重试；切换前 11111 个已完成断点全部保留。样本较小，不作为长期固定提速承诺；详细资源快照和 1 个下播后源站 404 分片记录在 ADR 0043。

---

## [2026-08-25]

### Changed
- ASR Worker 收敛为只生成实时初稿与离线终稿；AI 评分和复盘改为纯人工入口，生成复盘不再隐式创建剪辑任务。
- 自动剪辑只响应部署后新完成的离线终稿，并按场次幂等排队；不扫描或回填历史任务。
- 剪辑在 AI 选段前检查真实话术、真实回放、libass ffmpeg，以及缺少逐字时间戳时的 FunASR 可用性。

### Fixed
- 修复候选成片全部渲染失败时，外层剪辑任务仍被误记为完成的问题；局部失败和字幕精确对齐降级现在使用独立计数。
- 字幕对齐降级原因写入任务结果和成片质检数据，便于定位 FunASR、音频提取或时间戳问题。
- 采集与话术任务界面移除旧“自动 AI 复盘入库”状态，避免把兼容字段误当成真实队列。

### Migration
- 新增 Alembic `e6f7a8b9c0d1`，只将从未执行的历史 ASR 后处理积压安全标为 `skipped`，保留全部历史结果与失败记录。

---

## [2026-08-18]

### Added
- 主播话术页新增智能、最新和 FIFO 三种自动转写排序；所有排序都保留人工场次和直播场次硬优先级。
- 手动选择场次后进入人工独占转写，其他任务在两分钟分片边界保存断点并暂停，人工任务结束后自动恢复。
- 主播话术页和场次详情统一时间轴通过同一 WebSocket 即时显示已落库的直播话术。
- 话术分段复用版本化合规规则展示关键词命中、规则说明和改写建议，统一标为“涉嫌违规、待人工复核”。
- 主播话术任务中心新增真实排队位次、人工阻塞原因、安全停止、断点重试和取消人工优先操作；暂停任务与失败任务统一进入待处理视图。

### Changed
- 自动 ASR 范围调整为全部正在直播场次，以及 `Asia/Shanghai` 当天已下播场次；历史场次仅支持手动转写。
- “各主播增量转写”调整为“补排今日自动任务”，避免历史回放意外占用本机 FunASR。
- ASR 运行状态改为 FunASR 引擎、Worker 进程和独立心跳三重校验；僵死 Worker 会被自动替换，任务保留分片后断点续传。

### Fixed
- 修复 Worker 进程仍存在但事件循环已停止时页面误报正常、排队任务长期不推进的问题；页面现在展示明确异常并支持立即恢复。
- 修复失败任务重试被意外升级为人工独占，以及人工优先取消后其他场次无法立即恢复自动排序的问题。

### Migration
- 新增 Alembic `d5e6f7a8b9c0`，扩展 `asr_tasks.queue_source` 并新增 `asr_dispatch_policies`。

---

## [2026-08-17]

### Added
- 采集任务新增结构化错误码、失败阶段和可重试标识；登录过期后账号自动熔断，重新扫码后恢复。
- AI 复盘页新增全项目数据就绪漏斗，以及严格校验评论抖音号、主播与时间窗口的确认客资人工归属队列。
- 回放素材新增 14 天与 20GB 双阈值治理；因直播源可能过期，默认只告警，确认已有归档后才可显式开启自动清理。
- 新增 `setup.sh`，固定 Python 3.12、Node 22、pnpm 10.12.4；日常启动提供 `lite/standard/full` 三档。

### Changed
- MySQL 管理员、FastAPI 和 DataEase 使用三个独立账号；每次启动幂等校准最小权限。
- 完整复盘只调用统一 AI 复盘，场次详情与复盘页共享结果；低置信度结论统一标为待人工确认。
- 剪辑场次支持后端远程搜索与直达场次回显，生成按钮不再固定承诺 5 条结果。

### Fixed
- `segment_estimated` 估算字幕默认禁止确认发布，避免字幕不同步的成片被误标为可发布。
- 修复统一 AI 复盘已完成但完整度仍显示“AI报告 0%”的问题。
- Markdown 渲染异常回退路径现在先转义 HTML；Pydantic 对话 Schema 升级为 V2 配置。

### Migration
- 新增 Alembic `c4d5e6f7a8b9`，扩展 `scraper_tasks` 的失败诊断字段。

---

## [2026-08-08]

### Added
- AI 自动剪辑升级为多信号选段：把真实评论、高意向评论、互动指标增量、正式钩子、确认客资时间窗和话术评分组合成可解释分数；长直播采用“高信号优先 + 全场覆盖”，DeepSeek 仍只能引用真实话术行号。
- FunASR 转写开始保存纠错前原文、纠错后逐字/词时间和时间来源；历史场次仅对最终入选候选做二次离线对齐，避免整场重复转写。
- 成片同时输出 ASS/SRT、无字幕底片和基础质检结果；文件按 `clip_id/v版本` 保存，旧版本不覆盖。
- 剪辑审阅页新增字幕精度、渲染版本、评论/钩子/客资选段证据、逐段字幕校对、SRT 下载和“仅重制字幕”。

### Changed
- ffmpeg 管线从“每段直接烧字幕再拼接”调整为“画面切割拼接成 clean.mp4，再按成片局部时间轴一次烧录”，字幕修订无需重新下载回放或切割画面。
- 行业词纠错通过文本差异映射回原发音窗口；新字幕不再使用会累计超时的 0.8 秒强制下限，片段拼接处会删除原直播空档并保持语音停顿。
- “片段后 5 分钟客资”改为独立展示且始终附带非因果说明；没有正式钩子时不再用该时间邻近事实抬高选段分数。
- 整场重生成片把旧记录标为已丢弃而非删除，并按场次保留最近 10 条可安全清理的历史；字幕版本保留最近 20 个引用，超限文件在数据库提交后安全清理，未落库的失败渲染目录立即删除。

### Fixed
- 修复同场次已有任务时字幕编辑未入队却提示成功的问题；现在返回冲突并保留前端草稿。
- 候选二次 FunASR 对齐在 ffmpeg 提取及 FunASR 发送/等待期间定期检查取消；停止任务后中断当前处理，并把无视频草稿标记失败以便重新生成。
- 字幕重制任务记录目标版本，崩溃恢复不会把已完成 v2 重复渲染成 v3。
- 区分“FunASR token 时间对齐”和“行业词纠错重映射”，避免精度标签误导；根 `.env` 中的 `CLIP_FFMPEG_BIN` 现在由 Settings 正确读取。

### Security
- ASS/SRT 下载纳入只读媒体 Cookie 精确白名单；字幕重制写接口仍必须使用正常登录令牌，媒体 Cookie 不能调用。

### Migration
- 新增 Alembic `b3c4d5e6f7a8`，扩展 `transcript_segments` 和 `clip_clips` 的精确字幕、版本与证据字段。

---

## [2026-08-07]

### Added
- 新增一级菜单「AI自动剪辑」：AI 从整场直播话术中自动挑选主题片段，每场生成 5 条竖屏 9:16 短视频（30-90 秒，ASS 大字幕 + 封面），并自动生成抖音标题、发布文案和话题标签，一键复制人工发布。
- 选段采用"行号引用"契约（DeepSeek 只输出话术行号，程序映射回真实时间戳），实测消除推理模型偏移/编造时间戳的问题；单方案 1-3 段、总时长 30-90 秒、重叠拒绝，非法方案自动丢弃。
- 回放素材按需下载：从 `stream_sources` 流拷贝整场回放到 `data/videos/<session_id>/replay.mp4`（幂等复用），流地址过期时用已保存 Cookie 自动刷新后重试。
- 剪辑管线：ffmpeg 逐片段精确切割 + 竖屏转换 + 字幕烧录（一次重编码）→ concat 无损拼接 → 首帧封面；字幕烧录使用项目内 `.runtime/ffmpeg/ffmpeg`（evermeet.cx 静态版 9.0，含 libass），可用 `CLIP_FFMPEG_BIN` 覆盖。
- 新增 `clip_clips` 成片表与 13 个 `/api/v1/clip/*` 接口（任务列表/触发/重剪/确认/丢弃/视频/封面/字幕/统计/候选场次）；视频与封面纳入媒体 Cookie 白名单，浏览器原生 `<video>` 可直播放。
- 自动触发：离线终稿后处理链完成后自动排队剪辑（`CLIP_AUTO_GENERATE` 开关，默认开）；页面支持整场重新生成与单条重剪（可填选题方向）。
- 成片只生成内容不自动发布：确认后由运营复制标题/文案/话题人工发布到抖音，规避开放平台授权与风控成本。

### Fixed
- 修复成片页面视频无法播放（真正根因）：dev 模式 vite 代理只转发 `/proxy-default` 前缀（rewrite 后到后端），页面 axios 请求都带此前缀；但 video/img 标签用的裸 `/api` 路径在 vite dev server 上没有对应代理，返回 SPA 回退页（text/html），浏览器 video 无法解析导致黑屏。媒体地址改为按环境选择前缀——dev 用 `/proxy-default/api/...`，生产用同源 `/api`（nginx 已代理）；实测 9527 旧路径返回 text/html、新路径返回完整视频。
- 媒体 Cookie 的 `secure` 属性原为 `not DEBUG`，`DEBUG=false` 时通过 http 访问页面浏览器拒绝保存/发送该 Cookie，视频请求恒 401。改为 `secure` 跟随请求协议（https 生产仍安全标记，http 开发环境可正常种发），头像/回放等全部媒体链路一并受益；打开预览前自动续期 30 分钟媒体 Cookie，播放失败时给出明确提示。
- 修复剪辑页面场次下拉空白/信息不足：新增 `GET /api/v1/clip/candidate-sessions` 聚合候选场次（主播头像/抖音号、时间、话术转写完成度 x/y 段、已有成片数）；新接口不可用（后端未升级）时自动回退项目公共场次列表接口。
- 场次下拉渲染改用项目公共模式（与主播话术工作台一致）：`NSelect :render-label` + `AnchorIdentity` 公共组件（主播头像/昵称/抖音号）+ 右侧元信息，不再使用 `option.render`（naive-ui 回调签名是 `{ node, option, selected }`，原实现取错导致选项显示 `#undefined`）。
- 成片预览与卡片改为竖屏 9:16 比例展示（预览高度撑开居中、卡片封面 aspect-ratio 9/16），卡片网格改用 CSS Grid 大屏固定 5 列一排（1280/1024/720 断点自动降 4/3/2 列）。

### Verified
- 验收人：项目运营/开发者（2026-08-07，本机环境）。真实场次 #2130（81 分钟回放，3.7GB）全链路验收：AI 选段 5/5 通过校验（主题：开店预算、品牌避坑、下沉市场、一线vs二线、避坑指南），5 条成片全部渲染成功（1080x1920 H.264+AAC，每条 10-12MB，含字幕与封面），API 与文件服务 200。选段调用 Trace ID：`4db7e7de3a7b47678edd54fae38d9339`（success）。
- 失败项与恢复：选段调试期两次 DeepSeek 调用失败（`07b51803c1434f7a9d26bbfd49261a5a`、`e2304d5c91d74ada9260b2d664f8890f`，推理模型 max_tokens 不足导致输出为空），提高 max_tokens 并改为行号契约后恢复，未影响最终验收。
- 媒体链路复测：http 协议下 `getUserInfo` 返回的媒体 Cookie 不再带 `Secure`，用该 Cookie 播放成片视频返回 200（完整 11MB）；候选场次接口返回真实主播与话术统计；9527 dev server 实测 `/proxy-default` 前缀返回 `video/mp4`（裸 `/api` 返回 SPA 回退页）。
- 后端 385 项测试（新增 23 项剪辑测试）与 Ruff 检查通过；前端 typecheck、oxlint、eslint（0 错误）、Vite build 通过；`make doctor` 0 失败、`make check` 全绿。
- 新增 ADR 0038（直播回放 AI 自动剪辑架构决策），数据字典同步 clip_clips 表（36 业务表/55 对象）。

### Notes
- 每场自动任务消耗 1 次 DeepSeek 选段调用（5 方案一起出）+ 回放存储空间（每场约 1-4GB 在 `data/videos/`，已被 .gitignore 覆盖）；可在 `.env` 关闭 `CLIP_AUTO_GENERATE` 改手动触发。
- 依赖变更：需要带 libass 的 ffmpeg 做字幕烧录（系统 ffmpeg 8.1.2 无 libass，项目内静态版已就位）；换机器部署见 `docs/开发.md` 说明。
- 候选场次接口与前端回退逻辑兼容新旧后端；页面重启后端后下拉展示完整富信息。

---

## [2026-08-03]

### Fixed
- 修复实时初稿在直播收尾时被误判为失败的问题：最后一片遇到“直播音频缓存不完整”（下播后缓存停止增长）现在会平滑转交离线终稿补齐，不再把整场实时任务标记为失败。
- 修复离线终稿末尾分片反复失败的问题：ffmpeg 探测原来只验证回放开头（0 秒拉 3 秒），分片按起点定位时却可能落到回放真实时长之外读 0 帧。现在探测函数支持按分片起点验证并返回 ffmpeg 实测回放总时长；Worker 失败时先分类——分片起点超出回放真实时长则安全跳过，地址有效但 fast-seek 在 HLS 末尾定位越界则改用 slow-seek 精确定位兜底，最后才是刷新地址。

### Verified
- 使用真实失败场次 #352 完整修复验证：回放实测总时长 2883.61 秒（原采集值 2894 秒，已备份并修正为 2884），任务 #59 保留 24 个已完成分片，最后一片由 slow-seek 识别出 3.6 秒真实音频，245 条暂存话术全部公开为 246 条离线终稿，全文 15245 字；随后手动触发采集后处理，话术评分、9 条 AI 复盘发现、知识库与 DataEase 同步全部成功。
- 81 项 ASR 相关测试与 Ruff 检查通过。

### Known issues
- ASR Worker 的自动后处理轮询（`_poll_postprocess_tasks`）已实现但主循环未调用，导致离线终稿完成后的话术评分、AI 复盘、知识库同步不会自动执行（60+ 个历史任务处于 pending），目前只能靠页面手动触发。因涉及大量 DeepSeek API 调用成本，暂未修复，待评估后单独处理。

## [2026-08-02]

### Added
- 主播话术页新增场次工作台、初稿/终稿版本标识、业务话术分类、重复实时短片段折叠、可恢复失败原因和分片断点重试入口。
- 场次详情页与 AI 复盘页共用同一份用户互动链路分析，结合真实评论、附近主播话术、钩子和确认客资，输出精准新客、已开店、疑似已交钱/联系过拓展、非零食店、理性质疑、恶意用户、主播回应评分和错失机会。
- 统一 AI 复盘新增输入指纹缓存、过期标记、原文证据、有限重试和人工纠正；联系方式和抖音号不发送给模型。
- 客资口径改为同主播 60 秒内的“抖音号记录 + 手机/微信记录”稳定一对一配对；只有抖音号不再计为留资。
- 场次、DataEase、钩子时间窗和评论用户统计统一使用确认配对，并支持从原始客资幂等重建。
- 详情页和统一复盘时间轴在“已留资”下显示真实手机号或微信号，抖音号和联系方式支持点击复制。
- 新增评论用户公开资料分级补全：使用独立 Cookie 文件与固定请求指纹调用真实用户资料接口，按高意向和最近评论优先低速执行，并以 `sec_uid` 全局缓存头像、自定义抖音号和数字短号。
- 直播场次详情新增“补全本场用户资料”按钮、队列进度、头像与公开抖音号覆盖率；同一用户跨场次直接复用缓存。

### Changed
- 话术 AI 复盘只允许在离线终稿完成后执行；实时初稿继续用于观察和检索，不再显示误导性的 0% 完整度或 0 分 AI 评分。
- 话术正文按资料钩子、留资承接、互动引导、用户答疑和开店知识等真实关键词进行规则定位，并明确说明其不替代 AI 复盘结论。
- 统一“用户与转化”补齐评论用户头像、公开抖音号、已/未留资标识和可复制联系方式，并与一分钟客资配对事实保持一致。
- 删除详情页重复的旧“AI 分析”和“场次信息与话术完整度”，保留统一复盘、顶部可信度和回放下载入口。
- 评论用户公开资料在每次数据刷新成功后自动低速补全，并继续遵守缓存、退避和风控暂停；历史场次可用页面按钮显式重试。
- 客资用户匹配同时支持 `unique_id` 自定义抖音号和 `short_id` 数字短号完全一致匹配，页面明确展示匹配依据；昵称、`sec_uid` 和模糊值仍不参与确认。
- 评论用户资料专用 Cookie 保存到被 Git 忽略且权限为 `600` 的本地文件，不复用企业后台采集账号，也不写入日志、接口或数据库。

### Verified
- 使用真实场次 #2064 验证实时初稿持续增长、重复短片段折叠、关键词检索、失败任务抽屉、移动端和深色模式；页面控制台无错误或警告。
- 使用真实失败场次 #2063 验证企业后台回放地址重新提取、ffmpeg 拉流探测和新请求头生效；任务 #68 保留 3 个已完成分片并从第 4 片重试。平台回放随后持续返回 404，任务按真实结果明确失败，未伪造转写完成，失败候选也未覆盖旧 active。
- 使用最新真实场次完整补全18名评论用户，18/18成功、0失败；62条评论对应用户的头像与公开抖音号覆盖率均达到100%，并精确匹配4名本场已留资用户。

### Fixed
- 修复回放流监听注册过晚、`User-Agent` 多一层引号、旧 FLV 被误当成新回放，以及未经真实拉流验证就覆盖当前可用来源的问题；失败候选不再破坏旧 active。
- 修复长直播离线转写只在任务开始刷新一次地址的问题：404、TLS、无音频或读取中断时会刷新当前回放，并从失败分片继续，已完成分片不会重跑。
- 修复主播话术页混合统计实时初稿与离线终稿、跨时间窗口误删重复钩子，以及长直播只读取前 500 段的问题。

## [2026-08-01]

### Added
- 统一复盘时间轴新增“转化钩子”节点：覆盖后台、私信、领取资料、发资料、发消息、红色按钮等业务话术，并展示钩子强弱、缺失要素及后续 5/15/30 分钟评论和客资变化。
- 直播场次详情新增钩子转化摘要与时间轴、评论用户留资分析、主播同主题承接证据、未留资建议、身份字段覆盖率和全部场次指标展示。
- 新增 ADR 0035：《评论用户客资精确匹配与钩子时间窗归因》；用户级客资只允许公开抖音号精确匹配，钩子客资关系明确标注为时间窗关联。
- 新增可随 Git 分发的 DataEase 2.10.25 `application.yml`，并在一键启动时自动准备独立 `dataease` 数据库。
- 为根目录 `.env.example` 的每个变量补充中文用途、格式、单位和安全说明。
- 新增 ADR 0034：《跨机器一键部署与 CI 配置闭环》。

### Changed
- 移除详情页重复的独立钩子时间轴；资料内容只有同时出现领取或联系动作才计入正式钩子，单纯介绍资料标记为钩子铺垫。
- 评论采集兼容更多平台真实头像、公开抖音号及嵌套用户字段；平台未返回时保持为空，不再用稳定标识冒充公开抖音号。
- 采用适度精简的文档结构：核心 ADR 从 34 篇缩减为 16 篇，7 份验收说明合并为一份《项目验收手册》，移除失效的 Agent 教程和 SoybeanAdmin 上游模板文档；被移除内容仍可通过 Git 历史查看。
- 仓库统一只保留 `main` 分支，关闭 Dependabot 自动创建依赖升级分支；后续依赖升级在 `main` 上按需执行并完成对应检查。
- 按部署要求将生产数据库密码最低长度调整为 7 位、首次管理员密码最低长度调整为 6 位；`root123` 与 `admin123` 可用于首次部署，公网环境仍建议更换为随机强密码。
- 一键启动将 DataEase 与 FunASR 作为可降级服务；DataEase 配置缺失或启动失败时不再阻断前后端主系统。
- `.env.example` 保留用户指定的 `root123` / `admin123` 首次初始化值，并明确公网环境仍应主动更换强密码。
- CI 明确安装 `ruff`，Docker 配置检查使用 `.env.example` 生成临时环境文件，保证全新检出也能验证 Compose。
- Qdrant 集合初始化不再提前导入 `torch/transformers`，避免未使用向量模型时误报 Qdrant 不可用。

### Fixed
- 修复全新数据库已经扫码登录却因 `live_rooms` 为空而提前报错的问题：首次采集现在复用保存的 Cookie 与浏览器指纹，让企业后台自动选择最近有效直播间并保存真实 `room_id`，无需手工录入。
- 修复一键启动清理端口时误杀 Docker Desktop 进程的问题。
- 修复 DataEase 配置缺失时被 Docker 创建成同名目录、数据库未初始化以及只读账号配置失败的问题。
- 修复 macOS `ps` 输出包含非 UTF-8 字节时，ASR 控制中心接口和后端关闭流程抛出 `UnicodeDecodeError`。
- 修复新电脑首次管理员初始化密码与项目实际部署配置不一致的问题。

### Verified
- DataEase 登录 RSA 链路、HTTP 页面、MySQL 只读账号与 FunASR WebSocket 均曾使用真实本地服务验证通过；本次提交另以真实本地前后端完成管理员登录和首页验收。
- 使用已扫码账号真实验证根直播间自动发现成功，并同步发现 9 位主播、1045 场企业直播记录和 1001 场历史记录；详情补齐抽样 2 场成功后停止手工验收，剩余场次交由正常后台队列处理。
- 全新临时数据库从空库升级到 Alembic 最新版本后 `alembic check` 通过；320 项后端测试、前端类型检查、生产构建、代码规范与 Docker Compose 解析通过。

## [2026-07-30]

### Fixed
- **恢复并清洗 ASR 行业热词校准**：修复 FunASR 启动消息把 `hotwords` 写死为空字符串的问题，直播中初稿和下播后终稿都会加载 `docs/行业知识/` 中的真实品牌与业务术语；同时只解析明确的品牌分类，过滤 Markdown 分隔线、预算数字、面积单位、括号说明等噪声，避免错误热词降低识别准确率。
- **修复直播末尾转写失败**：实时任务在最后一片遇到下播 404、无音频或缓存结束时，保留已有初稿并平滑转交独立离线终稿，不再把整场标为失败。
- **修复长直播阻塞最新终稿**：单 FunASR 模型改为直播与最新下播终稿 3:1 分时，旧终稿在分片边界礼让最新场次。

### Added
- 新增 ASR 热词回归测试，覆盖核心词保留、文档噪声过滤，以及 `online`/`offline` 两种识别协议均携带热词。
- 新增 ADR 0032：《ASR 行业热词启用与知识文档噪声过滤》。
- 新增真实直播 PCM 连续缓存，默认保留 24 小时、总量不超过 2GB，避免终稿占用模型时漏掉直播声音。
- 新增话术时间轴完整度检测、缺失区间最多 3 轮自动续接，以及直播详情页“主播语速（字/分钟）”和终稿/初稿来源标识。
- 新增 ADR 0033：《ASR 连续缓存、分时调度与完整度治理》。
- 同步最新 OpenAPI 前端生成类型，并补齐此前漏生成的会话与客资接口契约。

### Changed
- 在线初稿以约 1.2 倍速追赶音频缓存，并缩短无意义的结果收尾等待；离线终稿继续使用完整精修等待。

---

## [2026-07-29]

### Changed
- **轻量文档治理**：补齐新手上手指南入口，新增 ADR 总索引，修正 `.env.example` 章节编号，移除开发指南里容易过期的文件数量，并在验收说明里增加“改动类型 → 必跑验收”映射，方便后期维护和开发。
- **分支策略改为 main 直接开发**：取消日常临时分支开发流程，后续开发、修复和文档维护都直接在 `main` 完成；提交前仍保留测试 Agent、代码审查 Agent 和 `git status` 检查，避免半成品进入主线。

### Fixed
- **修复 ASR 失败任务原因不清楚**：安装缺失的 Playwright Chromium，恢复流地址自动刷新能力；并把 ffmpeg 的 404/403 等真实取流错误写入分片失败原因，直播话术页任务抽屉能直接看到是流地址失效、刷新失败还是无音频帧。
- **修复知识库对话历史类型检查和历史消息显示**：对话历史接口统一通过 `unwrapServiceData` 解开请求响应，历史 AI 消息从后端 `assistant` 映射为前端 `ai`，并回填 AI 消息的后端 ID，保证 `pnpm typecheck` 通过、历史回答能按 AI 气泡展示，赞/踩反馈能同步到后端；新对话不再重复保存第一条用户问题。

### Added
- 新增 ADR 0031：《ASR 流地址刷新依赖与失败原因透传》。
- 新增 `docs/README.md` 作为文档总入口，统一指向新手、规则、开发、部署、ADR 和代码治理文档。
- 新增 `docs/代码治理清单.md`，记录后续代码整理优先级，避免一次性大重构。
- 新增 ADR 0030：《轻量文档治理与维护入口修复》（由重复编号 0027 修正）。
- 新增 ADR 0028：《知识库对话历史响应解包与角色映射修复》。
- 新增 ADR 0029：《main 直接开发流程》。

---

## [2026-07-28]

### Added
- **知识库 Chat UI 全面升级（方案 C）**：对标 ChatGPT 体验，包含以下改进：
  - **对话历史持久化**：新建 `conversations` + `conversation_messages` 数据库表，对话不会刷新丢失
  - **对话历史侧边栏**：左侧可切换/新建/删除历史对话
  - **Markdown 渲染**：AI 回答支持加粗、列表、代码块、链接（引入 `markdown-it`）
  - **打字光标动效**：流式输出末尾闪烁 `▍`，像 ChatGPT 一样
  - **停止生成按钮**：流式输出中可随时点击停止
  - **赞/踩反馈**：每条 AI 回答底部 👍👎，帮助你评价回答质量
  - **来源迷你卡**：AI 消息底部直接显示引用来源，不用去右侧面板也能看到
  - **品牌色用户气泡**：从微信绿 `#95ec69` 改为品牌主色白字
  - **CSS 变量化**：全面支持深色模式，跟随系统自动切换
  - **欢迎页升级**：渐变头像装饰 + 功能说明卡片 + 带图标推荐问题
  - **消息入场动效**：每条消息依次淡入，过渡自然
  - **清空确认弹窗**：点「新对话」前需确认，防止误删
  - **无障碍优化**：全量 `aria-label` 标签
- 新增 `markdown-it` 依赖（约 30KB），AI 回答 Markdown 转 HTML
- 新增 6 个后端 API：对话列表/创建/详情/删除/追加消息/反馈
- 新增 ADR 0027：《知识库 Chat UI 全面升级方案 C》

### Changed
- 知识库页面布局从双栏 → 三栏（侧边栏 + 聊天 + 来源）
- `ChatPanel.vue` 重写（约 400 行），移除微信绿色调

### Fixed
- **对话侧边栏高度自适应**：NSpin 组件的两层内部容器（`.n-spin-container`、`.n-spin-content`）阻断了高度传递链，导致 NScrollbar 只有内容高度（134px）而非容器高度（614px），多对话时滚动条不出现。修复方式：用 `:deep()` 穿透样式，逐层设置 `height: 100%`
- `useKnowledgeChat.ts` 集成对话持久化和反馈功能

## [2026-07-27]

### Changed
- **客资归属升级为四级匹配**：新增第 4 级「当天无直播，按主播不限日期就近匹配」，备注「当天无直播记录 / 换号播的」。之前 299 条待归属中 124 条被第 4 级匹配成功，剩余 175 条为真正找不到任何直播记录的新主播/换号。

### Security
- **业务权限改为三档角色并默认拒绝**：查看者只能读、操作员可以写但不能删除或管理用户、超级管理员拥有完整权限；历史 `R_ADMIN` 自动兼容。
- **媒体与内部刷新接口不再匿名开放**：视频流、回放和 WebSocket 必须登录；ASR Worker 使用独立内部令牌刷新流地址。
- **删除新数据库默认弱口令**：仅在用户表为空时，才允许通过根目录 `.env` 中至少 15 位的初始化密码创建首个超级管理员。
- **短信验证码安全加固**：使用安全随机数、HMAC 摘要、Redis 原子消费和 IP/手机号/账号多层限流，接口和日志不再泄露验证码。

### Added
- **安全版客资服务部署包**：新增 `deploy/kezi-service/`，保留 `/api/kezi`、`/api/douyinhao`、`/api/stats`，增加读写分离令牌、限流、输入校验和隐私日志保护。现网服务完成鉴权升级前不读取真实客资。
- **客资后台增量同步闭环**：后端每 60 秒从 `kezi.lpp6.com` 按源编号继续拉取，使用“来源 + 源编号”去重，并按真实主播和直播时间窗自动归属；证据不足的客资保留为“待归属”，不猜测场次。
- **客资同步模块卡片**：原“抖音站内私信客资”统一命名为“客资同步”，并嵌入数据处理控制中心，固定排在 DataEase 数据库同步后面；继续展示配置状态、累计同步、待归属、重复跳过和同步游标，密钥始终只保存在后端。
- **直播中初稿 + 下播后终稿双通道**：正在直播使用 FunASR `online` 协议持续产生临时话术，下播后新建独立 `offline` 任务生成最终稿；最终稿完整入库后才原子替换临时稿。
- 新增 ADR 0023：《安全基础与话术转写可靠性加固》。
- 新增 ADR 0024：《直播双通道转写与客资增量同步》。
- 新增 ADR 0025：《客资同步卡片与源编号契约》。

### Deployment
- **客资密钥必须同步配置三处**：服务器 `API_KEY`（只读）与主项目 `KEZI_API_KEY` 保持一致；服务器另设不同的 `WRITE_API_KEY`，真实写入方请求 `/api/kezi` 时必须放进 `x-api-key`。写入方未同步更新会返回 401，不能只部署服务端。

### Fixed
- **修复话术转写协议用错**：旧实现无论直播状态都发送 `offline`，并用仅离线启动脚本加载了实时标点模型，导致直播初稿无法产生且 FunASR 反复退出；现改为官方双通道服务并按任务类型发送不同协议。
- **修复下播终稿无法创建**：实时任务完成后不再阻止同一场次创建独立离线任务，实时与离线任务使用不同幂等键和队列判定。
- **修复新客资服务漏掉”只有手机号”的记录**：`/Users/lpp/kezi` 的增量查询现在返回手机号或抖音号任一存在的真实留资，并为每条数据提供 `sourceId`，主系统可以安全去重并推进游标。
- **修复客资全部”待归属”问题**：kezi 客资服务保存的主播名是短名/昵称（如”丹丹”），但直播场次记录的是抖音完整标题（如”丹姐谈零食店天准”），精确匹配导致 1592 条全部无法自动归属。改为两级模糊匹配（精确+包含 → 首字兜底），时间窗加缓冲（前30分/后60分），1252 条成功自动归属到 106 场直播。
- 新增 ADR 0026：《客资自动归属两级匹配》。
- **修复 Pydantic 校验拦截脏手机号导致整页同步失败**：远程客资中存在用户误填的拼接号码（超过 20 字符），Pydantic `max_length=20` 校验失败后整页 100 条数据全部丢弃。修复：`KeziLeadItem.phone` 放宽到 100 字符，数据库 `leads.lead_phone` 同步放宽，脏数据先入库不丢。本次修复后首次同步成功导入 1592 条真实客资。
- **修复客资服务隐私与密钥风险**：移除源码默认密钥和数据库弱默认密码，读取与写入使用两条不同的至少 32 位密钥；比较密钥使用固定时间算法，写入日志与响应不再回显个人信息。
- **修复离线终稿半成品混入页面**：离线分段先作为不可见断点暂存，完整成功后再与全文、任务状态一起原子公开；失败任务清理只删除自己的分片，不再误删同场直播初稿。
- **修复 AI 复盘误用直播初稿**：实时任务不再进入评分和知识库后处理；离线终稿完成后强制重算已有话术评分，最终业务结果以终稿为准。
- **修复话术转写进度不显示的 Bug**：后端 `TranscriptTaskOut` Pydantic schema 缺少 `total_chunks`/`completed_chunks`/`progress_percent` 字段，FastAPI 序列化时把进度数据丢弃了，导致前端进度条一直不出现。已在 schema 中补上这三个字段。
- **修复实时话术转写无限占用**：直播中的音频改为每 2 分钟一个有限窗口，完成后继续下一个窗口；分片处理中每 30 秒更新心跳，并增加硬超时。
- **修复历史离线任务堵住实时直播**：离线回放在每个 2 分钟分片边界和 FunASR 模型等待点检查实时队列，有新直播时自动保存断点并礼让，且不消耗失败重试次数。
- **修复单并发下实时任务无法进入等待队列**：即使离线任务已经占满容量，也会为当前直播保留一个排队位置，让分片边界礼让机制真正闭环。
- **修复空音频被误判为转写完成**：ffmpeg 没有输出任何 PCM 音频帧时立即重试当前分片，不再把几十个空分片全部标记成完成。
- **修复 FunASR 断线误报完成**：WebSocket 中途断开会让当前分片失败并从断点重试；任务领取和模型连接均固定单并发，避免离线、实时任务争抢锁或 C++ 服务被第二条连接冲垮。
- **修复 FunASR 重启恢复时间不足**：Worker 和一键启动脚本统一读取 15 分钟模型加载等待时间，适配 8GB 电脑重新加载 1.6GB 模型的真实耗时。
- **修复历史分片超过真实直播时长或升级后重叠**：时长修正后重新核对旧分片，完整保留已有 300 秒真实话术边界，只从最远结束点按新 120 秒规则续建；自动跳过没有内容且超出结束时间的分片。
- **修复 Worker 重启误耗尽重试次数**：基础设施中断会退回待处理状态，不再消耗正常业务重试额度。
- **修复安全审查发现的权限缺口**：查看者不能调用写入型流刷新接口；旧版 `R_ADMIN` 在后端用户管理、前端路由和删除按钮中继续按超级管理员兼容；全新空库缺少安全初始化密码时服务直接停止启动。

### Verified
- 真实直播流任务 `#354` 已按 `online` 协议产生连贯句段；双通道 FunASR 容器运行期间重启次数为 0，未发生内存溢出。
- 客资数据库迁移已在真实 MySQL 升级到 `c9d0e1f2a3b4 (head)`；本地契约测试验证源编号、增量游标、去重、精确场次匹配与待归属逻辑。
- 后端 297 项测试通过，覆盖率 52.34%；前端类型检查、代码检查和生产构建通过。
- 使用项目保存的真实 Cookie、StorageState 和浏览器指纹恢复采集；真实任务确认采用 120 秒分片且心跳持续更新。
- 真实域名 `kezi.lpp6.com` 的鉴权已通过，但线上 `/api/douyinhao` 返回项仍缺少增量去重必需的 `sourceId`；主系统已拒绝推进游标，需重新部署本次修正后的 `/Users/lpp/Documents/kezi-main`。
- 匿名流刷新和媒体回放均返回 401；最终运行态实时任务 `#331` 已连续完成 3 个 120 秒分片，第 4 个分片处理中，且同时只有 1 个 ASR 任务处于 processing。
- 历史任务 `#323` 最终保留 45 个已完成分片并安全跳过 14 个越界空分片，已有话术未被删除。

---

## [2026-07-25]

### Added
- **话术转写进度显示**：在状态卡片和任务抽屉里都能看到转写进度
  - 「正在转写」状态卡片显示最快进度百分比（如「最快进度 45%」）
  - 任务抽屉里处理中的任务显示进度条（含分片进度：已完成/总分数 + 百分比）
  - 后端批量查询音频分片进度，一次 SQL 查所有任务，不拖慢接口
  - 已有 5 秒轮询机制，进度自动刷新，无需手动操作
- 新增 ADR 0022：《话术转写进度显示》
- **m3u8 流地址自动刷新**：流地址过期时自动用已保存的 Cookie 重新从抖音大屏页面抓取新 m3u8，无需人工重新采集
  - **流地址健康探测**（`stream_health.py`）：ffmpeg 快速拉流 2-3 秒检测是否有效 + 从 URL 解析抖音自带过期时间戳做预警
  - **自动刷新服务**（`stream_refresh.py`）：Cookie → 打开大屏页面 → 抓取新 m3u8 → 更新 StreamSource + LiveSession
  - **ASR Worker 转写前自动刷新**：转写前先探测 m3u8，过期则自动调 API 刷新，成功用新 URL 继续
  - **前端播放器自动恢复**：播放失败时自动调用刷新 API，成功后自动重播，用户无感
  - **刷新 API 免认证**：放在 `stream_router`（和视频流端点一样），ASR Worker 独立进程无需 JWT Token 即可调用
- 新增 ADR 0019：《m3u8 流地址自动刷新》

### Added
- **一键启动自动安装依赖**：`start.sh` 启动时自动检查 Python/Node/FFmpeg/pnpm 是否安装，缺的通过 Homebrew 自动装，Docker 未安装则给出下载指引
- **Qdrant 向量数据库随系统启动**：`start.sh` 第 1 步同时拉起 Qdrant 容器，启动后等待健康检查通过
- **FunASR 语音转写随系统启动**：`start.sh` 第 5 步用 `--profile funasr` 拉起 FunASR 容器，等待 WebSocket 端口就绪（首次自动下载模型，最多等 5 分钟）
- **行业知识集成（MySQL + Qdrant 双存储）**：`docs/行业知识/` 下的品牌红黑榜和区域分布文档自动导入知识库，启动时幂等导入，AI 问答可引用
- **ASR 智能纠错（双通道）**：
  - 第 1 层：从行业知识自动提取 145 个品牌名/术语热词，注入 FunASR hotwords 参数，提高语音识别准确率
  - 第 2 层：后处理纠错器，用编辑距离模糊匹配（141 个品牌名词典），自动校正 ASR 识别错的品牌名（如「好想赖」→「好想来」）
- 新增 ADR 0017：《一键启动全服务覆盖与环境自动安装》

### Fixed
- **主播话术页手动转写不自动启动 Worker**：采集页关 ASR 后去话术页点"开始转写"，任务写入数据库但 Worker 没跑，一直卡在 queued。现在手动排队时自动拉起 ASR 运行时（已运行则幂等跳过）
- **ASR 转写频繁失败（FunASR 容器修复）**：三个排查
  - **pgrep 模式修正**：`pgrep -f` 会匹配 bash 命令行自身，导致 FunASR 崩溃后监控循环检测不到。改为 `pgrep funasr-wss-server`（只匹配进程名）
  - **显式 decoder 线程数**：Docker for Mac 的 /proc/cpuinfo 显示宿主机 8 核，run_server.sh 自动检测错误。显式设置 `--decoder-thread-num 4 --io-thread-num 1`
  - **FunASR C++ segfault**：服务在收到异常连接后可能崩溃，靠 Docker `restart: unless-stopped` + pgrep 修复自动恢复
- **话术转写一直失败**：根因是 FunASR Docker 容器从未被启动（`profiles: [funasr]` 需显式 `--profile` 才能拉起），`start.sh` 原来只有占位符没有实际启动命令
- **Qdrant 健康检查 404**：`start.sh` 里 Qdrant 健康检查 URL 从 `/health` 改为 `/healthz`（Qdrant v1.13.5 实际端点）
- **话术转写任务抽屉新增清空失败任务功能**：筛选到「失败」tab 时显示红色「清空全部失败任务」按钮，每条失败/已取消任务右侧也有删除按钮。删除前弹确认框防误操作，删除时自动清理关联的音频分片和话术分段
- 新增 ADR 0020：《ASR 转写失败修复——FunASR 自动恢复 + 流刷新优化》

---

## [2026-07-24]

### Added
- **知识库问答支持流式输出（打字机效果）**：
  - 后端新增 `/api/v1/ai/qa/stream` 流式端点（SSE），逐 token 推送 AI 回答
  - kb_service.py 重构：提取 `_prepare_qa_context()` 公共检索逻辑，新增 `qa_search_stream()` 生成器
  - 前端用 `fetch + ReadableStream` 消费 SSE 流，替代原来的一次性等待
  - 修复 Vue 响应式 Bug：通过 `messages.value.find()` 获取代理引用，确保 token 追加能被 Vue 追踪
- **知识库问答 UI 优化**：
  - 流式打字过程中不再自动滚动，用户可自由阅读已输出内容
  - 用户消息气泡下方显示发送时间戳
  - AI 检索阶段显示「正在查找知识库…」替代骨架屏
  - 重新设计 4 个推荐问题，覆盖留资诊断、内容选题、评论转化、开场承接
  - 系统提示词禁止 Markdown 格式输出，AI 回答使用纯文本
- **知识库来源卡片点击跳转直播回放**：点击带场次来源的卡片直接跳转到对应场次详情页，自动从引用时间轴开始播放视频
- 新增 ADR 0016：《知识库问答流式输出与 UI 布局方案》

### Fixed
- **视频回放彻底修复——再也不报格式错误了**：
  - 直播场次详情页的视频播放从 EasyPlayer.js（npm 包损坏，无法使用）换成 mpegts.js，通过浏览器原生 MediaSource 解码 H.264 TS 流
  - 修复 JWT 鉴权导致 `MEDIA_ELEMENT_ERROR: Format error`：视频流端点单独部署在不需登录的公开路由上
  - 后端用 macOS 自带的 VideoToolbox 硬件加速把抖音的 H.265 流转成 H.264，首帧 2-5 秒就出画面
  - 播放进度条支持拖拽跳转（seek），复盘发现标记点照常显示
  - 补充了短信验证码登录缺失的类型定义

### Added
- 新增 ADR 0015：《浏览器视频播放方案选择——mpegts.js + H.264 TS》

### Changed
- 视频流编码器检测改为复用已有缓存函数，不再每次请求都跑子进程
- 清理了废弃的 `@easydarwin/easyplayer` npm 依赖
- **播放器底部状态栏精简**：移除「9:16 · H.264 TS」编码标签和直播标题文字，控制栏更简洁

---

## [2026-07-23]

### Changed
- **数据采集控制中心按最终业务流程收敛**：
  - “全部场次数据补齐刷新”改为高优先级手动按钮，默认刷新全部真实主播和全部场次，不再限制 20 场。
  - 直播监控和 ASR 话术转写保留为长期运行开关；关闭后停止对应后台工作并释放资源。
  - 知识库与 DataEase 改为有新数据就自动增量同步，不再向用户暴露容易误关的开关。
  - AI 复盘改为在直播场次详情页手动生成，不再由采集页自动触发。
  - 删除采集页共用进度条和页面头部，任务状态统一由任务队列、资源卡片和结构化日志反馈。
- **刷新优先复用同一登录态**：刷新开始后接管共享 Playwright 浏览器租约，监控在安全检查点等待；刷新结束后监控自动恢复，避免两个任务争抢 Cookie、浏览器指纹和页面句柄。
- **ASR 根据电脑资源实时调控**：优先处理正在开播的直播间，没有开播时从最新场次开始；根据 CPU、内存和核心数动态调整并发，高内存压力时在分片边界暂停，资源恢复后继续。
- **场次工作流双向联动**：直播场次详情、主播话术、AI 复盘和知识库页面共享当前 `sessionId`，可在同一场次上下文中互相跳转。
- **统一主播身份展示**：主播头像、昵称和抖音号由共享组件统一渲染，直播场次列表中的真实主播资料可复用于采集、话术、复盘、知识库和详情页面。

### Added
- **电脑资源概览**：采集页展示实时 CPU、内存、资源压力、ASR 目标并发和运行说明。
- **账号资产管理**：账号列表展示真实扫码昵称、抖音号、Cookie 状态、扫码时间、刷新时间和检查时间，并支持真实 Cookie 存活检查与二次确认删除。
- **结构化采集日志**：日志关联主播、场次、房间、任务、阶段和 Trace ID；数据详情使用中文字段展示，不再要求用户阅读原始 JSON。
- **评论用户资料字段**：评论保存真实昵称，并为平台后续返回头像或公开抖音号预留字段；当前企业评论接口未返回的字段明确显示“未获取”，不使用 `secUId` 冒充公开抖音号。
- **AI Prompt 统一目录**：新增后端 `app/prompts/`，集中管理复盘、评分、知识问答、高意向识别等提示词模板和版本。
- **孤儿任务恢复**：调度器自动识别并回收由旧后端进程遗留的监控运行任务，避免页面长期显示无法停止的“运行中”。
- **启动互斥锁**：一键启动脚本使用 `.runtime/start.lock` 防止重复启动；正常重启先等待业务进程最多 60 秒安全退出，避免强制关闭正在采集的 BrowserContext。
- **安全停机编排**：后端与前端使用独立进程组，终端 `Ctrl+C` 只交给启动脚本统一处理；停机先暂停新任务，再等待当前控制任务和实时采集完成，最后关闭 Playwright、Vite 和端口。

### Fixed
- **主播头像不显示**：后端仪表盘按 `douyin_id` 子查询聚合统计数据，再 JOIN 最新场次获取头像 URL，避免 `GROUP BY anchor_avatar_url` 把同一主播拆成多行导致头像丢失。前端 `AnchorIdentity` 组件改为有 `sessionId` 时始终走后端代理，即使原始头像 URL 为空也先尝试通过代理获取。
- **控制中心卡片高度不齐**：6 个模块卡片改为 3 列 × 2 排布局，CSS 统一加 `height: 100%` + `display: flex; flex-direction: column`，利用 Grid 的 `align-items: stretch` 实现同一行卡片高度一致。4 个电脑资源统计卡片同时统一高度。
- 修复刷新与直播监控并发时可能出现的 `BrowserContext.new_page: Target page, context or browser has been closed`。
- 修复删除采集账号返回 500、账号身份字段缺失、任务停止与重试反馈不完整等问题。
- 修复直播场次详情评论归属和评论用户信息契约，避免跨场次显示评论。
- 修复受统一鉴权保护后原生头像、回放和下载请求无法携带 Bearer Token 的问题；改用短时 HttpOnly 媒体 Cookie，且该 Cookie 不能访问普通业务 API。
- 修复监控页面关闭时未回收响应解析任务产生的 Playwright Future 异常噪声。
- 修复用户管理抽屉直接修改组件属性导致的前端检查错误，并更新 Playwright 冒烟测试到实际端口和 SoybeanAdmin 登录存储格式。

### Verified
- 使用已保存的真实 Cookie 和浏览器指纹完成账号检查，账号昵称为“大全谈开店天准”，Cookie 有效。
- 稳定完成真实补齐刷新任务 `#7443`：企业账号记录 10 个、发现 1032 场、新增 1 场、补齐 1 场、失败 0 场；整次任务只执行一次且没有浏览器关闭错误。
- 企业评论接口真实返回昵称、`secUId` 和平台内部用户 ID，但不返回头像或公开抖音号；系统按真实能力展示，不伪造资料。
- 实时监控识别到正在开播场次 `#13370`，安全停机前完成 12 条分钟趋势、9 条新增评论和 36 条画像写入，没有中断本轮真实数据。
- 后端 233 项测试通过，覆盖率 52.24%；前端 ESLint、Oxlint、类型检查和生产构建通过；真实前后端 Playwright 冒烟测试 10 项通过。

---

## [2026-07-22]

### Security
- **P0-01：所有业务 API 统一登录鉴权**（影响 16 个子路由）：
  - `v1_router` 新增全局 `dependencies=[Depends(get_current_user)]`
  - auth 路由单独注册（login/refreshToken 保持公开）
  - 之前采集、复盘、场次、话术、知识库等接口无需登录即可访问
- **P0-06：保护最后一个超级管理员**：
  - 不能删除/降级最后一个 R_SUPER 管理员

### Fixed
- **数据采集稳定性与反馈修复**：
  - 监控和全量刷新不再通过关闭浏览器互相打断，浏览器操作改为安全排队
  - 修复首次启动任务时 MySQL 旧事务偶尔读不到新任务详情的问题
  - Cookie 存活检查成功后保存平台轮换的新 Cookie，不再只检查不更新
  - 日志统一移除 Cookie、Token、Authorization 和直播流地址等敏感信息
  - FunASR 改为离线低资源模式，固定单并发并支持安全暂停和断点续传
- **P0-02：修复 ReviewFindingOut Schema 字段错配**：
  - 补回 9 个缺失字段（finding_type、description、severity、evidence 系列等）
  - 删除 2 个不存在的字段（evidence_summary、recommendation）
  - `_row_dict` 增加 datetime→ISO 字符串转换
  - 修复后更新 finding 状态不会丢失证据数据
- **P0-03：修复 ComplianceRuleOut Schema 字段错配**：
  - title/description → name/guidance/pattern（和数据库模型一致）

### Added
- **数据采集六模块控制中心**：
  - 全部数据刷新、直播监控、ASR、AI 复盘、知识库、DataEase 改为六个独立开关
  - 新增一个持久任务队列，支持停止、重试、服务重启恢复、心跳和 Trace ID
  - 新增唯一共用进度条，展示主播数、场次数、检查数、补齐数、失败数和剩余数
  - 账号列表新增真实扫码昵称、抖音号、Cookie/指纹状态、扫码/刷新/检查时间
  - 日志新增主播、场次、房间、阶段和中文数据详情，详情不再显示代码格式 JSON
  - 新增数据库迁移 `3a7c1f9e2d44` 和 ADR 0012
- **P0-04：Review API 响应契约测试**（`test_review_contracts.py`，12 个测试）：
  - workbench / finding update / compliance rules 返回值 Schema 校验
  - 所有复盘端点未登录 → 401 验证
- **P0-05：Playwright 前端冒烟测试框架**：
  - 10 个核心页面基础检查（登录→每页标题+非白屏+控制台无致命错误）
  - `pnpm e2e` 命令，`make test-frontend-e2e` 入口

### Changed
- **采集后处理全部解耦**：全部数据刷新只负责真实采集，不再自动启动 ASR、AI 复盘、知识库或 DataEase；四类重任务进入同一个队列串行执行，直播监控和 ASR 可继续常驻运行。
- **数据采集页按 SoybeanAdmin 现有规范重排**：使用 `NCard`、`NGrid`、`NSwitch`、`NProgress`、`NDataTable`、`NDrawer` 和 `NModal`，保留统一间距、状态色、移动端布局和静默轮询。
- **采集页二轮瘦身**（`index.vue` 752→204 行，-73%）：
  - 新增 `useCollectorLogin` composable：扫码登录流程独立管理（发起→轮询→成功/失败→清理）
  - 新增 `useCollectorData` composable：所有状态+数据加载+监控/采集/ASR/DataEase/日志/账号操作
  - `CollectorLogTable` 内置 logColumns 列定义（不再从父组件传入），新增 `openDetail` 事件
  - `index.vue` 精简为纯编排器：只负责组合子组件+生命周期
- **用户管理页方案 A 重构**（`index.vue` 408→108 行，-74%）：
  - 新增 `useUserManagement` composable：表格配置+搜索+CRUD+表单验证规则
  - 新增 `UserDrawer` 子组件：创建/编辑从 NModal 改为 NDrawer（侧边滑出，体验更流畅）
  - 删除确认从 `dialog.warning()` 改为 `NPopconfirm`（内联确认，不用弹窗打断操作）
  - 表单验证从手动 if 检查改为 `NForm :rules` 声明式规则
- **知识库页方案 A 重构**（`index.vue` 718→43 行，-94%）：
  - 新增 `useKnowledgeChat` composable：聊天状态+发送问题+清空对话+复制文本
  - 新增 `ChatPanel` 子组件：手写 HTML 全部替换为 Naive UI（NButton/NInput/NAlert/NSkeleton）
  - 新增 `SourcePanel` 子组件：来源卡片用 NCard+NTag 统一风格
  - 新增 `knowledge-adapter`：来源类型中文映射（话术/评论/指标/知识）
  - 新增推荐问题列表（4 个预设问题，点击即发送）
  - 打字中状态从 CSS 手写动画改为 NSkeleton 骨架屏
- **后端无改动**，三个任务全是纯前端重构
- **P0-07：前端运行时稳定性加固**（Phase 1）：
  - **新增 ErrorBoundary 组件**：子组件渲染崩溃时显示友好降级 UI（重试/回首页），不再白屏
  - **增强全局错误处理**：`app.config.errorHandler` 和 `unhandledrejection` 现在会给用户 toast 提示
  - **路由守卫异常保护**：`beforeEach` 整体 try-catch，出错自动回首页
  - **修复冒烟测试默认密码**：`admin123456` → `Admin123456`（对齐数据库种子数据）
- **P1-01：Phase 2 数据完整性校验与参数验证加固**：
  - **前端安全取值工具**（`safeAccess.ts`）：新增 `safeGet`（防 undefined 链式崩溃）/ `ensureArray`（防 `.map()` 崩溃）/ `safeNumber`（后端返回 null 也不怕）
  - **响应拦截器加固**：`backendRequest` 的 `transform` 加 null 检查，后端返回空数据时输出警告而非静默崩溃
  - **复盘工作台安全性修复**：5 处 API 调用从手动 `.data` 改为 `unwrapServiceData` 统一解包
  - **API 参数边界校验**：5 个分页/limit 类 API 前端加范围裁剪（`current>=1`, `size 1~500`）
  - **后端 Schema 约束**：8 个 CRUD schema 共 ~50 个字段加 `min_length`/`max_length`/`gt`/`pattern` 约束
  - **统一错误响应格式**（`error_handler.py`）：3 类异常统一转 `{"code":"XXXX","msg":"..."}` 格式

---
## [2026-07-21]

### Fixed
- **主播排班页空白修复**：后端 `AnchorScheduleDashboardResponse` Schema 只定义了 6 个旧字段（`completions`/`details`），但 `build_schedule_dashboard()` 实际返回 `summary`/`anchors`/`rows`/`reminders`/`rule` 等完整字段，被 Pydantic `response_model` 全部过滤掉，导致前端拿到的数据全是 `undefined`、页面显示空白。修复：Schema 新增 10 个字段对齐 Service 返回结构。
- **P0 生产就绪修复**（7 项）：
  - **部署文档 Worker 数量**：`docs/部署.md` 中 uvicorn `--workers 4` → `--workers 1`，加注释说明原因（BrowserManager/SchedulerManager/登录会话在进程内存中，多 Worker 会状态不一致）
  - **部署文档数据库地址**：宿主机部署时 `DB_HOST=mysql` → `127.0.0.1`、`REDIS_URL` 中 `redis` → `127.0.0.1`，加注释区分 Docker 内/外两种场景
  - **Grafana 访问方式**：从 `http://服务器IP:3000` 改为 SSH 隧道 + Nginx 反向代理两种安全方式（Compose 绑定 127.0.0.1）
  - **统一 APP_VERSION**：`config.py` 中 `0.1.0` → `0.9.0`，与版本标签一致
  - **PLAYWRIGHT_HEADLESS 生效**：`browser.py` 2 处 `headless=True` 硬编码 → `headless=settings.PLAYWRIGHT_HEADLESS`，现在可通过 `.env` 控制
  - **补齐 CI 检查**：CI 新增 ruff check + alembic check 步骤，新增 docker-check job；Makefile `check` 目标补上 `docker-check` 依赖
  - **过期文档更新**：`开发.md` 更新文件行数/任务状态/断链；`ADR 0006` 更新待办状态/文件名/行数；`验收测试/说明.md` 修复 6 个英文断链

### Changed
- **主播排班页方案 A 重构**（`index.vue` 646 行 → 147 行，-77%）：
  - 新增 `utils/anchorScheduleHelpers.ts`：10 个纯工具函数（状态映射表、时间格式化、缺场/无效/加场摘要格式化）
  - 新增 `adapters/anchor-schedule-adapter.ts`：表格列定义适配器（用 h() 渲染复杂列内容）
  - 新增 `views/anchor-schedule/composables/useAnchorSchedule.ts`：排班状态管理（全部 ref + computed + 异步操作 + 生命周期）
  - 新增 4 个子组件：`AnchorScheduleStatCards`（KPI 统计卡片）、`AnchorScheduleAnchorCards`（主播完成度卡片网格）、`AnchorScheduleTable`（班次明细表格）、`AnchorScheduleReminderDrawer`（提醒抽屉）
  - `index.vue` 精简为纯编排器：只负责日期控件 + 错误提示 + 组合子组件
  - 后端无改动，纯前端重构
- **主播话术页方案 A 重构**（`index.vue` 796 行 → 154 行，-81%）：
  - 新增 `utils/transcriptHelpers.ts`：7 个纯工具函数（时间格式化、状态文案/类型映射）
  - 新增 `adapters/transcript-adapter.ts`：数据适配器（分类统计、任务卡片配置、场次下拉选项构建）
  - 新增 `views/transcripts/composables/useTranscriptWorkbench.ts`：话术工作台状态管理（全部 ref + computed + 异步操作）
  - 新增 `views/transcripts/composables/useTranscriptRealtime.ts`：WebSocket 实时话术连接管理
  - 新增 5 个子组件：`TranscriptTaskCards`（任务状态卡片）、`TranscriptSessionControl`（场次选择+工具栏）、`TranscriptStatCards`（统计卡片）、`TranscriptContentPanel`（话术内容+侧边栏）、`TranscriptTaskDrawer`（任务抽屉）
  - `index.vue` 精简为纯编排器：只负责组合子组件，所有逻辑委托 composable
  - 后端无改动，纯前端重构
- **采集页方案 A 重构**（`index.vue` 1438 行 → 752 行，模板 547 行 → 128 行）：
  - 新增 `utils/collectorHelpers.ts`：6 个纯工具函数（时间解析/格式化、日志摘要拼接）
  - 新增 `composables/useCollectorPolling.ts`：轮询 + 时钟逻辑抽离
  - 新增 7 个子组件：`CollectorStatCards`（统计卡片）、`CollectorRefreshCard`（刷新采集）、`CollectorMonitorCard`（监控）、`CollectorDataEaseCard`（DataEase）、`CollectorAccountTable`（账号表格）、`CollectorTaskDrawer`（任务抽屉）、`CollectorLogDetailModal`（日志详情）
  - `index.vue` 精简为编排器：只保留状态管理 + 数据加载 + 扫码登录流程，UI 全部委托子组件
  - 后端无改动，纯前端重构
- **AI 复盘页方案 A 重构**（`index.vue` 1000 行 → 187 行，-81%）：
  - 新增 `utils/analysisHelpers.ts`：14 个纯工具函数（日期格式化、分数判定、报告元数据、数据安全工具）
  - 新增 `adapters/review-report-adapter.ts`：报告解析适配器（原始 JSON → 类型安全 AiScoreResult/AiOptimizationResult）
  - 新增 `views/analysis/composables/useReviewWorkbench.ts`：复盘工作台状态管理（所有 ref + computed + 异步操作集中管理）
  - 新增 5 个子组件：`AnalysisSessionControl`（场次选择+启动面板）、`AnalysisStatCards`（4 张统计卡片）、`AnalysisScoreOverview`（复盘总览 Tab）、`AnalysisEvidence`（证据与发现 Tab）、`AnalysisReportHistory`（历史报告 Tab）
  - `index.vue` 精简为编排器：只负责布局 + 传递 props，所有业务逻辑交给 composable
  - 后端无改动，纯前端重构

### Added
- **Matt Pocock 工程技能体系配置**：
  - 新增 `docs/agents/问题追踪.md`：GitHub Issues 作为问题追踪器，含 `gh` CLI 常用操作手册
  - 新增 `docs/agents/分类标签.md`：5 标签分类体系（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）
  - 新增 `docs/agents/领域文档.md`：单上下文领域文档消费者规则（先读 CONTEXT.md + ADR，再探索代码）
  - 新增 `docs/agents/skill技能使用示例.md`：~25 个技能的详细中文使用示例 + 3 套组合拳场景
  - CLAUDE.md 新增 `## Agent skills` 块，注册三个配置入口
  - 新增 ADR 0008《引入 Matt Pocock 工程技能体系》（后续文档精简时归档至 Git 历史）

### Fixed
- **采集日志不显示**：
  - 根因：`CollectorLogTable.vue` 子组件中的 `NDataTable` 使用 `flex-height` 模式，需要 CSS 设定高度才能可见。父组件 `index.vue` 的 scoped CSS 无法穿透 Vue 3 的 scoped 边界（`data-v-xxx` 只加到子组件根元素 `NCard`，不加到内部 `NDataTable`），子组件自身又没有 `<style>` 块 → 表格高度为 0 → 不可见
  - 修复：`CollectorLogTable.vue` 新增 `<style scoped>`，设置 `height: 420px`（移动端 `360px`），同时清理父组件中已失效的同名 CSS
- **scheduler.py 遗漏 import**：M5 拆分 `manual_collect.py` 时 `discover_enterprise_live_sessions` 和 `collect_live_session_snapshot` 的 import 路径未更新，导致监控器运行时 ImportError
- **M1 Schema 字段修复**：
  - `KnowledgeTimeSliceStatusResponse`：5 个错误字段 → 11 个真实字段（修复 response_model 过滤导致全零数据）
  - `DataEaseSyncResponse`：新增 `selected_count`/`errors`/`removed_stale_row_count`，移除不存在的 `skipped_count`
  - `AiKbSaveResponse`/`AiKbSyncRecentResponse`/`AiPipelineResponse`：新增 `review_saved` 字段
  - 重新生成前端类型 `generated.d.ts`
- **M3 URL 常量统一**：
  - 新增 `backend/app/services/collector/constants.py`：`LEADS_BASE`/`LIVE_SCREEN_URL`/`COMMENT_URL`/`DEFAULT_FINGERPRINT`
  - 8 个文件改为从 constants 导入，URL 修改只需改 1 处
  - 修复 5 个 E402/unused-import lint 问题
- **M8 核心链路集成测试**：
  - 新增 `backend/tests/conftest.py`：SQLite 内存数据库 + FastAPI TestClient + 自动建表/删表
  - 新增 `test_integration_auth.py`（9 个测试）：登录/获取用户信息/刷新 Token 全场景覆盖
  - 新增 `test_integration_collector.py`（11 个测试）：采集状态/账号 CRUD/日志/任务
  - 新增 `test_integration_dashboard.py`（8 个测试）：汇总/日期筛选/按主播分组
  - 28 个集成测试全部通过，补充项目首个端到端 API 测试覆盖
  - LONGTEXT→TEXT SQLite 兼容适配（保存/恢复原始类型，不影响其他测试）
- **M10 全项目 Lint 清零**：
  - 后端 ruff：`--fix` 自动修复 48 个 + 手动修复 13 个（含 `l`→`lead` 变量名、`== True`→`.is_(True)`、未使用变量删除等）
  - 前端 ESLint：修复 6 个未使用变量/函数/import（analysis/transcripts/collector/knowledge 页面）
  - 47 个文件净删 73 行无用代码，ruff 0 错误 / ESLint 0 错误
- **M9 Alembic 列注释迁移**：
  - `alembic check` 检测到 45 个列注释缺失（模型已定义但数据库未同步），涉及 6 张表：`ai_call_traces`/`anchor_schedules`/`compliance_rules`/`review_action_items`/`review_findings`/`script_assets`
  - 新增迁移 `27d9dc5d2b31_phase_31_fix_missing_column_comments.py`：45 条 `ALTER TABLE ... MODIFY COLUMN ... COMMENT` + 完整 downgrade
  - 根因：3 个历史迁移（phase_23/phase_28/phase_30）创建表时漏写 `comment=` 参数
  - 修复后 `alembic check` 通过，185 测试全量通过，覆盖率 51% 不变
- **M7 .env.example 补齐 5 个缺项**：
  - 补齐 `FUNASR_HOST` / `FUNASR_PORT` / `ASR_SAMPLE_RATE` / `ASR_WORKER_MODE`（ASR 段）
  - 补齐 `JWT_ALGORITHM`（JWT 段）
- **M6 Docker Redis 硬编码密码修复**：
  - `docker-compose.yml`：Redis `--requirepass` 从硬编码密码改为 `${REDIS_PASSWORD:?...}` 环境变量
  - `.env`：新增 `REDIS_PASSWORD` 独立变量（与 `REDIS_URL` 中的密码保持同步）
  - `.env.example`：补齐 `REDIS_PASSWORD` 和带密码的 `REDIS_URL` 模板
- **M5 browser.py 冗余 .value 移除 + 缺失 import 补充**：
  - 移除 2 处 `TaskStatus.COMPLETED.value` 的冗余 `.value`（TaskStatus 继承 str，直接用即可）
  - 补充缺失的 `touch_task` / `publish_task_event` import（此前扫码登录成功后调用会 NameError）
- **M4 response_model 补齐（11 个端点）**：
  - 新增通用 `MessageResponse`（8 个 DELETE 端点复用）
  - 新增 `AccountDeleteResponse`/`LogsClearResponse`（collector 专用）
  - 复用已有 `LoginQRResponse`（登录二维码端点）
  - 3 个二进制流端点（avatar/video/playback）跳过，加 response_model 会导致 JSON 序列化崩溃
  - 前端类型从 `unknown` 变为具体类型

### Changed
- **统一任务状态枚举**（零数据库迁移）：
  - 新增 `core/status.py`：`TaskStatus` / `ReviewFindingStatus` / `ReviewActionStatus` / `ScriptAssetStatus`（str+Enum 双重继承）
  - 新增 `core/response.py`：`ok_response()` 消除 auth/user_mgmt 重复的 `_ok()` 函数
  - 66 处硬编码状态字符串（`"running"`, `"pending"`, `"failed"` 等）替换为枚举值
  - 15 个 API/Service/Schema 文件引入统一枚举
  - 新增 22 个枚举+响应包装单元测试
- **README.md 重构**（433 行 → 120 行）：
  - 精简为项目门面：项目简介 / 技术栈 / 快速开始 / 核心功能要点 / 文档导航 / 安全问题
  - 详细功能说明、UI/UX 优化记录、ASR 说明、知识库详情等分流到 `docs/开发.md`、`docs/部署.md`、`docs/故障排查.md`
  - 新增 ADR 0007《README 重构与文档职责划分》（后续文档精简时归档至 Git 历史）
- **`manual_collect.py` 模块化拆分**（2,827 行 → 8 个模块，最大 674 行）：
  - 新增 `utils.py`（231 行）— 通用工具：数值/时间解析、去重标识、Cookie 读取
  - 新增 `session.py`（225 行）— 场次 CRUD、重复场次合并修复、主播资料写入
  - 新增 `comments.py`（210 行）— 评论页抓取、增量/全量入库、DOM 兜底解析
  - 新增 `metrics.py`（226 行）— 实时/趋势指标入库、画像解析、摘要映射
  - 新增 `room.py`（674 行）— 大屏页数据捕获、主页直播卡片、流地址抓取
  - 新增 `enterprise.py`（370 行）— 企业员工接口、主播场次映射、直播发现
  - 新增 `history.py`（427 行）— 历史场次同步、详情补齐、实时快照
  - `manual_collect.py`（667 行）— 精简为编排器 + 进度报告 + 错误处理
  - 4 个测试文件导入路径同步更新
  - 消除未使用函数 `_is_context_closed_error`（与 `_is_context_closed_message` 重复）
  - 消除 `_comment_belongs_to_session` 对 LiveSession 模型的冗余依赖
  - `_fetch_enterprise_post` 从 manual_collect 分离到 room，enterprise 反向导入

### Added
- **项目维护体系建立**：
  - 打首个版本标签 `v0.9.0`
  - 新增 `docs/开发.md` 开发指南（含目录结构、开发流程、代码红线、职责分层）
  - 新增 `docs/部署.md` 部署指南（含首次部署、发布流程、回滚方案、备份策略）
  - 新增 `docs/故障排查.md` 故障排查手册（按症状→诊断→解决的结构）
  - 新增 `docs/adr/0006-项目维护标准与红线.md`
- **docs 英文文件名改为中文**：
  - `deployment.md` → `部署.md`、`development.md` → `开发.md`、`troubleshooting.md` → `故障排查.md`
  - `acceptance/` → `验收测试/`、`architecture/` → `架构/`、`audits/` → `审计/`
  - 同步更新 README / CHANGELOG / 架构 README 中的引用路径
- **Makefile 扩展**：
  - 新增 `check` 目标：一键运行测试 + lint + 构建 + 数据库迁移检查
  - 新增 `lint-backend`（ruff）、`db-check`（alembic check）、`docker-check`（docker compose config）
  - 新增 `lint` 目标现在同时检查前后端

---

## [2026-07-20]

### Added
- **首页重做为经营仪表盘**：
  - 日期筛选：今天（默认）/ 本周 / 上周 / 本月 / 上月 + 自定义日期范围选择器
  - 8 张总体经营指标卡片：总场次、总观看、总评论、总私信/线索、广告花费、平均线索成本、待办复盘、活跃主播
  - 主播数据明细表：按主播分组展示场次/观看/评论/私信/线索/新增粉丝/互动/广告花费
  - 后端 `GET /dashboard/summary` 新增 `start_date` / `end_date` 日期参数
  - 后端新增 `GET /dashboard/summary/by-anchor` 按主播分组端点
  - 快捷入口改为：直播场次、话术转写、AI 复盘、知识库
  - 将面向运维的采集状态卡片移出首页

### Removed
- `frontend/src/views/home/modules/` — 6 个 SoybeanAdmin 模板 mock 组件（硬编码假数据，从未被使用）

### Changed
- **播放器整场进度条 + 复盘时间轴联动**：
  - 去掉原生 video controls，改为自定义控制栏
  - 进度条宽度 = 整场直播时长（非仅视频缓冲），点击直接跳转
  - 进度条上标记复盘发现（红/黄/蓝小竖线），hover 显示标题
  - 视频播放进度实时同步到右侧复盘时间轴（高亮当前节点）
  - 点击时间轴节点 → 视频同步跳转
  - 键盘 ← → 控制快退/快进 10 秒
- **播放器卡顿优化**：
  - timeupdate 节流到 250ms（~4fps），Pinia store 更新频率降低 60-75%
  - 进度条 width → transform: scaleX()，GPU 合成层，避免 Layout Reflow
  - 去掉进度条 CSS transition，避免 200ms 动画与高频更新互相冲突导致抖动
  - isPlaying 只在状态真正变化时更新，避免无谓重渲染

### Fixed
- **直播场次详情页 `Cannot read properties of undefined (reading 'map')` 崩溃**：
  - 根因：`ReviewComparisonResponse` Pydantic schema 字段名（`primary`/`baseline`）与 `compare_sessions()` 实际返回（`current`/`baseline`/`dimensions`/`current_series`/`baseline_series`/`comparison_note`）不匹配
  - FastAPI `response_model` 过滤掉未声明字段 → 前端 `comparison.value.current_series` 为 `undefined` → `.map()` 崩溃
  - 修复：schema 字段改为匹配实际返回值，前端添加防御性 `|| []` 保护
  - 新增全局 Vue 错误处理器（`main.ts`）：捕获 `.map()` 错误并输出精确堆栈

### Added
- 根 `.env` 新增 `CORS_ORIGINS` / `BACKEND_RELOAD` 变量
- `config.py` 新增 `extra="ignore"`，兼容 docker-compose / start.sh 专用变量
- 前端 `VITE_ICONIFY_URL` 待配置注释
- 后端 ~40 个端点补齐 Pydantic `response_model`（`schemas/ai.py`, `transcript.py`, `dashboard.py`, `knowledge.py`）
- **契约强制**：`openapi-typescript` 自动从后端 OpenAPI schema 生成前端 TypeScript 类型（`pnpm gen-api`）
- CI 新增 `check-api-types` job：后端改 Pydantic 字段 → 前端类型不同步 → 构建变红
- `frontend/scripts/generate-api-types.ts`：支持本地和 CI 两种模式
- `frontend/src/typings/api/generated.d.ts`：7910 行自动生成的 API 类型定义
- Dependabot groups：npm/pip 的 patch 和 minor 各合并为一个 PR（不再 10 个分散 PR）
- pytest-cov + CI 覆盖率红线（初始阈值 50%）
- `docs/adr/` 目录：5 个架构决策记录（只增不改）
- `docs/架构/说明.md`：架构文档导航
- `docs/adr/0002-*`：绞杀者迁移模板（7 步标准流程）
- `CHANGELOG.md`：按时间倒序的版本变更记录

### Changed
- CORS `allow_origins` 从 `main.py` 硬编码改为读取 `settings.CORS_ORIGINS`
- docker-compose `DATAEASE_ORIGIN_LIST` 改为 `${CORS_ORIGINS:-...}`
- 前后端 `.env` 分离：根 `.env` 纯后端变量，`frontend/.env` 纯 VITE_* 变量
- `.gitignore`: `.env` → `/.env`（只忽略根目录含密钥的 .env）
- 部分架构文档从 `docs/架构/` 迁移为 ADR 格式

### Removed
- `packages/alova/` — 未使用的 HTTP 客户端包（项目用 `@sa/axios`）
- `frontend/.env.prod`, `frontend/.env.test` — SoybeanAdmin 模板 mock 地址
- `.env.production`, `.env.test` — 多余的 Vite mode 文件

### Fixed
- 全站 UI/UX 优化：无障碍（aria-label、44px 触控目标）、8px 间距节奏、暗色模式对比度、图标统一 mdi:
- 安全区域适配（刘海屏/灵动岛）
- `business-focus-ring` / `business-active-press` 通用样式类

---

## [2026-07-18]

### Added
- DataEase 数据大屏 iframe 嵌入
- 内网穿透支持（ngrok）
- 采集刷新全部待补场次
- 前端全站体验优化：响应式栅格、加载状态、失败重试、轮询暂停
- 后端 `settings.runtime_configuration_issues()` 启动前校验
- Prometheus/Grafana 4 条告警规则
- DataEase 只读语义视图（`de_v_*`）
- `ai_call_traces` 表（轻量 Langfuse 风格追踪）
- 主播排班 `de_v_fact_anchor_schedule` 视图
- 复盘发现、整改任务、话术资产接口

### Changed
- 直播场次列表性能优化（数据库分页、轻量字段、索引）
- 长场次可靠性（`LONGTEXT` 保存，Worker 异常回滚）
- 话术工作台：默认最新场次、自动队列、活跃任务 5s 刷新
- 场次详情重构：视频回放 + 统一复盘分析
- 前后端协调验收

### Fixed
- DataEase 登录旧密钥异常
- 采集日志清空二次确认
- ASR 空状态不再误报 404

---

## 模板

后续版本按此格式追加：

```markdown
## [YYYY-MM-DD]

### Added
- 新增的功能

### Changed
- 行为变更

### Fixed
- 已修复的 bug

### Removed
- 已删除的功能
```

## [2026-07-24] — Prompt 管理页面（方案 A）

### 新增
- 前端 Prompt 管理页面（`/prompt-management`），菜单栏排在"主播排班"和"用户管理"之间
- 支持新建提示词、编辑（自动创建新版本保留历史）、删除（二次确认）
- 编辑抽屉内展示该类型所有历史版本，可对比回看
- 后端新增 `GET /ai/prompts/{id}` 和 `PUT /ai/prompts/{id}` 接口

### 变更
- 路由顺序调整：`prompt-management` order=9，`user-management` 顺延至 order=10
- 中英文 i18n 新增 `route.prompt-management`

## [2026-07-24] — Prompt 页改为"仅管理生效提示词"

### 变更
- 后端新增 `GET /ai/prompts/active` 接口，返回 6 种注册类型的最新版本
- 前端重写 Prompt 管理页：加载时自动展示生效的 6 条提示词，去掉"新建"按钮和类型筛选
- 编辑抽屉的"类型"字段改为禁用，禁止变更类型

## [2026-07-24] — Prompt 管理页：版本 diff + 变量检测 + 测试运行

### 新增
- 版本 diff 对比：编辑抽屉中点击「对比当前」，高亮显示新增/删除的行
- 一键恢复旧版：版本历史中每条加「恢复此版本」按钮
- 代码编辑器增强：行号 + monospace 字体 + 字数统计
- 变量占位符检测：自动提取 `{变量名}` 在编辑框下方显示为标签
- 运行测试：使用最近真实场次数据填充提示词，调 DeepSeek 返回结果
- 后端新增 `POST /ai/prompts/test` 接口

## [2026-07-24] — Prompt 管理页编辑抽屉深度优化

### 新增
- 抽屉左右分栏：左侧编辑表单 + 右侧版本历史面板，互不遮挡
- 标题显示当前版本号：`编辑：话术评分 — v2`
- Ctrl+S 快捷键保存
- 「保存并继续」按钮，保存后不关闭抽屉
- diff 独立弹窗：点击「对比」后全屏 Modal 展示完整 diff
- 变量标签点击即插入编辑框光标位置

## [2026-07-24] — 全部提示词重写：精确对齐零食店避坑留资业务

### 变更
- BUSINESS_CONTEXT 重写：明确「教避坑→给资料→引私信」的留资型直播定位，列出 5 类资料钩子
- 6 种提示词全部更新至 v3：评分维度、分析维度、优化建议、意向识别全面对齐留资业务逻辑
- 系统角色提示词同步更新

## [2026-07-24] — 项目业务定位全量适配：留资型直播系统

### 变更
- 系统标题改为「零食店直播运营系统」
- 提示词 v3 已补入数据库，全部对齐留资业务逻辑
- 首页空状态文案增加采集引导
- DataEase 大屏描述更新为留资转化漏斗和线索成本

## [2026-07-24] — 腾讯云短信验证码登录

### 新增
- 腾讯云短信服务对接：发送验证码 + 验证码登录
- 后端新增 `POST /auth/send-code` 和 `POST /auth/code-login` 接口
- 验证码存入 Redis，有效期 5 分钟，一次性使用
- 前端验证码登录页对接真实 API，captcha 钩子重写
- 未配置 APP_ID 时进入开发模式（不真发短信）
