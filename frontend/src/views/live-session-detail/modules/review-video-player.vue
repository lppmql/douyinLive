<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import mpegts from 'mpegts.js';
import { getStreamUrl } from '@/service/api/douyin';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ReviewVideoPlayer' });
const props = defineProps<{
  sessionId: number;
  streamUrl: string | null;
  title: string;
  /** 整场直播总时长（秒） */
  durationSeconds: number;
  /** 复盘发现列表（用于进度条标记） */
  findings: Api.Douyin.ReviewFinding[];
}>();

const videoRef = ref<HTMLVideoElement | null>(null);
const progressRef = ref<HTMLElement | null>(null);
const started = ref(false);
const loading = ref(false);
const errorMessage = ref('');
const isPlaying = ref(false);
const reviewStore = useReviewStore();
const { seekToken } = storeToRefs(reviewStore);

// ── mpegts.js 实例 ──
let player: mpegts.Player | null = null;
/** 当前 ffmpeg 流的起始秒数（video 的 currentTime 从 0 开始，实际时间 = streamStart + currentTime） */
let streamStartSeconds = 0;

// ── 播放进度节流（每 250ms 同步一次）──
let lastSyncTime = 0;
const SYNC_INTERVAL_MS = 250;

/** 当前播放位置（秒），用于进度条 */
const currentTime = computed(() => reviewStore.currentSecond);

/** 总时长：优先用视频实际时长，否则用 session 时长 */
const totalDuration = computed(() => {
  const video = videoRef.value;
  if (video && Number.isFinite(video.duration) && video.duration > 0) return video.duration;
  return props.durationSeconds || 0;
});

/** 进度百分比 */
const progressPercent = computed(() => {
  if (!totalDuration.value) return 0;
  return Math.min(100, (currentTime.value / totalDuration.value) * 100);
});

/** 复盘发现标记点 */
const progressMarkers = computed(() =>
  props.findings
    .filter(f => f.start_seconds != null && f.start_seconds >= 0)
    .map(f => ({
      id: f.id,
      title: f.title,
      severity: f.severity,
      leftPercent: totalDuration.value ? (f.start_seconds! / totalDuration.value) * 100 : 0
    }))
);

// ── 播放器管理 ──

/** 销毁 mpegts.js player 并重置 video 元素 */
function releasePlayer() {
  if (player) {
    try { player.destroy(); } catch { /* 忽略 */ }
    player = null;
  }
  const video = videoRef.value;
  if (video) {
    video.pause();
    video.removeAttribute('src');
    video.load();
  }
}

/** 启动 mpegts.js 播放。
 *  后端输出 H.264 MPEG-TS 流（VideoToolbox 硬编），所有浏览器通用。 */
function startPlayback() {
  if (!props.streamUrl) return;
  const video = videoRef.value;
  if (!video) return;

  errorMessage.value = '';
  loading.value = true;
  started.value = true;

  // 构建绝对 URL（mpegts.js Web Worker 在 blob:// 上下文中运行，必须用绝对路径）
  const url = getStreamUrl(props.sessionId, streamStartSeconds);

  // isLive: true → 连续拉流模式，不发 Range 请求（pipe 输出不支持 Range）
  // enableWorker: true → Web Worker 解复用，不卡主线程
  player = mpegts.createPlayer(
    { type: 'mpegts', isLive: true, url },
    {
      enableWorker: true,
      autoCleanupSourceBuffer: true,
      stashInitialSize: 128,
      enableStashBuffer: false,
      liveBufferLatencyChasing: false,
    },
  );

  player.attachMediaElement(video);
  player.load();

  // 媒体信息就绪 → 开始播放
  let ready = false;
  const onReady = () => {
    if (ready) return;
    ready = true;
    loading.value = false;
    void video.play().catch(() => {});
  };
  player.on(mpegts.Events.MEDIA_INFO, onReady);
  // 兜底：5 秒后强制开始
  setTimeout(onReady, 5000);

  // 错误处理
  player.on(mpegts.Events.ERROR, (_type, info) => {
    console.error('[mpegts.js] 播放错误:', _type, info);
    loading.value = false;
    errorMessage.value = '播放失败，请刷新后重试';
    releasePlayer();
  });
}

// ── 播放/暂停 ──

function togglePlay() {
  const video = videoRef.value;
  if (!video) return;
  if (video.paused) {
    void video.play().catch(() => {});
  } else {
    video.pause();
  }
}

// ── 进度条点击 seek ──
// mpegts.js 无法对连续流做原生 seek，策略：销毁 → 重建（带新 start_seconds）

function seekByProgress(event: MouseEvent) {
  const bar = progressRef.value;
  if (!bar || !totalDuration.value) return;
  const rect = bar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const targetSecond = Math.round(ratio * totalDuration.value);

  if (!started.value) {
    streamStartSeconds = targetSecond;
    reviewStore.seekTo(targetSecond);
    nextTick(() => startPlayback());
    return;
  }

  streamStartSeconds = targetSecond;
  reviewStore.seekTo(targetSecond);
  releasePlayer();
  nextTick(() => startPlayback());
}

// ── 播放进度同步 ──
// video.currentTime 从 0 开始，实际位置 = streamStartSeconds + video.currentTime

function updatePlayback() {
  const video = videoRef.value;
  if (!video) return;
  const now = Date.now();
  const playing = !video.paused;
  if (now - lastSyncTime < SYNC_INTERVAL_MS && isPlaying.value === playing) return;
  lastSyncTime = now;
  if (isPlaying.value !== playing) isPlaying.value = playing;

  const realTime = streamStartSeconds + video.currentTime;
  if (realTime > 0) {
    reviewStore.updatePlayback(realTime, playing);
  }
}

// ── 外部 seek（时间轴点击触发）──

watch(seekToken, () => {
  const target = reviewStore.currentSecond;
  if (!started.value) {
    streamStartSeconds = target;
    nextTick(() => startPlayback());
    return;
  }
  streamStartSeconds = target;
  releasePlayer();
  nextTick(() => startPlayback());
});

// ── 生命周期 ──

onBeforeUnmount(() => {
  releasePlayer();
});

// ── 时间格式化 ──

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}
</script>

<template>
  <div class="review-player overflow-hidden rounded-12px bg-[#101820]">
    <!-- 视频画面区 -->
    <div class="portrait-video-stage w-full flex-center">
      <video
        v-if="streamUrl"
        ref="videoRef"
        class="size-full bg-black object-contain"
        :class="{ 'pointer-events-none opacity-0': !started }"
        playsinline
        preload="none"
        :aria-label="`${title} 直播回放`"
        @timeupdate="updatePlayback"
        @play="updatePlayback"
        @pause="updatePlayback"
        @ended="isPlaying = false"
      ></video>

      <!-- 未播放状态 -->
      <div v-if="!started" class="absolute max-w-360px px-20px text-center text-13px leading-22px text-gray-300">
        <SvgIcon icon="mdi:video-outline" class="mb-10px text-42px text-gray-400" />
        <div v-if="streamUrl">
          H.264 实时转码流，mpegts.js 秒开播放。
        </div>
        <div v-else>该场次尚未采集到可回放的 m3u8 地址。</div>
        <NButton v-if="streamUrl" class="mt-14px" type="primary" secondary @click="startPlayback">
          <template #icon><SvgIcon icon="mdi:play-circle-outline" /></template>
          播放回放
        </NButton>
      </div>

      <!-- 加载中 -->
      <div v-if="started && loading" class="pointer-events-none absolute flex flex-col items-center text-white">
        <NSpin size="large" stroke="#fff" />
        <span class="mt-10px text-12px">正在连接直播流...</span>
      </div>
    </div>

    <!-- 错误提示 -->
    <NAlert v-if="errorMessage" type="error" :show-icon="true" :bordered="false" class="mx-12px mt-10px">
      {{ errorMessage }}
      <NButton text type="primary" class="ml-8px" @click="startPlayback">重新播放</NButton>
    </NAlert>

    <!-- 自定义控制栏 -->
    <div v-if="started" class="player-controls px-10px pb-8px pt-6px">
      <!-- 整场进度条 -->
      <div
        ref="progressRef"
        class="session-progress-bar relative mb-5px h-22px w-full cursor-pointer"
        role="slider"
        :aria-label="`整场进度 ${formatTime(currentTime)} / ${formatTime(totalDuration)}`"
        :aria-valuenow="currentTime"
        :aria-valuemax="totalDuration"
        tabindex="0"
        @click="seekByProgress"
        @keydown.left.prevent="reviewStore.seekTo(Math.max(0, currentTime - 10))"
        @keydown.right.prevent="reviewStore.seekTo(Math.min(totalDuration, currentTime + 10))"
      >
        <div class="absolute bottom-7px h-5px w-full rounded-full bg-white/15"></div>
        <div
          class="absolute bottom-7px h-5px w-full origin-left rounded-full bg-primary"
          :style="{ transform: `scaleX(${progressPercent / 100})` }"
        ></div>
        <div
          class="absolute bottom-1px z-10 h-17px w-17px -translate-x-1/2 rounded-full bg-white shadow-md shadow-black/30"
          :style="{ left: `${progressPercent}%` }"
        ></div>
        <!-- 复盘发现标记点 -->
        <div
          v-for="marker in progressMarkers"
          :key="marker.id"
          class="absolute bottom-7px z-5 h-11px w-3px -translate-x-1/2 rounded-full"
          :class="marker.severity === 'critical' ? 'bg-red-500' : marker.severity === 'warning' ? 'bg-yellow-400' : 'bg-blue-400'"
          :style="{ left: `${marker.leftPercent}%` }"
          :title="marker.title"
        >
          <span class="absolute -top-3px left-1/2 h-5px w-5px -translate-x-1/2 rounded-full" :class="marker.severity === 'critical' ? 'bg-red-500' : marker.severity === 'warning' ? 'bg-yellow-400' : 'bg-blue-400'" />
        </div>
      </div>

      <!-- 控制按钮行 -->
      <div class="flex items-center justify-between gap-8px text-12px text-gray-300">
        <div class="flex items-center gap-8px">
          <button
            type="button"
            class="flex-center h-30px w-30px rounded-full text-white transition hover:bg-white/10"
            :aria-label="isPlaying ? '暂停' : '播放'"
            @click="togglePlay"
          >
            <SvgIcon :icon="isPlaying ? 'mdi:pause' : 'mdi:play'" class="text-20px" />
          </button>
          <span class="font-mono tabular-nums">
            {{ formatTime(currentTime) }}
            <span class="mx-1 text-gray-500">/</span>
            {{ formatTime(totalDuration) }}
          </span>
        </div>

        <!-- 右侧控制信息已按用户要求移除 -->
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-player {
  width: min(100%, 280px);
  box-shadow: 0 18px 40px rgba(11, 20, 28, 0.18);
}

.portrait-video-stage {
  position: relative;
  aspect-ratio: 9 / 16;
}

.session-progress-bar:focus-visible {
  outline: 2px solid rgba(32, 128, 240, 0.7);
  outline-offset: 2px;
}

.session-progress-bar .origin-left {
  will-change: transform;
}

.player-controls {
  background: linear-gradient(to top, rgba(0, 0, 0, 0.5), transparent);
}
</style>
