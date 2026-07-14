import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.api.v1.live_sessions import download_session_video
from app.services.collector.video_download import build_video_download_command


def test_video_download_remuxes_without_reencoding():
    command = build_video_download_command(
        "https://example.test/replay.m3u8",
        {"Referer": "https://example.test", "Cookie": "secret"},
    )

    assert command[command.index("-c") + 1] == "copy"
    assert command[command.index("-bsf:a") + 1] == "aac_adtstoasc"
    assert "frag_keyframe+empty_moov+default_base_moof" in command
    assert any("Referer: https://example.test" in value for value in command)
    assert "secret" not in command


def test_video_download_rejects_local_paths():
    with pytest.raises(ValueError, match="HTTP/HTTPS"):
        build_video_download_command("file:///tmp/private.mp4")


def test_video_download_waits_until_live_has_ended():
    db = SimpleNamespace(get=lambda _model, _record_id: SimpleNamespace(live_status="live"))

    with pytest.raises(HTTPException) as error:
        download_session_video(9, db=db)

    assert error.value.status_code == 409
