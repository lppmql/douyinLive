import { ref } from 'vue';
import { defineStore } from 'pinia';
import { SetupStoreId } from '@/enum';

export const useReviewStore = defineStore(SetupStoreId.Review, () => {
  const sessionId = ref<number | null>(null);
  const currentSecond = ref(0);
  const selectedEvidenceId = ref<number | null>(null);
  const seekToken = ref(0);
  const isPlaying = ref(false);

  /**
   * 待处理的 seek 请求（秒数）。
   *
   * 场景：从知识库来源卡片跳转到场次详情页时，父页面在播放器挂载前就设置了这个值。
   * 播放器挂载后检查该字段，如果存在则从该秒数开始播放。
   * 播放器读取后自动清空（设为 null）。
   */
  const pendingSeekSeconds = ref<number | null>(null);

  function initialize(nextSessionId: number) {
    if (sessionId.value === nextSessionId) return;
    sessionId.value = nextSessionId;
    currentSecond.value = 0;
    selectedEvidenceId.value = null;
    seekToken.value = 0;
    isPlaying.value = false;
  }

  function seekTo(second: number, evidenceId?: number | null) {
    currentSecond.value = Math.max(0, second);
    selectedEvidenceId.value = evidenceId ?? null;
    seekToken.value += 1;
  }

  function updatePlayback(second: number, playing: boolean) {
    currentSecond.value = Math.max(0, second);
    isPlaying.value = playing;
  }

  return {
    sessionId,
    currentSecond,
    selectedEvidenceId,
    seekToken,
    isPlaying,
    pendingSeekSeconds,
    initialize,
    seekTo,
    updatePlayback
  };
});
