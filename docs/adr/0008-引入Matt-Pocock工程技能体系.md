# ADR 0008：引入 Matt Pocock 工程技能体系

**日期**：2026-07-21  
**状态**：已采纳

---

## 背景

项目已有 185+ 测试、完整 CI/CD、7 份 ADR 和清晰的代码红线。但随着规模增长，以下场景越来越频繁：

- 提交前想知道代码是否符合规范（Code Review）
- 多个 Issue 同时涌入时需要分类和优先级（Triage）
- 从 Issue 到实现缺少标准化流程（To-Spec / To-Tickets）
- 架构改进时需要系统性分析（Grill / Improve Architecture）

目前这些工作全凭人工判断，缺乏辅助工具和标准化流程。

## 决策

引入 [Matt Pocock 工程技能体系](https://github.com/mattpocock/engineering-skills)，配置如下：

| 配置项 | 选择 | 原因 |
|--------|------|------|
| 问题追踪器 | GitHub Issues（`gh` CLI） | 项目已有 GitHub 仓库，原生集成 |
| 分类标签 | 5 默认标签 | 标准三问流程，无需自定义 |
| 领域文档 | 单上下文（`CONTEXT.md` + `docs/adr/`） | 非 monorepo，单仓库结构 |

### 已安装的技能

- **代码审查**：`/code-review` — 双轴审查（规范 + 需求），并行子代理
- **问题分类**：`/triage` — 按标签分类，识别重复/模糊问题
- **Issue 转任务**：`/to-tickets` — 把 Issue 拆成可执行的子任务
- **Issue 转规格**：`/to-spec` — 从 Issue 中提取技术规格
- **深入质询**：`/grill-with-docs` — 对照文档深挖假设
- **架构改进**：`/improve-codebase-architecture` — 系统分析并提案改进
- **领域建模**：`/domain-modeling` — 维护术语表和领域文档

## 影响

- **正面**：每次改代码前有标准审查流程，需求管理更规范，新手友好
- **负面**：多了一套配置文件和概念需要理解
- **回滚**：删除 `docs/agents/` 目录 + 移除 `CLAUDE.md` 中 `## Agent skills` 块即可

## 替代方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| 不用技能体系，继续人工处理 | 零配置 | 缺乏标准化，依赖经验 |
| 自建脚本/规则 | 完全定制 | 维护成本高，无社区支持 |
| Linear / Jira | 功能强大 | 需额外服务，与 GitHub 重复 |
