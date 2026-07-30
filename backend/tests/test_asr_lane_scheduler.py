"""直播与最新下播终稿的单模型分时调度测试。"""

from app.services.asr.lane_scheduler import choose_asr_lane


def test_scheduler_allows_one_offline_chunk_after_three_live_chunks():
    """直播连续执行三片后，下一次必须让最新下播终稿推进一片。"""
    assert choose_asr_lane(True, True, live_streak=0, live_quota=3) == "realtime"
    assert choose_asr_lane(True, True, live_streak=1, live_quota=3) == "realtime"
    assert choose_asr_lane(True, True, live_streak=2, live_quota=3) == "realtime"
    assert choose_asr_lane(True, True, live_streak=3, live_quota=3) == "offline"


def test_scheduler_never_blocks_the_only_available_lane():
    """只有一路有任务时直接执行，不能为了配额制造空转。"""
    assert choose_asr_lane(True, False, live_streak=9, live_quota=3) == "realtime"
    assert choose_asr_lane(False, True, live_streak=0, live_quota=3) == "offline"
    assert choose_asr_lane(False, False, live_streak=0, live_quota=3) is None
