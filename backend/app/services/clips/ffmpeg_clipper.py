"""ffmpeg 剪辑执行引擎。

管线：
1. 每个片段精确切割并转竖屏 9:16，生成无字幕中间视频；
2. concat 无损拼接为 clean.mp4；
3. 按成片局部时间轴一次性烧录 ASS，同时输出可导入剪辑软件的 SRT；
4. 字幕修订只重跑第 3 步，不再重新下载回放或切割画面。

字幕烧录依赖带 libass 的 ffmpeg：优先使用项目内 .runtime/ffmpeg/ffmpeg
（evermeet.cx 静态版，含 libass+fontconfig），找不到时回退系统 ffmpeg
并检测 subtitles 滤镜是否可用，不可用时报清晰错误而不是静默丢字幕。
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from pathlib import Path

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.services.clips.ass_subtitle import write_ass_file, write_srt_file
from app.services.clips.replay_downloader import session_video_dir

# macOS 系统字体目录，供 fontconfig 找不到字体时兜底（Linux 部署忽略）
MACOS_FONT_DIR = "/System/Library/Fonts"


@functools.lru_cache(maxsize=1)
def resolve_clip_ffmpeg() -> Path | None:
    """定位带字幕能力的 ffmpeg：环境变量 > 项目内静态版 > 系统 ffmpeg。"""
    candidates: list[Path] = []
    env_bin = settings.CLIP_FFMPEG_BIN.strip()
    if env_bin:
        candidates.append(Path(env_bin))
    candidates.append(Path(PROJECT_ROOT) / ".runtime" / "ffmpeg" / "ffmpeg")
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        candidates.append(Path(system_ffmpeg))
    for candidate in candidates:
        if candidate.exists() and _supports_subtitles(candidate):
            return candidate
    return None


@functools.lru_cache(maxsize=4)
def _supports_subtitles(binary: Path) -> bool:
    """检测 ffmpeg 是否编译了 subtitles/ass 滤镜（libass）。"""
    try:
        result = subprocess.run(
            [str(binary), "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return bool(re.search(r"\bsubtitles\b|\bass\b", result.stdout))
    except Exception:
        return False


def _require_ffmpeg() -> Path:
    binary = resolve_clip_ffmpeg()
    if not binary:
        raise RuntimeError(
            "找不到支持字幕烧录的 ffmpeg（需要 libass）。"
            "请下载带 libass 的静态版放到 .runtime/ffmpeg/ffmpeg，"
            "或设置环境变量 CLIP_FFMPEG_BIN 指向带字幕支持的 ffmpeg"
        )
    return binary


def _escape_filter_path(path: Path) -> str:
    """转义 ffmpeg filter 参数里的路径特殊字符（冒号/逗号/反斜杠/单引号）。"""
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("'", "\\'")
    )


def _video_encode_args(binary: Path, encoder: str | None = None) -> list[str]:
    """选择编码器与参数：macOS 优先硬件编码，其他回退 libx264。"""
    if encoder is None:
        result = subprocess.run(
            [str(binary), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
        )
        encoder = (
            "h264_videotoolbox" if "h264_videotoolbox" in result.stdout else "libx264"
        )
    if encoder == "h264_videotoolbox":
        return [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            "2500k",
            "-maxrate",
            "3500k",
            "-bufsize",
            "5000k",
        ]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-threads", "1"]


def _build_segment_command(
    binary: Path,
    replay: Path,
    start: float,
    duration: float,
    output: Path,
    encoder: str | None,
) -> list[str]:
    """单片段命令：切割并转竖屏，不烧字幕，供后续快速重制字幕复用。"""
    target_w = settings.CLIP_TARGET_WIDTH
    target_h = settings.CLIP_TARGET_HEIGHT
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h}"
    )
    return [
        str(binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(replay),
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *_video_encode_args(binary, encoder),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "avc1",
        "-movflags",
        "+faststart",
        str(output),
    ]


def _build_subtitle_burn_command(
    binary: Path,
    clean_video: Path,
    ass_file: Path,
    output: Path,
    encoder: str | None,
) -> list[str]:
    """在无字幕成片上烧录字幕；音频直接复制，降低重制成本。"""
    vf = (
        f"subtitles={_escape_filter_path(ass_file)}:"
        f"fontsdir={_escape_filter_path(Path(MACOS_FONT_DIR))}"
    )
    return [
        str(binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(clean_video),
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *_video_encode_args(binary, encoder),
        "-c:a",
        "copy",
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "avc1",
        "-movflags",
        "+faststart",
        str(output),
    ]


def _build_concat_command(binary: Path, concat_file: Path, output: Path) -> list[str]:
    """拼接命令：同参数片段流拷贝合并。"""
    return [
        str(binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]


def _build_cover_command(binary: Path, video: Path, output: Path) -> list[str]:
    """封面命令：取视频第 0.5 秒帧，转竖屏输出 JPG。"""
    target_w = settings.CLIP_TARGET_WIDTH
    target_h = settings.CLIP_TARGET_HEIGHT
    return [
        str(binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        "0.5",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}",
        "-q:v",
        "3",
        str(output),
    ]


def _run_ffmpeg(command: list[str], label: str) -> None:
    """同步执行 ffmpeg，失败抛异常（stderr 截断保留）。"""
    logger.info("[剪辑] %s: %s", label, " ".join(command[:6]) + " ...")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=settings.CLIP_REPLAY_DOWNLOAD_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[-500:]
        raise RuntimeError(f"{label}失败 code={result.returncode}: {stderr}")


def render_clip(
    replay: Path,
    segments: list[dict],
    *,
    clip_order: int,
    session_id: int,
    clip_id: int | None = None,
    render_version: int = 1,
    encoder: str | None = None,
) -> dict[str, Path]:
    """渲染一条成片，返回视频、干净底片、封面及 ASS/SRT 路径。

    segments: [{start, end, text}]（已由 copywriter 校验，时间戳相对回放）。
    """
    binary = _require_ffmpeg()
    video_dir = session_video_dir(session_id)
    stable_clip_id = clip_id or clip_order
    artifact_dir = video_dir / "clips" / str(stable_clip_id) / f"v{render_version}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = video_dir / "tmp" / f"clip_{stable_clip_id}_v{render_version}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    clean_video = artifact_dir / "clean.mp4"
    out_video = artifact_dir / "video.mp4"
    out_cover = artifact_dir / "cover.jpg"
    merged_ass = artifact_dir / "subtitle.ass"
    merged_srt = artifact_dir / "subtitle.srt"

    try:
        # 1) 逐片段切割 + 竖屏，保留无字幕底片
        concat_lines: list[str] = []
        for index, segment in enumerate(segments, start=1):
            start = float(segment["start"])
            end = float(segment["end"])
            duration = end - start
            if duration <= 0:
                raise ValueError(f"片段 {index} 时长非法: {start}-{end}")
            seg_out = tmp_dir / f"seg_{index}.mp4"
            _run_ffmpeg(
                _build_segment_command(
                    binary, replay, start, duration, seg_out, encoder
                ),
                f"片段{index}切割({start:.0f}s-{end:.0f}s)",
            )
            concat_lines.append(f"file '{seg_out}'")

        # 2) concat 拼接（流拷贝）
        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        _run_ffmpeg(_build_concat_command(binary, concat_file, clean_video), "片段拼接")

        # 3) 生成精确字幕并一次性烧录，拼接处的时间由字幕模块统一压缩映射
        write_ass_file(segments, merged_ass)
        write_srt_file(segments, merged_srt)
        _run_ffmpeg(
            _build_subtitle_burn_command(
                binary, clean_video, merged_ass, out_video, encoder
            ),
            "字幕烧录",
        )

        # 4) 封面
        _run_ffmpeg(_build_cover_command(binary, out_video, out_cover), "封面生成")
        return {
            "video": out_video,
            "clean_video": clean_video,
            "cover": out_cover,
            "subtitle": merged_ass,
            "subtitle_srt": merged_srt,
        }
    except Exception:
        # 数据库尚未拿到这些路径，失败版本没有恢复价值，避免留下无引用的大文件。
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def rerender_subtitles(
    clean_video: Path,
    segments: list[dict],
    *,
    session_id: int,
    clip_id: int,
    render_version: int,
    encoder: str | None = None,
) -> dict[str, Path]:
    """复用无字幕底片生成新版本；旧版本文件保持不动，可随时追溯。"""
    if not clean_video.exists():
        raise FileNotFoundError("无字幕底片不存在，请先重新生成整条成片")
    binary = _require_ffmpeg()
    artifact_dir = (
        session_video_dir(session_id) / "clips" / str(clip_id) / f"v{render_version}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ass_path = artifact_dir / "subtitle.ass"
    srt_path = artifact_dir / "subtitle.srt"
    video_path = artifact_dir / "video.mp4"
    cover_path = artifact_dir / "cover.jpg"
    try:
        write_ass_file(segments, ass_path)
        write_srt_file(segments, srt_path)
        _run_ffmpeg(
            _build_subtitle_burn_command(
                binary, clean_video, ass_path, video_path, encoder
            ),
            "仅重制字幕",
        )
        _run_ffmpeg(_build_cover_command(binary, video_path, cover_path), "封面生成")
        return {
            "video": video_path,
            "clean_video": clean_video,
            "cover": cover_path,
            "subtitle": ass_path,
            "subtitle_srt": srt_path,
        }
    except Exception:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise
