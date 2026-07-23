# 技能使用示例

> 本文档列出本机已安装的全部 AI 技能，每条带一个本项目相关的实际使用示例。
> 使用方法：在对话框输入 `/<技能名>` 即可调用。

---

## 🔍 代码审查与质量（6 个）

### `/code-review` — 代码审查

检查刚改的代码有没有 Bug、逻辑错误、安全隐患。

```
/code-review
```

> 直接输入，AI 会对比 git diff 逐行审查。

---

### `/simplify` — 简化代码

代码能跑但感觉太复杂？让 AI 帮你精简重构。

```
/simplify
```

---

### `/security-review` — 安全检查

检查代码有没有安全漏洞（SQL 注入、XSS、密钥泄露等）。

```
/security-review
```

---

### `/grilling` — 深度拷问

从多个角度深度挑刺，帮你理清思路，比 `/code-review` 更狠。

```
/grilling 帮我审查 backend/app/services/collector/manual_collect.py 有没有隐藏问题
```

---

### `/scope-creep-detector` — 需求范围检查

怀疑需求越改越多跑偏了？让 AI 帮你检查是否超出了原定范围。

```
/scope-creep-detector
```

---

### `/commit-archaeologist` — 代码考古

追查某段代码是谁写的、为什么这么写、什么时候改的。

```
/commit-archaeologist backend/app/api/v1/dashboard.py 第 100 行的子查询是什么时候加的
```

---

## 🐛 诊断与排查（2 个）

### `/diagnosing-bugs` — 系统排查 Bug

从建立反馈循环开始，系统化排查 Bug（复现 → 假设 → 修复）。

```
/diagnosing-bugs 前端打开直播间页面白屏，控制台报 TypeError: Cannot read properties of undefined (reading 'map')
```

```
/diagnosing-bugs 后端 API 返回 500 错误，日志显示 "sqlalchemy.exc.OperationalError: no such column"
```

---

### `/project-graveyard` — 失败项目归档

项目做废了？把经验教训记录下来，以后避坑。

```
/project-graveyard
```

---

## 🎨 UI / 前端与设计（13 个）

### `/ui-ux-pro-max` — 设计规范数据库

67 种风格、161 套配色、57 组字体、99 条 UX 指南，做页面/组件时自动参考。

```
/ui-ux-pro-max 检查 frontend/src/views/home/index.vue 的设计质量
```

```
/ui-ux-pro-max 帮我设计一个数据仪表盘页面的配色方案
```

---

### `/frontend-design` — 前端页面设计

从零设计一个完整的前端页面。

```
/frontend-design 设计一个"主播排班表"页面，支持拖拽调整时间
```

---

### `/design` — 页面/组件设计

通用的 UI 设计方案输出。

```
/design 设计一个"私信留资转化漏斗"的页面
```

---

### `/design-system` — 设计系统

提取和管理项目的设计规范（颜色、字体、间距等）。

```
/design-system 从现有前端页面中提取设计规范
```

---

### `/ui-styling` — 样式调整

调整已有组件的 CSS 样式。

```
/ui-styling 帮我把登录按钮改成圆角、加阴影、hover 时颜色变深
```

---

### `/banner-design` — Banner 设计

给页面设计横幅图、头图。

```
/banner-design 为我的直播间运营系统做一个首页 Banner
```

---

### `/brand` — 品牌设计

设计 Logo、品牌色系、字体方案。

```
/brand 为"零食店避坑指南"这个抖音号设计一套品牌色系
```

---

### `/prototype` — 快速原型

快速做一个可交互的页面原型。

```
/prototype 做一个评论管理页面的原型
```

---

### `/dataviz` — 数据可视化

创建任何类型的图表（柱状图、折线图、饼图、仪表盘等）。

```
/dataviz 按主播分组，画一张"观看人数对比"柱状图
```

```
/dataviz 画一张"近 30 天线索数量趋势"折线图
```

---

### `/slides` — 制作幻灯片

生成演示文稿/PPT。

```
/slides 帮我做一份"直播间运营复盘月度汇报"PPT
```

---

### `/domain-modeling` — 领域建模

帮你梳理业务概念，生成术语表和领域模型。

```
/domain-modeling 我这是个抖音直播间运营系统，帮我梳理核心业务概念
```

---

### `/codebase-design` — 代码库架构设计

从零设计一个模块的代码结构。

```
/codebase-design 我要加一个"自动化采集调度"模块，帮我设计代码结构
```

---

### `/impeccable` — 极致打磨

追求完美方案时用，AI 会反复推敲每一个细节。

```
/impeccable 帮我打磨 backend/app/services/collector/scheduler.py 的调度逻辑
```

---

## 📊 深度调研（3 个）

### `/research` — 快速调研

轻量级技术调研，适合快速查技术选型。

```
/research Vue 3 状态管理方案对比：Pinia vs Vuex
```

---

### `/deep-research` — 深度调研

多来源搜索 + 交叉验证，输出带引用的调研报告。

```
/deep-research Python 异步音视频处理的最佳实践方案
```

```
/deep-research 抖音直播间数据采集的技术方案对比（Selenium vs Playwright vs 抓包）
```

---

### `/agent-reach` — Agent 范围分析

分析当前项目的 Agent 能做什么、不能做什么。

```
/agent-reach
```

---

## 🧪 测试（1 个）

### `/tdd` — 测试驱动开发

先写测试，再写代码，确保代码质量。

```
/tdd 给 backend/app/services/collector/utils.py 写单元测试
```

---

## 🚀 项目启动与运行（2 个）

### `/run` — 启动项目

启动前后端，在浏览器里看效果。

```
/run
```

---

### `/init` — 初始化项目

新项目第一次用 Claude Code 时初始化配置。

```
/init
```

---

## 🐙 Git 相关（2 个）

### `/git-commit` — 规范提交

自动分析改动，生成规范的中文 commit message。

```
/git-commit
```

---

### `/resolving-merge-conflicts` — 解决合并冲突

Git merge 冲突了不知道怎么解。

```
/resolving-merge-conflicts
```

---

## 🔄 自动化与配置（5 个）

### `/loop` — 定时执行

让某个命令每隔一段时间自动跑。

```
/loop 5m /code-review
```

> 每 5 分钟自动审查一次代码。

---

### `/find-skills` — 发现技能

帮你发现和安装新的 AI 技能。

```
/find-skills
```

```
/find-skills 有没有能帮我写飞书文档的技能
```

---

### `/update-config` — 配置 Claude Code

修改 Claude Code 的设置（权限、Hook、环境变量等）。

```
/update-config 以后每次 git commit 前自动跑一遍 pytest
```

---

### `/keybindings-help` — 自定义快捷键

修改 Claude Code 的键盘快捷键。

```
/keybindings-help 把提交命令的快捷键改成 Ctrl+Enter
```

---

### `/fewer-permission-prompts` — 减少权限弹窗

分析你的使用日志，自动配置白名单减少弹窗打扰。

```
/fewer-permission-prompts
```

---

## 💬 决策辅助（1 个）

### `/grilling` — 深度拷问

不断追问你的决策，逼你理清思路再动手。

```
/grilling 我想把数据库从 SQLite 换成 PostgreSQL，帮我理清利弊
```

---

## 🔌 API 参考（1 个）

### `/claude-api` — Claude API 参考

查询 Claude API 的模型列表、价格、参数、Token 计算等。

```
/claude-api Claude Opus 4 和 Sonnet 5 价格差多少
```

```
/claude-api 怎么在代码里用 Prompt Caching 省钱
```

---

## 🔍 代码审查（GitHub PR）（1 个）

### `/review` — 审查 Pull Request

列出 GitHub 上待审查的 PR，选一个进行审查。

```
/review
```

---

## 🏢 飞书 Lark 集成（21 个）

### `/lark-doc` — 飞书文档

读写飞书文档。

```
/lark-doc 把本次直播复盘数据写成飞书文档
```

---

### `/lark-sheets` — 飞书电子表格

读写飞书电子表格。

```
/lark-sheets 把主播数据导出到飞书表格
```

---

### `/lark-base` — 飞书多维表格

操作飞书多维表格（数据库）。

```
/lark-base 在飞书多维表格里创建"直播间运营看板"
```

---

### `/lark-calendar` — 飞书日历

管理飞书日历。

```
/lark-calendar 帮我在飞书日历里排下周的直播时间表
```

---

### `/lark-im` — 飞书即时消息

发送/读取飞书消息。

```
/lark-im 把今日运营数据摘要发到飞书运营群里
```

---

### `/lark-task` — 飞书任务

管理飞书任务列表。

```
/lark-task 在飞书里创建"修复主播头像 Bug"这个任务
```

---

### `/lark-vc` — 飞书视频会议

管理飞书视频会议。

```
/lark-vc 帮我创建一个飞书视频会议"周复盘会"
```

---

### `/lark-vc-agent` — 飞书会议 Agent

让 Agent 代表你参加飞书会议、记录要点。

```
/lark-vc-agent 帮我在今晚 8 点的运营周会里做纪要
```

---

### `/lark-approval` — 飞书审批

处理飞书审批流程。

```
/lark-approval 帮我创建一个"直播间推流码申请"审批模板
```

---

### `/lark-wiki` — 飞书知识库

读写飞书知识库。

```
/lark-wiki 在飞书知识库里更新"抖音直播运营 SOP"页面
```

---

### `/lark-okr` — 飞书 OKR

管理飞书 OKR。

```
/lark-okr 帮我在飞书 OKR 里创建本月的运营目标
```

---

### `/lark-mail` — 飞书邮箱

收发飞书邮件。

```
/lark-mail 把运营周报通过飞书邮箱发给团队
```

---

### `/lark-minutes` — 飞书会议纪要

生成飞书会议纪要。

```
/lark-minutes 把今晚直播复盘会的录音转成纪要
```

---

### `/lark-slides` — 飞书幻灯片

创建飞书幻灯片。

```
/lark-slides 帮我做一份"零食店避坑指南"课程 PPT
```

---

### `/lark-drive` — 飞书云盘

管理飞书云盘文件。

```
/lark-drive 把后端导出的 Excel 报表上传到飞书云盘
```

---

### `/lark-contact` — 飞书通讯录

查询飞书通讯录。

```
/lark-contact 帮我查运营组有哪些成员
```

---

### `/lark-event` — 飞书事件订阅

管理飞书事件通知。

```
/lark-event
```

---

### `/lark-markdown` — 飞书 Markdown

把 Markdown 内容渲染到飞书。

```
/lark-markdown 把 CHANGELOG.md 转成飞书消息格式
```

---

### `/lark-openapi-explorer` — 飞书 API 浏览器

浏览飞书 OpenAPI。

```
/lark-openapi-explorer 查一下飞书文档的 API 接口有哪些
```

---

### `/lark-shared` — 飞书共享工具

飞书相关操作的共享基础工具，其他飞书技能依赖它。

---

### 飞书工作流快捷模板（2 个）

| 技能 | 用途 | 示例 |
|------|------|------|
| `/lark-workflow-meeting-summary` | 生成会议纪要工作流 | `/lark-workflow-meeting-summary` |
| `/lark-workflow-standup-report` | 生成站会报告工作流 | `/lark-workflow-standup-report` |

---

## 🛠️ 其他飞书工具技能（2 个）

| 技能 | 用途 |
|------|------|
| `/lark-apps` | 飞书应用管理 |
| `/lark-attendance` | 飞书考勤 |
| `/lark-skill-maker` | 制作飞书相关技能 |
| `/lark-whiteboard` | 飞书白板 |

---

## 💡 实战组合拳

### 场景：我要做一个新功能

```
第 1 步：/grilling 我想做"私信留资自动打标签"功能
第 2 步：/codebase-design 设计自动打标签模块的代码结构
第 3 步：/frontend-design 设计标签管理页面
第 4 步：写代码...
第 5 步：/code-review
第 6 步：/run（启动项目实际验证）
```

### 场景：发现一个 Bug

```
第 1 步：/diagnosing-bugs [贴报错信息]
第 2 步：让 AI 修...
第 3 步：/code-review
第 4 步：/run（验证修复）
```

### 场景：代码越来越乱

```
第 1 步：/simplify
第 2 步：/code-review（确认简化后没引入问题）
```

### 场景：要做月度汇报

```
第 1 步：/dataviz 画"本月线索转化趋势"折线图
第 2 步：/slides 把这些图表做成月度汇报 PPT
第 3 步：/lark-doc 把 PPT 导出为飞书文档分享给团队
```

---

> **提示**：输入 `/<技能名>` 即可调用。如果某个技能没反应，可能是还没安装，用 `/find-skills` 搜索安装。
