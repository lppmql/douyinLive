"""ffmpeg 剪辑执行引擎。

管线（每片段一次重编码完成，最后无损拼接）：
1. 每个片段独立切割：-ss 前置 input seeking（本地文件精确）+ scale/crop 转竖屏 9:16
   + subtitles 烧录 ASS 大字幕（该片段自己的 0 起时间轴）→ 一次重编码输出；
2. concat demuxer 流拷贝拼接各片段（同参数可直接 -c copy）；
3. 输出首帧截图作为封面。

字幕烧录依赖带 libass 的 ffmpeg：优先使用项目内 .runtime/ffmpeg/ffmpeg
（evermeet.cx 静态版，含 libass+fontconfig），找不到时回退系统 ffmpeg
并检测 subtitles 滤镜是否可用，不可用时报清晰错误而不是静默丢字幕。
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.core.config import PROJECT_ROOT, settings
from app.core.logger import logger
from app.services.clips.ass_subtitle import write_ass_file
from app.services.clips.replay_downloader import session_video_dir

# macOS 系统字体目录，供 fontconfig 找不到字体时兜底（Linux 部署忽略）
MACOS_FONT_DIR = "/System/Library/Fonts"


@functools.lru_cache(maxsize=1)
def resolve_clip_ffmpeg() -> Path | None:
    """定位带字幕能力的 ffmpeg：环境变量 > 项目内静态版 > 系统 ffmpeg。"""
    candidates: list[Path] = []
    env_bin = os.environ.get("CLIP_FFMPEG_BIN")
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
    ass_file: Path,
    output: Path,
    encoder: str | None,
) -> list[str]:
    """单片段命令：切割 + 竖屏 9:16 居中裁剪 + ASS 字幕烧录，一次重编码。"""
    target_w = settings.CLIP_TARGET_WIDTH
    target_h = settings.CLIP_TARGET_HEIGHT
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"subtitles={_escape_filter_path(ass_file)}:fontsdir={_escape_filter_path(Path(MACOS_FONT_DIR))}"
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
    encoder: str | None = None,
) -> dict[str, Path]:
    """渲染一条成片，返回 {video, cover, subtitle} 路径。

    segments: [{start, end, text}]（已由 copywriter 校验，时间戳相对回放）。
    """
    binary = _require_ffmpeg()
    video_dir = session_video_dir(session_id)
    tmp_dir = video_dir / "tmp" / f"clip_{clip_order}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_video = video_dir / f"clip_{clip_order}.mp4"
    out_cover = video_dir / f"clip_{clip_order}_cover.jpg"
    merged_ass = video_dir / f"clip_{clip_order}.ass"

    try:
        # 1) 逐片段切割 + 竖屏 + 字幕烧录
        concat_lines: list[str] = []
        for index, segment in enumerate(segments, start=1):
            start = float(segment["start"])
            end = float(segment["end"])
            duration = end - start
            if duration <= 0:
                raise ValueError(f"片段 {index} 时长非法: {start}-{end}")
            # 每个片段独立字幕（时间轴从 0 起），保证拼接后字幕节奏正确
            seg_ass = tmp_dir / f"seg_{index}.ass"
            write_ass_file([segment], seg_ass)
            seg_out = tmp_dir / f"seg_{index}.mp4"
            _run_ffmpeg(
                _build_segment_command(
                    binary, replay, start, duration, seg_ass, seg_out, encoder
                ),
                f"片段{index}切割({start:.0f}s-{end:.0f}s)",
            )
            concat_lines.append(f"file '{seg_out}'")

        # 2) concat 拼接（流拷贝）
        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        _run_ffmpeg(_build_concat_command(binary, concat_file, out_video), "片段拼接")

        # 3) 封面
        _run_ffmpeg(_build_cover_command(binary, out_video, out_cover), "封面生成")

        # 4) 汇总字幕文件（供前端预览/复查）
        write_ass_file(segments, merged_ass)
        return {"video": out_video, "cover": out_cover, "subtitle": merged_ass}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
