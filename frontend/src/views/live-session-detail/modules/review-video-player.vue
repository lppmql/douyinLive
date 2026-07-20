<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { getLiveSessionPlaybackUrl } from '@/service/api/douyin';
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
const playbackOffset = ref(0);
const errorMessage = ref('');
const isPlaying = ref(false);
const reviewStore = useReviewStore();
const { seekToken } = storeToRefs(reviewStore);
let loadingTimer: ReturnType<typeof setTimeout> | undefined;

// ── 播放进度节流：timeupdate 每秒触发 4-10 次，节流到 ~4fps (250ms) 避免卡顿 ──
let lastSyncTime = 0;
const SYNC_INTERVAL_MS = 250;
let rafId: ReturnType<typeof requestAnimationFrame> | undefined;

const playbackUrl = computed(() => getLiveSessionPlaybackUrl(props.sessionId, playbackOffset.value));

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

/** 在进度条上值得标记的复盘发现（有 start_seconds 的） */
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

function clearLoadingTimer() {
  if (loadingTimer) clearTimeout(loadingTimer);
  loadingTimer = undefined;
}

function beginLoading() {
  clearLoadingTimer();
  loading.value = true;
  loadingTimer = setTimeout(() => {
    loading.value = false;
    started.value = false;
    releaseVideo();
    errorMessage.value = '兼容画面生成超时，旧播放连接已释放，请重新播放。';
  }, 30_000);
}

function releaseVideo() {
  const video = videoRef.value;
  if (!video) return;
  video.pause();
  video.removeAttribute('src');
  video.load();
}

function loadAndPlay() {
  const video = videoRef.value;
  if (!video) return;
  video.src = playbackUrl.value;
  video.load();
  void video.play().catch(() => {});
}

function startPlayback() {
  if (!props.streamUrl) return;
  errorMessage.value = '';
  beginLoading();
  started.value = true;
  loadAndPlay();
}

function restartAt(second: number) {
  playbackOffset.value = Math.max(0, second);
  if (!started.value) return;
  beginLoading();
  errorMessage.value = '';
  loadAndPlay();
}

/** 视频播放/暂停切换 */
function togglePlay() {
  const video = videoRef.value;
  if (!video) return;
  if (video.paused) {
    void video.play().catch(() => {});
  } else {
    video.pause();
  }
}

/** 点击进度条跳转到对应位置 */
function seekByProgress(event: MouseEvent) {
  const bar = progressRef.value;
  if (!bar || !totalDuration.value) return;
  const rect = bar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const targetSecond = Math.round(ratio * totalDuration.value);
  // 还没开始播放：直接从该位置启动
  if (!started.value) {
    playbackOffset.value = targetSecond;
    startPlayback();
    return;
  }
  reviewStore.seekTo(targetSecond);
}

/** 节流的播放进度同步：用时间间隔 + requestAnimationFrame 避免高频触发重渲染 */
function updatePlayback() {
  const video = videoRef.value;
  if (!video) return;
  const now = Date.now();
  // 距上次同步不到 250ms 且播放状态没变 → 跳过
  const playing = !video.paused;
  if (now - lastSyncTime < SYNC_INTERVAL_MS && isPlaying.value === playing) return;
  lastSyncTime = now;
  if (isPlaying.value !== playing) isPlaying.value = playing;

  if (rafId) cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(() => {
    const v = videoRef.value;
    if (!v) return;
    reviewStore.updatePlayback(playbackOffset.value + v.currentTime, !v.paused);
  });
}

function handleLoaded() {
  clearLoadingTimer();
  loading.value = false;
  errorMessage.value = '';
  updatePlayback();
}

function handlePlaybackError() {
  clearLoadingTimer();
  loading.value = false;
  isPlaying.value = false;
  const mediaError = videoRef.value?.error;
  errorMessage.value = mediaError?.message || '兼容回放启动失败，请刷新采集后重试。';
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

watch(seekToken, () => restartAt(reviewStore.currentSecond));

onBeforeUnmount(() => {
  clearLoadingTimer();
  if (rafId) cancelAnimationFrame(rafId);
  releaseVideo();
});
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
        @loadeddata="handleLoaded"
        @canplay="handleLoaded"
        @waiting="loading = true"
        @error="handlePlaybackError"
        @timeupdate="updatePlayback"
        @play="updatePlayback"
        @pause="updatePlayback"
        @ended="isPlaying = false"
      ></video>

      <!-- 未播放状态 -->
      <div v-if="!started" class="absolute max-w-360px px-20px text-center text-13px leading-22px text-gray-300">
        <SvgIcon icon="mdi:video-outline" class="mb-10px text-42px text-gray-400" />
        <div v-if="streamUrl">该回放是 H.265，需转换为浏览器兼容画面。仅在播放期间占用一路硬件转码。</div>
        <div v-else>该场次尚未采集到可回放的 m3u8 地址。</div>
        <NButton v-if="streamUrl" class="mt-14px" type="primary" secondary @click="startPlayback">
          <template #icon><SvgIcon icon="mdi:play-circle-outline" /></template>
          {{
            playbackOffset
              ? `从 ${formatTime(playbackOffset)} 播放`
              : '播放兼容回放'
          }}
        </NButton>
      </div>

      <!-- 加载中 -->
      <div v-if="started && loading" class="pointer-events-none absolute flex flex-col items-center text-white">
        <NSpin size="large" stroke="#fff" />
        <span class="mt-10px text-12px">正在准备 H.264 兼容画面...</span>
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
        <!-- 进度条底色 -->
        <div class="absolute bottom-7px h-5px w-full rounded-full bg-white/15"></div>
        <!-- 已播放进度（GPU 合成层：transform scaleX 不触发 Reflow） -->
        <div
          class="absolute bottom-7px h-5px w-full origin-left rounded-full bg-primary"
          :style="{ transform: `scaleX(${progressPercent / 100})` }"
        ></div>
        <!-- 拖拽圆点 -->
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
          <!-- 播放/暂停 -->
          <button
            type="button"
            class="flex-center h-30px w-30px rounded-full text-white transition hover:bg-white/10"
            :aria-label="isPlaying ? '暂停' : '播放'"
            @click="togglePlay"
          >
            <SvgIcon :icon="isPlaying ? 'mdi:pause' : 'mdi:play'" class="text-20px" />
          </button>
          <!-- 时间显示 -->
          <span class="font-mono tabular-nums">
            {{ formatTime(currentTime) }}
            <span class="mx-1 text-gray-500">/</span>
            {{ formatTime(totalDuration) }}
          </span>
        </div>

        <div class="flex items-center gap-8px">
          <NTag size="small" type="success" :bordered="false">9:16 · H.264</NTag>
          <span class="hidden sm:inline">{{ title }}</span>
        </div>
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

/* GPU 合成层：进度条 scaleX 动画走 Composite 阶段，不触发 Reflow/Repaint */
.session-progress-bar .origin-left {
  will-change: transform;
}

.player-controls {
  background: linear-gradient(to top, rgba(0, 0, 0, 0.5), transparent);
}
</style>
