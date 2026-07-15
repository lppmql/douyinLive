<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { getLiveSessionPlaybackUrl } from '@/service/api/douyin';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ReviewVideoPlayer' });
const props = defineProps<{ sessionId: number; streamUrl: string | null; title: string }>();
const videoRef = ref<HTMLVideoElement | null>(null);
const started = ref(false);
const loading = ref(false);
const playbackOffset = ref(0);
const errorMessage = ref('');
const reviewStore = useReviewStore();
const { seekToken } = storeToRefs(reviewStore);
let loadingTimer: ReturnType<typeof setTimeout> | undefined;

const playbackUrl = computed(() => getLiveSessionPlaybackUrl(props.sessionId, playbackOffset.value));

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
  void video.play().catch(() => {
    // 保留原生播放按钮，用户仍可手动继续播放。
  });
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

function updatePlayback() {
  const video = videoRef.value;
  if (!video) return;
  reviewStore.updatePlayback(playbackOffset.value + video.currentTime, !video.paused);
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
  const mediaError = videoRef.value?.error;
  errorMessage.value = mediaError?.message || '兼容回放启动失败，请刷新采集后重试。';
}

watch(seekToken, () => restartAt(reviewStore.currentSecond));
onBeforeUnmount(() => {
  clearLoadingTimer();
  releaseVideo();
});
</script>

<template>
  <div class="review-player overflow-hidden rounded-12px bg-[#101820]">
    <div class="portrait-video-stage w-full flex-center">
      <video
        v-if="streamUrl"
        ref="videoRef"
        class="size-full bg-black object-contain"
        :class="{ 'pointer-events-none opacity-0': !started }"
        controls
        playsinline
        preload="none"
        :aria-label="`${title}直播回放`"
        @loadeddata="handleLoaded"
        @canplay="handleLoaded"
        @waiting="loading = true"
        @error="handlePlaybackError"
        @timeupdate="updatePlayback"
        @play="updatePlayback"
        @pause="updatePlayback"
      ></video>
      <div v-if="!started" class="absolute max-w-360px px-20px text-center text-13px leading-22px text-gray-300">
        <SvgIcon icon="mdi:video-outline" class="mb-10px text-42px text-gray-400" />
        <div v-if="streamUrl">该回放是 H.265，需转换为浏览器兼容画面。仅在播放期间占用一路硬件转码。</div>
        <div v-else>该场次尚未采集到可回放的 m3u8 地址。</div>
        <NButton v-if="streamUrl" class="mt-14px" type="primary" secondary @click="startPlayback">
          <template #icon><SvgIcon icon="mdi:play-circle-outline" /></template>
          {{ playbackOffset ? `从 ${Math.floor(playbackOffset / 60)}:${String(Math.floor(playbackOffset % 60)).padStart(2, '0')} 播放` : '播放兼容回放' }}
        </NButton>
      </div>
      <div v-if="started && loading" class="pointer-events-none absolute flex flex-col items-center text-white">
        <NSpin size="large" stroke="#fff" />
        <span class="mt-10px text-12px">正在准备 H.264 兼容画面...</span>
      </div>
    </div>
    <NAlert v-if="errorMessage" type="error" :show-icon="true" :bordered="false" class="mx-12px mt-10px">
      {{ errorMessage }}
      <NButton text type="primary" class="ml-8px" @click="startPlayback">重新播放</NButton>
    </NAlert>
    <div class="flex flex-wrap items-center justify-between gap-8px px-14px py-10px text-12px text-gray-300">
      <span class="min-w-0 flex-1 truncate">{{ title }}</span>
      <div class="flex shrink-0 items-center gap-8px">
        <NTag size="small" type="success" :bordered="false">9:16 · H.264</NTag>
        <span>联动位置 {{ Math.floor(reviewStore.currentSecond / 60) }}:{{ String(Math.floor(reviewStore.currentSecond % 60)).padStart(2, '0') }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-player {
  width: min(100%, 360px);
  margin-inline: auto;
  box-shadow: 0 18px 40px rgba(11, 20, 28, 0.18);
}

.portrait-video-stage {
  position: relative;
  aspect-ratio: 9 / 16;
}
</style>
