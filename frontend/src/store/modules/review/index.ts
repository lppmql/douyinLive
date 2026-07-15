import { ref } from 'vue';
import { defineStore } from 'pinia';
import { SetupStoreId } from '@/enum';

export const useReviewStore = defineStore(SetupStoreId.Review, () => {
  const sessionId = ref<number | null>(null);
  const currentSecond = ref(0);
  const selectedEvidenceId = ref<number | null>(null);
  const seekToken = ref(0);
  const isPlaying = ref(false);

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
    initialize,
    seekTo,
    updatePlayback
  };
});
