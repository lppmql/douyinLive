"""AI 自动剪辑成片表。

一条记录 = 一个可发布的短视频成品（含标题、文案、话题、片段时间轴）。
生成任务本身复用 scraper_tasks 表（task_type="clip_task"），
这里只保存 AI 选段结果和剪辑产出的文件信息。
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from app.models.base import Base, TimestampMixin


class ClipClip(Base, TimestampMixin):
    """AI 自动剪辑成片 - 每场直播 AI 产出 5 条候选短视频"""

    __tablename__ = "clip_clips"
    __table_args__ = (
        Index("idx_clip_clips_session_status", "session_id", "status"),
        Index("idx_clip_clips_task", "task_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="成片ID")
    task_id = Column(
        BigInteger,
        ForeignKey("scraper_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="最近一次生成该成片的剪辑任务ID",
    )
    session_id = Column(
        Integer,
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联直播场次ID",
    )
    clip_order = Column(Integer, nullable=False, default=1, comment="场次内序号 1-5")
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        comment="状态: draft(待确认)/approved(已确认)/discarded(已丢弃)/failed(生成失败)",
    )
    title = Column(String(200), nullable=True, comment="抖音发布标题（AI 生成）")
    theme = Column(String(200), nullable=True, comment="成片主题摘要")
    description = Column(Text, nullable=True, comment="发布文案（AI 生成）")
    topics_json = Column(JSON, nullable=True, comment="话题标签数组")
    segments_json = Column(
        JSON, nullable=False, comment="剪辑片段数组 [{start, end, text}]"
    )
    duration_seconds = Column(Integer, nullable=True, comment="成片总时长（秒）")
    video_path = Column(
        String(500), nullable=True, comment="成片文件相对 data/videos 的路径"
    )
    cover_path = Column(
        String(500), nullable=True, comment="封面图相对 data/videos 的路径"
    )
    subtitle_path = Column(String(500), nullable=True, comment="ASS 字幕文件相对路径")
    subtitle_srt_path = Column(
        String(500), nullable=True, comment="SRT 字幕文件相对路径"
    )
    clean_video_path = Column(
        String(500), nullable=True, comment="无字幕底片相对路径，供快速重制字幕"
    )
    subtitle_precision = Column(
        String(30), nullable=False, default="segment_estimated", comment="字幕精度来源"
    )
    render_version = Column(
        Integer, nullable=False, default=1, comment="当前成片渲染版本"
    )
    artifact_versions_json = Column(
        JSON, nullable=True, comment="历史成片版本及文件路径"
    )
    selection_evidence_json = Column(
        JSON, nullable=True, comment="评论、互动、钩子、客资等选段证据"
    )
    qc_json = Column(JSON, nullable=True, comment="成片自动质检结果")
    source_text = Column(Text, nullable=True, comment="AI 选段依据的话术摘要")
    ai_raw_json = Column(JSON, nullable=True, comment="AI 原始返回")
    is_manual = Column(
        Integer, nullable=False, default=0, comment="是否人工重剪: 1是 0否"
    )
    error_message = Column(Text, nullable=True, comment="生成失败原因")
