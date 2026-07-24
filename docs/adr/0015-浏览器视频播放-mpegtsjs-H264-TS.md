# ADR 0015：浏览器视频播放方案选择——mpegts.js + H.264 TS

## 日期
2026-07-24

## 状态
已决定

## 背景

抖音直播回放的 m3u8 原始流是 **H.265（HEVC）** 编码。浏览器 `<video>` 标签对 H.265 支持极差：

- Chrome/Edge：不支持 H.265 硬解（专利问题）
- Safari 17.1+：部分支持
- Firefox：不支持

这意味着直接把 H.265 流给浏览器播放会黑屏或报格式错误。

此外 `v1_router` 有全局 JWT 鉴权（`Depends(get_current_user)`），浏览器 `<video>` 标签的原生 fetch 无法带 JWT header，导致视频请求被返回 401 JSON，浏览器尝试解码 JSON 为视频时触发 `MEDIA_ELEMENT_ERROR: Format error`。

## 决策

选用 **mpegts.js + H.264 MPEG-TS 转码流**。

```
抖音 H.265 m3u8 → ffmpeg VideoToolbox 硬编码 H.264 → MPEG-TS pipe → mpegts.js MSE 解码 → 播放
```

### 对比已废弃的方案

| 方案 | 为什么放弃 |
|------|-----------|
| **EasyPlayer.js WASM** | npm 包 `@easydarwin/easyplayer` v5.1.6 `files` 字段只有 `README.md`，无 dist 文件；`<easy-player>` 元素不支持 raw HTTP MPEG-TS，只支持 HTTP-FLV/WS-FLV/HLS |
| **hls.js + fMP4 分段转码** | fMP4 分段对直播流兼容性差、seek 延迟大、启动时间长 |
| **纯转发 H.265 TS（不转码）** | mpegts.js 理论上支持 H.265 但实际兼容性差，多数浏览器 MSE 不支持 HEVC codec |

### mpegts.js 关键配置

| 参数 | 值 | 原因 |
|------|---|------|
| `type` | `mpegts` | MPEG-TS 容器，不是 fMP4/HLS |
| `isLive` | `true` | 禁用 Range 请求、启用连续拉流 |
| `enableWorker` | `true` | Web Worker 解复用，不卡主线程 |
| `enableStashBuffer` | `false` | 回放场景不需要大缓冲区 |
| URL | **绝对路径** | Web Worker 运行在 `blob://` 上下文，相对路径无法解析 |

### JWT 鉴权绕过

流端点部署在独立的 `stream_router`，直接注册在 `app` 而非 `v1_router`，避开全局 `Depends(get_current_user)`。

### 编码器选择

复用 `select_browser_h264_encoder()`（带 `@lru_cache`），macOS 用 VideoToolbox 硬编码，其他平台回退 libx264 软编码。避免每次请求都执行 `ffmpeg -encoders` 子进程。

## 影响

- **用户体验**：首帧约 2-5 秒（硬编码），全浏览器兼容，无需安装任何插件
- **服务器资源**：每次播放启动一个 ffmpeg 子进程做 H.265→H.264 转码，CPU 负载取决于分辨率和帧率（1080p 约 20-40% 单核）
- **维护**：流端点代码约 110 行，和已有 `playback_session_video` 端点逻辑相似，后续可考虑抽取公共部分

## 后续优化方向

1. 给 ffmpeg 子进程添加 `asyncio.wait_for` 超时保护
2. 添加并发控制信号量，限制同时播放的流数量
3. 抽取公共的 ffmpeg 子进程管理逻辑到 `video_download.py`
