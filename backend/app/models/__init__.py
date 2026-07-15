"""Phase 1: 10 张核心业务表 + Phase 3: 3 张采集任务表 + Phase 4: 流源表"""
from app.models.base import Base, TimestampMixin
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.comments import Comment
from app.models.leads import Lead
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.analysis_reports import AnalysisReport
from app.models.knowledge_base import KnowledgeBase
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_tasks import ScraperTask
from app.models.scraper_logs import ScraperLog
from app.models.stream_sources import StreamSource
from app.models.asr_tasks import AsrTask
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.user import User

__all__ = [
    "Base",
    "TimestampMixin",
    "LiveRoom",
    "LiveSession",
    "LiveMetric",
    "LiveAudienceProfile",
    "Comment",
    "Lead",
    "TranscriptSegment",
    "TranscriptFullText",
    "AnalysisReport",
    "KnowledgeBase",
    "ScraperAccount",
    "ScraperTask",
    "ScraperLog",
    "StreamSource",
    "AsrTask",
    "AsrAudioChunk",
    "User",
]
