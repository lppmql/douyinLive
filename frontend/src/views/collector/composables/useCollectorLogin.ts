/**
 * 采集页 — 扫码登录流程管理
 *
 * 职责：管理扫码登录的完整生命周期（发起 → 轮询 → 成功/失败 → 清理）。
 * 不依赖其他 composable，只接受 loadData 回调用于登录成功后刷新页面数据。
 */
import { ref } from 'vue';
import { useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { unwrapServiceData } from '@/utils/service';
import {
  startCollectorLogin,
  fetchLoginQR,
  fetchLoginStatus,
  reCollectorLogin
} from '@/service/api/douyin';

/** 登录流程的各个阶段 */
export type LoginState = 'idle' | 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';

export function useCollectorLogin(onLoginSuccess: () => Promise<void>) {
  const message = useMessage();

  /* ===== 状态 ===== */

  const showQRModal = ref(false);
  const qrImage = ref('');
  const loginTaskId = ref<number | null>(null);
  const loginStatus = ref<LoginState>('idle');
  const loginMessage = ref('');
  let loginPollTimer: number | null = null;

  /* ===== 轮询登录状态（每 3 秒检查一次） ===== */

  async function pollLoginStatus() {
    if (loginPollTimer) window.clearInterval(loginPollTimer);

    loginPollTimer = window.setInterval(async () => {
      if (!loginTaskId.value) return;

      try {
        // 第一步：获取二维码图片（只拿一次）
        if (!qrImage.value) {
          try {
            const qrRes = await fetchLoginQR(loginTaskId.value);
            const qrData = unwrapServiceData(qrRes, '二维码尚未生成');
            qrImage.value = qrData.qr_code_base64;
            loginStatus.value = 'scanning';
            loginMessage.value = $t('page.collector.scanQrCode');
          } catch {
            // 二维码可能还没生成好，下一轮再试
          }
        }

        // 第二步：检查登录状态
        const statusRes = await fetchLoginStatus(loginTaskId.value);
        const statusData = unwrapServiceData(statusRes, '登录状态读取失败');

        loginStatus.value = statusData.status as LoginState;
        loginMessage.value = statusData.message;

        if (statusData.status === 'success') {
          message.success($t('page.collector.loginSuccess'));
          stopLoginPoll();
          showQRModal.value = false;
          await onLoginSuccess();
        } else if (statusData.status === 'failed' || statusData.status === 'timeout') {
          message.error(statusData.message || $t('page.collector.loginFailed'));
          stopLoginPoll();
        }
      } catch {
        // 轮询中的临时网络错误忽略，下一轮自动重试
      }
    }, 3000);
  }

  /** 停止轮询定时器 */
  function stopLoginPoll() {
    if (loginPollTimer) {
      window.clearInterval(loginPollTimer);
      loginPollTimer = null;
    }
  }

  /* ===== 公开操作 ===== */

  /** 新账号扫码登录 */
  async function handleStartLogin() {
    try {
      qrImage.value = '';
      loginMessage.value = '';
      stopLoginPoll();
      const res = await startCollectorLogin();
      const data = unwrapServiceData(res, '启动登录失败');
      loginTaskId.value = data.task_id;
      loginStatus.value = 'pending';
      loginMessage.value = '';
      showQRModal.value = true;
      pollLoginStatus();
    } catch {
      message.error('启动登录失败');
    }
  }

  /** 已有账号重新扫码登录 */
  async function handleReLogin(accountId: number) {
    try {
      qrImage.value = '';
      loginMessage.value = '';
      stopLoginPoll();
      const res = await reCollectorLogin(accountId);
      const data = unwrapServiceData(res, '启动重新登录失败');
      loginTaskId.value = data.task_id;
      loginStatus.value = 'pending';
      loginMessage.value = '';
      showQRModal.value = true;
      pollLoginStatus();
    } catch {
      message.error('启动重新登录失败');
    }
  }

  /** 关闭扫码弹窗，清理所有登录状态 */
  function closeQRModal() {
    showQRModal.value = false;
    stopLoginPoll();
    qrImage.value = '';
    loginTaskId.value = null;
    loginStatus.value = 'idle';
    loginMessage.value = '';
  }

  return {
    // 状态
    showQRModal,
    qrImage,
    loginTaskId,
    loginStatus,
    loginMessage,
    // 操作
    handleStartLogin,
    handleReLogin,
    pollLoginStatus,
    stopLoginPoll,
    closeQRModal
  };
}
