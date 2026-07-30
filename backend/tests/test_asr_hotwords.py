"""ASR 行业热词的公开行为测试。"""

from app.services.asr import funasr_client
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.hotwords import MAX_HOTWORDS, extract_hotwords


def test_industry_hotwords_keep_core_terms_and_remove_document_noise():
    """行业知识能贡献核心词，但 Markdown 说明文字不能进入识别热词。"""
    hotwords = extract_hotwords()

    assert {"好想来", "赵一鸣", "零食很忙", "快招公司", "回本周期"} <= set(hotwords)
    assert {
        "----------",
        "12",
        "150㎡",
        "不低于",
        "但基本要求",
        "例如河南郑州的",
        "另设广州总部）",
        "商丘等）",
        "南通有部分门店）",
        "黑榜品牌",
        "即二线品牌列表",
        "各省均有门店",
        "含房租等",
        "品牌速查手册",
        "避坑黑榜",
    }.isdisjoint(hotwords)
    assert len(hotwords) <= MAX_HOTWORDS


def test_funasr_start_message_contains_cleaned_industry_hotwords():
    """直播初稿和下播终稿的握手协议都必须真正携带行业热词。"""
    client = FunasrClient("ws://test.invalid")

    realtime_message = client.build_start_message("realtime")
    offline_message = client.build_start_message("offline")

    assert realtime_message["hotwords"] == offline_message["hotwords"]
    for message in (realtime_message, offline_message):
        words = message["hotwords"].split()
        assert {"好想来", "赵一鸣", "快招公司", "回本周期"} <= set(words)
        assert "----------" not in words


def test_funasr_hotword_failure_falls_back_without_blocking_transcription(monkeypatch):
    """行业文档临时损坏时应降级为空热词，不能阻断真实音频转写。"""

    def raise_hotword_error():
        raise OSError("测试用行业文档读取失败")

    monkeypatch.setattr(funasr_client, "get_hotwords_cached", raise_hotword_error)

    message = FunasrClient("ws://test.invalid").build_start_message("offline")

    assert message["hotwords"] == ""
    assert message["mode"] == "offline"
