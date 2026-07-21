"""
统一任务状态枚举 — 项目中所有任务/处理状态的唯一来源。

设计原则：
1. 枚举值就是数据库中存储的字符串，不改 Column 类型，零迁移
2. 继承 str + Enum，枚举值可以直接当字符串比较（TaskStatus.RUNNING == "running" → True）
3. 每个模型从自己的领域取对应的枚举值，不强制统一

使用方式：
    from app.core.status import TaskStatus, ReviewFindingStatus
    task.status = TaskStatus.RUNNING   # str 继承，直接赋值即可
    if task.status == TaskStatus.RUNNING:  # 直接和字符串比较
        ...
"""

from enum import Enum


class TaskStatus(str, Enum):
    """
    通用任务/处理状态 — 覆盖采集、ASR、话术分段、场次详情等。

    各模型使用的状态子集（以数据库实际 comment 为准）：
    - ScraperTask.status:            PENDING / RUNNING / COMPLETED / FAILED
    - ScraperTask.detail (via LiveSession): PENDING / RETRYABLE / COMPLETED / FAILED
    - AsrTask.status:                QUEUED / PROCESSING / COMPLETED / FAILED
    - AsrTask.postprocess_status:    PENDING / PROCESSING / COMPLETED / FAILED
    - AsrAudioChunk.status:          PENDING / PROCESSING / COMPLETED / FAILED
    - TranscriptSegment.asr_status:  PENDING / PROCESSING / COMPLETED / FAILED
    - LiveSession.detail_collection_status: PENDING / RETRYABLE（也在历史查询中使用）
    """

    PENDING = "pending"           # 已创建，等待执行
    QUEUED = "queued"             # 已入队（ASR 任务专用）
    RUNNING = "running"           # 执行中（采集任务用）
    PROCESSING = "processing"     # 处理中（ASR / AI 后处理用）
    RETRYABLE = "retryable"       # 可重试（场次详情采集失败但可重试）
    COMPLETED = "completed"       # 已成功完成
    FAILED = "failed"             # 已失败（不再自动重试）
    CANCELLED = "cancelled"       # 已取消（预留，当前未使用）


class ReviewFindingStatus(str, Enum):
    """
    复盘发现状态 — ReviewFinding 专用。

    数据库实际值：open / confirmed / dismissed / resolved
    """

    OPEN = "open"                 # 待确认（AI 生成后默认）
    CONFIRMED = "confirmed"       # 已确认（人工核对通过）
    DISMISSED = "dismissed"       # 已忽略（确认为误报）
    RESOLVED = "resolved"         # 已解决（已在后续场次中改进）


class ReviewActionStatus(str, Enum):
    """
    整改任务状态 — ReviewActionItem 专用。

    数据库实际值：pending / in_progress / completed / verified
    """

    PENDING = "pending"           # 待处理
    IN_PROGRESS = "in_progress"   # 处理中
    COMPLETED = "completed"       # 已完成
    VERIFIED = "verified"         # 已验证（跨场确认）


class ScriptAssetStatus(str, Enum):
    """
    话术资产状态 — ScriptAsset 专用。

    数据库实际值：candidate / approved / archived
    """

    CANDIDATE = "candidate"       # 候选（从 ASR 中自动提取）
    APPROVED = "approved"         # 已确认（人工审核通过）
    ARCHIVED = "archived"         # 已归档
