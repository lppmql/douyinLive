"""剪辑回放文件与 ffmpeg 前置条件测试。"""

from app.services.clips.replay_downloader import (
    MIN_REPLAY_BYTES,
    build_replay_download_command,
    replay_file_is_usable,
)


def test_replay_file_rejects_empty_and_incomplete_files(tmp_path):
    replay = tmp_path / "replay.mp4"
    assert not replay_file_is_usable(replay)

    replay.write_bytes(b"0" * MIN_REPLAY_BYTES)
    assert not replay_file_is_usable(replay)

    replay.write_bytes(b"0" * (MIN_REPLAY_BYTES + 1))
    assert replay_file_is_usable(replay)


def test_replay_download_uses_preflight_verified_ffmpeg():
    command = build_replay_download_command(
        "https://example.invalid/replay.m3u8",
        output="/tmp/replay.mp4",
        ffmpeg_binary="/project/.runtime/ffmpeg/ffmpeg",
    )

    assert command[0] == "/project/.runtime/ffmpeg/ffmpeg"
