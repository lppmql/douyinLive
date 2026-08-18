/** 两个话术页面共用的实时 ASR WebSocket。 */
import { computed, ref, watch, type Ref } from 'vue';
import { useWebSocket } from '@vueuse/core';
import { getServiceBaseURL, getWebSocketBaseURL } from '@/utils/service';

export interface TranscriptRealtimePayload extends Api.Douyin.TranscriptSegment {
  text?: string;
  is_final?: boolean;
}

export interface TranscriptRealtimeOptions {
  selectedSessionId: Ref<number | null>;
  onSegment?: (segment: TranscriptRealtimePayload, sessionId: number) => void;
}

export function useTranscriptRealtime(options: TranscriptRealtimeOptions) {
  const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
  const { otherBaseURL } = getServiceBaseURL(import.meta.env, isHttpProxy);
  const transcriptWsBaseURL = getWebSocketBaseURL(otherBaseURL.backend || window.location.origin);
  const wsUrl = computed(() =>
    options.selectedSessionId.value ? `${transcriptWsBaseURL}/ws/transcript/${options.selectedSessionId.value}` : ''
  );

  const {
    status: wsStatus,
    data: wsData,
    open,
    close
  } = useWebSocket(wsUrl, {
    immediate: false,
    autoReconnect: { retries: 5, delay: 3000 },
    heartbeat: { message: 'ping', interval: 30000 }
  });
  const wsConnected = computed(() => wsStatus.value === 'OPEN');
  const livePreview = ref('');
  const liveSegment = ref<TranscriptRealtimePayload | null>(null);

  watch(wsData, value => {
    if (!value || value === 'pong') return;
    try {
      const result = JSON.parse(String(value)) as TranscriptRealtimePayload & { type?: string };
      if (result.type === 'pong') return;
      const preview = result.text_content || result.text || '';
      if (preview) livePreview.value = preview;
      if (result.id && options.selectedSessionId.value) {
        liveSegment.value = { ...result, text_content: preview };
        options.onSegment?.(liveSegment.value, options.selectedSessionId.value);
      }
    } catch {
      // 心跳或平台异常文本不写入话术列表。
    }
  });

  watch(options.selectedSessionId, sessionId => {
    livePreview.value = '';
    liveSegment.value = null;
    close();
    if (sessionId) setTimeout(() => open(), 100);
  });

  function onPageActivated() {
    if (options.selectedSessionId.value) setTimeout(() => open(), 100);
  }

  function onPageDeactivated() {
    close();
  }

  return { livePreview, liveSegment, wsConnected, onPageActivated, onPageDeactivated };
}
