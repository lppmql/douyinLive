# 问题追踪器：GitHub

本项目的问题和需求文档以 GitHub Issues 形式管理。所有操作通过 `gh` CLI 完成。

## 常用操作

- **创建 Issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **查看 Issue**：`gh issue view <编号> --comments`，可用 `jq` 过滤评论、查看标签。
- **列出 Issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，可按 `--label` 和 `--state` 筛选。
- **评论 Issue**：`gh issue comment <编号> --body "..."`
- **添加/移除标签**：`gh issue edit <编号> --add-label "..."` / `--remove-label "..."`
- **关闭 Issue**：`gh issue close <编号> --comment "..."`

仓库信息通过 `git remote -v` 自动推断——在 clone 目录下运行 `gh` 即可。

## PR 作为问题来源

**PR 作为问题来源：否。**（设为"是"时，外部 PR 会被当作功能请求纳入 triage 流程。）

设为"是"时，PR 与 Issue 享有相同的标签和状态流转，使用对应的 `gh pr` 命令：

- **查看 PR**：`gh pr view <编号> --comments`，`gh pr diff <编号>` 查看代码差异。
- **列出待分类的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的（排除 `OWNER`/`MEMBER`/`COLLABORATOR`）。
- **评论 / 标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 中 Issue 和 PR 共享编号空间，裸 `#42` 可能是 Issue 也可能是 PR——先用 `gh pr view 42` 尝试，失败则回退到 `gh issue view 42`。

## 当技能说"发布到问题追踪器"时

创建一个 GitHub Issue。

## 当技能说"获取相关工单"时

运行 `gh issue view <编号> --comments`。
