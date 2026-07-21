import { ref } from 'vue';

/**
 * 采集页轮询 + 时钟管理
 *
 * 把定时器逻辑从组件中抽出来，让 index.vue 更干净。
 *
 * @param shouldPoll - 判断当前是否应该触发轮询（比如有采集任务在跑、抽屉打开时）
 * @param onPoll - 轮询回调，通常是 loadData(true) 静默刷新
 *
 * 使用示例：
 * ```ts
 * const { now, startPolling, stopPolling, startClock, stopClock } = useCollectorPolling(
 *   () => collectionRunning.value || Boolean(collectorStatus.value?.active_task_count) || taskDrawerVisible.value,
 *   () => loadData(true)
 * );
 * ```
 */
export function useCollectorPolling(
  shouldPoll: () => boolean,
  onPoll: () => Promise<void>
) {
  /** 当前毫秒时间戳 — 每 30 秒更新一次，驱动相对时间显示（"刚刚" / "X 分钟前"） */
  const now = ref(Date.now());

  let dataPollTimer: number | null = null;
  let clockTimer: number | null = null;

  /** 开始数据轮询：每 5 秒检查是否有任务在运行，有就静默刷新 */
  function startPolling() {
    stopPolling();
    dataPollTimer = window.setInterval(() => {
      // 页面不可见时跳过，省资源
      if (document.visibilityState !== 'visible') return;
      if (shouldPoll()) {
        onPoll();
      }
    }, 5000);
  }

  /** 停止数据轮询 */
  function stopPolling() {
    if (dataPollTimer !== null) {
      window.clearInterval(dataPollTimer);
      dataPollTimer = null;
    }
  }

  /** 开始时钟：每 30 秒刷新 now，所有用到相对时间的地方会自动更新 */
  function startClock() {
    if (clockTimer !== null) window.clearInterval(clockTimer);
    clockTimer = window.setInterval(() => {
      now.value = Date.now();
    }, 30_000);
  }

  /** 停止时钟 */
  function stopClock() {
    if (clockTimer !== null) {
      window.clearInterval(clockTimer);
      clockTimer = null;
    }
  }

  /** 一次性清理所有定时器（组件卸载时调用） */
  function cleanup() {
    stopPolling();
    stopClock();
  }

  return {
    now,
    startPolling,
    stopPolling,
    startClock,
    stopClock,
    cleanup
  };
}
