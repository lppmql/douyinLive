# 技能使用示例.md

> 本文档列出本项目可用的所有 AI 技能命令，每条带一个实际使用示例。
> 使用方法：在对话框输入 `/技能名` 即可调用。

---

## 🔍 代码审查与质量

### `/code-review` — 代码审查

检查你刚改的代码有没有 Bug、逻辑错误、安全隐患。

```
/code-review
```

> 直接输入即可，AI 会对比最近改动逐行审查。

---

### `/simplify` — 简化代码

代码能跑但感觉太复杂？让 AI 帮你精简重构。

```
/simplify
```

---

### `/diagnosing-bugs` — 排查 Bug

遇到报错不知道原因，把报错信息贴给 AI 分析。

```
/diagnosing-bugs 前端打开直播间页面白屏，控制台报 TypeError: Cannot read properties of undefined (reading 'map')
```

```
/diagnosing-bugs 后端 API 返回 500 错误，日志显示 "sqlalchemy.exc.OperationalError: no such column"
```

---

### `/security-review` — 安全检查

检查代码有没有安全漏洞（SQL 注入、XSS、密钥泄露等）。

```
/security-review
```

---

### `/grilling` — 深度审查

从多个角度深度挑刺，比 `/code-review` 更狠。

```
/grilling 帮我审查 backend/app/services/collector/manual_collect.py 这个文件有没有隐藏问题
```

---

## 📐 需求与任务管理

### `/triage` — Issue 分类

给 GitHub Issue 自动打标签、判断优先级。

```
/triage #1
```

> 前提：你已经在 GitHub 上创建了 Issue，把编号替换成你的。

---

### `/to-tickets` — 需求拆任务

你有一个大想法，让 AI 帮你拆成一步一步的具体任务。

```
/to-tickets 我想在直播间详情页加一个"导出评论为 Excel"的功能
```

```
/to-tickets 给系统加一个暗色模式切换开关
```

---

### `/to-spec` — 写实现规格

有了任务之后，让 AI 写出"具体怎么实现"的详细技术规格。

```
/to-spec 实现评论导出为 Excel 功能
```

---

## 🧠 深度调研与设计

### `/deep-research` — 深度调研

多来源搜索 + 交叉验证，输出一份带引用的调研报告。

```
/deep-research Python 异步音视频处理的最佳实践方案
```

```
/deep-research 抖音直播间数据采集的技术方案对比（Selenium vs Playwright vs 抓包）
```

---

### `/research` — 快速调研

比 deep-research 轻量，适合快速查技术选型。

```
/research Vue 3 状态管理方案对比：Pinia vs Vuex
```

---

### `/domain-modeling` — 领域建模

帮你梳理业务概念，生成 `CONTEXT.md` 术语表。

```
/domain-modeling 我这是个抖音直播间运营系统，帮我梳理核心业务概念
```

---

## 🎨 UI / 前端

### `/ui-ux-pro-max` — 设计规范检查

检查你的前端页面是否符合设计规范（颜色、间距、可访问性等）。

```
/ui-ux-pro-max 检查 frontend/src/views/home/index.vue 的设计质量
```

```
/ui-ux-pro-max 帮我设计一个数据仪表盘页面的配色方案
```

---

### `/banner-design` — Banner 设计

给页面设计横幅图、头图。

```
/banner-design 为我的直播间运营系统做一个首页 Banner
```

---

### `/design` — 页面/组件设计

从零设计一个页面或组件的 UI。

```
/design 设计一个"主播排班表"页面，支持拖拽调整时间
```

---

### `/design-system` — 设计系统

提取和管理项目的设计规范（颜色、字体、间距等）。

```
/design-system 从现有前端页面中提取设计规范
```

---

### `/prototype` — 快速原型

快速做一个可交互的页面原型。

```
/prototype 做一个评论管理页面的原型
```

---

### `/ui-styling` — 样式调整

调整已有组件的样式。

```
/ui-styling 帮我把登录按钮改成圆角、加阴影、hover 时颜色变深
```

---

## 📊 数据可视化

### `/dataviz` — 图表

创建任何类型的图表（柱状图、折线图、饼图等）。

```
/dataviz 按主播分组，画一张"观看人数对比"柱状图
```

```
/dataviz 画一张"近 30 天线索数量趋势"折线图
```

---

## 🧪 测试

### `/tdd` — 测试驱动开发

先写测试，再写代码。

```
/tdd 给 backend/app/services/collector/utils.py 写单元测试
```

---

## 🚀 项目启动与运行

### `/run` — 启动项目

启动前后端，在浏览器里看效果。

```
/run
```

---

## 🐛 Git 相关

### `/resolving-merge-conflicts` — 解决合并冲突

Git merge 冲突了不知道怎么解。

```
/resolving-merge-conflicts
```

---

## 🔁 自动化

### `/loop` — 定时执行

让某个命令每隔一段时间自动跑。

```
/loop 5m /code-review
```

> 每 5 分钟自动审查一次代码。

---

## 🏗️ 代码架构

### `/improve-codebase-architecture` — 改善架构

发现代码架构问题并给出改进方案。

```
/improve-codebase-architecture backend/app/services/ 目录结构有没有改进空间
```

---

### `/codebase-design` — 代码库设计

从零设计一个模块的代码结构。

```
/codebase-design 我要加一个"自动化采集调度"模块，帮我设计代码结构
```

---

## 📖 其他

### `/ask-matt` — 工程最佳实践

问工程实践类的问题。

```
/ask-matt Python 项目应该如何组织 services 层的代码
```

---

## 💡 实战组合拳

### 场景：我要做一个新功能

```
第 1 步：/to-tickets 我想做"主播排班表"功能
第 2 步：/to-spec 实现主播排班表
第 3 步：/codebase-design 设计排班表模块的代码结构
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

---

> **提示**：这些技能会读取 `docs/agents/` 下的配置文件（问题追踪器、标签、领域文档），所以不同项目的同一技能行为可能不同。
