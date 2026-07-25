# ADR 0021：ASR 失败任务清空功能

**日期**：2026-07-25
**状态**：已实施

## 背景

ASR 话术转写偶尔会因为 FunASR 服务崩溃、音频下载失败、网络超时等原因产生失败任务。
这些失败任务会堆积在任务列表中，用户需要一个简单的方式清理它们。

虽然系统已有「重试」功能（`POST /collector/task-queue/asr/{id}/retry`），
但有些失败任务确实无法恢复（如直播回放链接永久过期），清理掉可以让任务列表更清爽。

## 决策

### 1. 只允许删除 failed / cancelled 状态

**选择**：API 层校验，只有 `status IN ('failed', 'cancelled')` 的任务才能删除。

**原因**：
- `queued` 任务：Worker 可能正在取走，突然删除会让 Worker 找不到任务
- `processing` 任务：Worker 正在处理中，删除会导致 Worker 状态混乱
- `completed` 任务：有用户需要的真实话术数据，不应该删除
- 如果用户想停止正在进行的任务，应该先调停止接口，等状态变成 cancelled 后再删除

### 2. 删除时同步清理关联数据

**选择**：删除任务时，同步删除 `asr_audio_chunks`（音频分片）和 `transcript_segments`（话术分段）。

**原因**：
- `asr_audio_chunks` 是转写进度追踪表，任务没了就没有存在意义
- `transcript_segments` 是失败任务的残留数据，可能不完整或错误，留着会误导用户
- 如果用户之后重新发起转写成功，会产生新的完整话术分段

### 3. 前端确认弹窗

**选择**：每次删除前弹确认框（NaiveUI `dialog.warning`）。

**原因**：
- 删除不可撤销，确认弹窗防止误操作
- 弹窗里写明会清理关联数据，让用户知道后果
- 批量清空时显示数量（如「清空全部 5 条失败任务」）

### 4. 前端按钮位置

**选择**：在任务抽屉（TranscriptTaskDrawer）里放两个操作入口：
- 顶部红色按钮：「清空全部失败任务（N 条）」— 仅在筛选到「失败」tab 时显示
- 每条任务右侧删除按钮 — 仅在 `failed` / `cancelled` 状态时显示

## 影响范围

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 API | `backend/app/api/v1/ws.py` | 新增 `DELETE /tasks/{id}` 和 `DELETE /tasks/failed` |
| 后端 Schema | `backend/app/schemas/transcript.py` | 新增 `TranscriptTaskDeleteResponse`、`TranscriptFailedClearResponse` |
| 前端 API | `frontend/src/service/api/douyin.ts` | 新增 `deleteTranscriptTask()`、`clearFailedTranscriptTasks()` |
| 前端状态 | `frontend/src/views/transcripts/composables/useTranscriptWorkbench.ts` | 新增 `deleteTask()`、`clearFailedTasks()` |
| 前端 UI | `frontend/src/views/transcripts/components/TranscriptTaskDrawer.vue` | 新增清空按钮、删除按钮 |
| 前端编排 | `frontend/src/views/transcripts/index.vue` | 传递新 props 和事件 |

## 替代方案（已拒绝）

### 方案 A：删除任务但保留话术分段

**拒绝原因**：失败任务产生的话术分段通常不完整或为空，保留没有意义。
用户很可能在任务失败后重试，产生新的完整分段，旧数据反而会造成混淆。

### 方案 B：软删除（加 deleted_at 字段）

**拒绝原因**：系统目前没有软删除的需求，增加复杂度没有实际收益。
失败任务的数据价值很低（转写不完整），真需要时可以重新发起转写。
