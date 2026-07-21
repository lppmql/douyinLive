/**
 * WebSocket 实时话术连接管理
 *
 * 职责：
 * 1. 根据当前选中场次自动连接/断开 WebSocket
 * 2. 解析实时推送的转写片段，更新 livePreview
 * 3. 收到最终片段时回调通知工作台刷新数据
 * 4. 页面隐藏/切换时自动管理连接生命周期
 */
import { computed, ref, watch, type Ref } from 'vue';
import { useWebSocket } from '@vueuse/core';
import { getServiceBaseURL, getWebSocketBaseURL } from '@/utils/service';

export interface TranscriptRealtimeOptions {
  /** 当前选中的场次 ID */
  selectedSessionId: Ref<number | null>;
  /** 收到最终片段时的回调（用于触发话术数据刷新） */
  onFinalSegment: (sessionId: number) => void;
}

export function useTranscriptRealtime(options: TranscriptRealtimeOptions) {
  const { selectedSessionId, onFinalSegment } = options;

  // WebSocket 地址前缀
  const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
  const { otherBaseURL } = getServiceBaseURL(import.meta.env, isHttpProxy);
  const transcriptWsBaseURL = getWebSocketBaseURL(otherBaseURL.backend || window.location.origin);

  /** WebSocket 地址（场次变化时自动更新） */
  const wsUrl = computed(() =>
    selectedSessionId.value ? `${transcriptWsBaseURL}/ws/transcript/${selectedSessionId.value}` : ''
  );

  const {
    status: wsStatus,
    data: wsData,
    open,
    close
  } = useWebSocket(wsUrl, {
    autoReconnect: { retries: 5, delay: 3000 },
    heartbeat: { message: 'ping', interval: 30000 }
  });

  /** WebSocket 是否已连接 */
  const wsConnected = computed(() => wsStatus.value === 'OPEN');

  /** 实时话术预览文本（转写进行中时持续更新） */
  const livePreview = ref('');

  // ── 监听 WebSocket 消息 ──

  watch(wsData, value => {
    if (!value || value === 'pong') return;
    try {
      const result = JSON.parse(String(value));
      if (result.type === 'pong') return;
      // 实时更新预览文本
      if (result.text) livePreview.value = result.text;
      // 收到最终结果 → 通知工作台静默刷新话术数据
      if (result.is_final && selectedSessionId.value) {
        onFinalSegment(selectedSessionId.value);
      }
    } catch {
      // 非 JSON 心跳消息，忽略
    }
  });

  // ── 场次切换：断开旧连接 → 建立新连接 ──

  watch(selectedSessionId, sessionId => {
    close();
    if (sessionId) setTimeout(() => open(), 100);
  });

  // ── 页面生命周期挂钩（由外部调用） ──

  function onPageActivated() {
    if (selectedSessionId.value) setTimeout(() => open(), 100);
  }

  function onPageDeactivated() {
    close();
  }

  return { livePreview, wsConnected, onPageActivated, onPageDeactivated };
}
