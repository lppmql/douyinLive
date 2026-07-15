<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import Hls, { ErrorTypes, Events } from 'hls.js';
import { storeToRefs } from 'pinia';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ReviewVideoPlayer' });
const props = defineProps<{ streamUrl: string | null; title: string }>();
const videoRef = ref<HTMLVideoElement | null>(null);
const errorMessage = ref('');
const reviewStore = useReviewStore();
const { seekToken } = storeToRefs(reviewStore);
let hls: Hls | null = null;

const isHls = computed(() => Boolean(props.streamUrl && /\.m3u8(?:\?|$)/i.test(props.streamUrl)));

function destroyHls() {
  hls?.destroy();
  hls = null;
}

async function attachStream() {
  destroyHls();
  errorMessage.value = '';
  await nextTick();
  const video = videoRef.value;
  if (!video || !props.streamUrl) return;
  if (!isHls.value) {
    errorMessage.value = '当前是直播 FLV 地址，浏览器不能直接回放；下播补齐 m3u8 后即可在此联动复盘。';
    return;
  }
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = props.streamUrl;
    return;
  }
  // oxlint-disable-next-line import/no-named-as-default-member -- hls.js types only expose this as a static class method.
  if (!Hls.isSupported()) {
    errorMessage.value = '当前浏览器不支持 HLS 回放，可继续使用时间轴和视频下载功能。';
    return;
  }
  hls = new Hls({ enableWorker: true, lowLatencyMode: false, backBufferLength: 90 });
  hls.loadSource(props.streamUrl);
  hls.attachMedia(video);
  hls.on(Events.ERROR, (_event, data) => {
    if (!data.fatal) return;
    errorMessage.value = '回放地址已过期或暂时不可访问，请刷新采集后重试。';
    if (data.type === ErrorTypes.NETWORK_ERROR) hls?.startLoad();
    else if (data.type === ErrorTypes.MEDIA_ERROR) hls?.recoverMediaError();
    else destroyHls();
  });
}

function updatePlayback() {
  const video = videoRef.value;
  if (!video) return;
  reviewStore.updatePlayback(video.currentTime, !video.paused);
}

watch(() => props.streamUrl, attachStream, { immediate: true });
watch(seekToken, () => {
  const video = videoRef.value;
  if (!video) return;
  video.currentTime = reviewStore.currentSecond;
});
onBeforeUnmount(destroyHls);
</script>

<template>
  <div class="review-player overflow-hidden rounded-12px bg-[#101820]">
    <div class="aspect-video w-full flex-center">
      <video
        v-if="streamUrl && isHls"
        ref="videoRef"
        class="size-full bg-black object-contain"
        controls
        preload="metadata"
        :aria-label="`${title}直播回放`"
        @timeupdate="updatePlayback"
        @play="updatePlayback"
        @pause="updatePlayback"
      ></video>
      <div v-else class="max-w-520px px-24px text-center text-13px leading-22px text-gray-300">
        <SvgIcon icon="mdi:video-off-outline" class="mb-10px text-42px text-gray-500" />
        <div>{{ errorMessage || '该场次尚未采集到可回放的 m3u8 地址' }}</div>
      </div>
    </div>
    <div class="flex items-center justify-between gap-12px px-14px py-10px text-12px text-gray-300">
      <span class="truncate">{{ title }}</span>
      <span class="shrink-0">联动位置 {{ Math.floor(reviewStore.currentSecond / 60) }}:{{ String(Math.floor(reviewStore.currentSecond % 60)).padStart(2, '0') }}</span>
    </div>
  </div>
</template>

<style scoped>
.review-player {
  box-shadow: 0 18px 40px rgba(11, 20, 28, 0.18);
}
</style>
