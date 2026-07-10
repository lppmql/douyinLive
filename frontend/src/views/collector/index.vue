<script setup lang="ts">
import { ref, h, onMounted, onUnmounted } from 'vue';
import { NTag, NButton, useMessage, useDialog } from 'naive-ui';
import { $t } from '@/locales';
import {
  fetchCollectorStatus,
  fetchCollectorAccounts,
  fetchCollectorLogs,
  startCollectorLogin,
  fetchLoginQR,
  fetchLoginStatus,
  reCollectorLogin,
  deleteCollectorAccount,
  fetchMonitorStatus,
  startMonitor,
  stopMonitor,
  triggerMockLive,
  triggerMockEnd,
  collectAllData
} from '@/service/api/douyin';

defineOptions({
  name: 'Collector'
});

const message = useMessage();
const dialog = useDialog();

/* ---------- 状态 ---------- */
const loading = ref(true);
const collectorStatus = ref<Api.Douyin.CollectorStatus | null>(null);
const accounts = ref<Api.Douyin.CollectorAccount[]>([]);
const logs = ref<Api.Douyin.CollectorLog[]>([]);

type LoginState = 'idle' | 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';

/* ---------- 扫码登录 ---------- */
const showQRModal = ref(false);
const qrImage = ref('');
const loginTaskId = ref<number | null>(null);
const loginStatus = ref<LoginState>('idle');
const loginMessage = ref('');
let loginPollTimer: ReturnType<typeof setInterval> | null = null;

/* ---------- 监控 ---------- */
const monitorStatus = ref<Api.Douyin.MonitorStatus | null>(null);
const monitorLoading = ref(false);

/* ---------- 一键采集 ---------- */
const collectAllLoading = ref(false);
const collectAllResult = ref<Api.Douyin.CollectAllResponse | null>(null);

async function loadMonitorStatus() {
  const res = await fetchMonitorStatus();
  if (res.data) monitorStatus.value = res.data;
}

async function handleStartMonitor() {
  monitorLoading.value = true;
  try {
    const res = await startMonitor();
    if (res.data?.success) message.success(res.data.message);
    await loadMonitorStatus();
  } catch { message.error('启动监控失败'); }
  finally { monitorLoading.value = false; }
}

async function handleStopMonitor() {
  monitorLoading.value = true;
  try {
    const res = await stopMonitor();
    if (res.data?.success) message.success(res.data.message);
    await loadMonitorStatus();
  } catch { message.error('停止监控失败'); }
  finally { monitorLoading.value = false; }
}

async function handleTriggerLive() {
  const res = await triggerMockLive();
  if (res.data?.success) message.success(res.data.message);
  else message.warning(res.data?.message || '模拟开播失败');
  await loadMonitorStatus();
}

async function handleTriggerEnd() {
  const res = await triggerMockEnd();
  if (res.data?.success) message.success(res.data.message);
  await loadMonitorStatus();
}

/* ---------- 一键采集 ---------- */
async function handleCollectAll() {
  collectAllLoading.value = true;
  collectAllResult.value = null;
  try {
    const res = await collectAllData();
    collectAllResult.value = res.data;
    if (res.data?.collected_rooms && res.data.collected_rooms > 0) {
      message.success(`采集完成：${res.data.collected_rooms}/${res.data.total_rooms} 个房间`);
      if ((res.data.history_detail_remaining_count || 0) > 0) {
        message.info(
          `历史场次本次补齐 ${res.data.history_detail_synced_count} 场，剩余 ${res.data.history_detail_remaining_count} 场，继续点一次会接着补`
        );
      }
    } else if (res.data?.message) {
      message.warning(res.data.message);
    }
  } catch {
    message.error('一键采集失败');
  } finally {
    collectAllLoading.value = false;
  }
}

/* ---------- 加载数据 ---------- */
async function loadData() {
  loading.value = true;
  try {
    const [statusRes, accountsRes, logsRes] = await Promise.all([
      fetchCollectorStatus(),
      fetchCollectorAccounts(),
      fetchCollectorLogs({ limit: 50 })
    ]);
    if (statusRes.data != null) collectorStatus.value = statusRes.data;
    if (accountsRes.data != null) accounts.value = accountsRes.data;
    if (logsRes.data != null) logs.value = logsRes.data;
  } catch {
    message.error('加载采集数据失败');
  } finally {
    loading.value = false;
  }
}

/* ---------- 扫码登录流程 ---------- */
async function handleStartLogin() {
  try {
    const res = await startCollectorLogin();
    if (!res.data) return;
    loginTaskId.value = res.data.task_id;
    loginStatus.value = 'pending';
    loginMessage.value = '';
    showQRModal.value = true;
    pollLoginStatus();
  } catch {
    message.error('启动登录失败');
  }
}

async function handleReLogin(accountId: number) {
  try {
    const res = await reCollectorLogin(accountId);
    if (!res.data) return;
    loginTaskId.value = res.data.task_id;
    loginStatus.value = 'pending';
    loginMessage.value = '';
    showQRModal.value = true;
    pollLoginStatus();
  } catch {
    message.error('启动重新登录失败');
  }
}

async function handleDeleteAccount(accountId: number) {
  dialog.warning({
    title: $t('common.confirm'),
    content: $t('page.collector.confirmDelete'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteCollectorAccount(accountId);
        message.success($t('common.deleteSuccess'));
        await loadData();
      } catch {
        message.error('删除失败');
      }
    }
  });
}

async function pollLoginStatus() {
  if (loginPollTimer) clearInterval(loginPollTimer);

  loginPollTimer = setInterval(async () => {
    if (!loginTaskId.value) return;

    try {
      // 获取二维码
      if (!qrImage.value) {
        try {
          const qrRes = await fetchLoginQR(loginTaskId.value);
          if (qrRes.data) {
            qrImage.value = qrRes.data.qr_code_base64;
            loginStatus.value = 'scanning';
            loginMessage.value = $t('page.collector.scanQrCode');
          }
        } catch {
          // QR 可能还没生成
        }
      }

      // 检查登录状态
      const statusRes = await fetchLoginStatus(loginTaskId.value);
      if (!statusRes.data) return;

      loginStatus.value = statusRes.data.status as LoginState;
      loginMessage.value = statusRes.data.message;

      if (statusRes.data.status === 'success') {
        message.success($t('page.collector.loginSuccess'));
        stopLoginPoll();
        showQRModal.value = false;
        await loadData();
      } else if (statusRes.data.status === 'failed' || statusRes.data.status === 'timeout') {
        message.error(statusRes.data.message || $t('page.collector.loginFailed'));
        stopLoginPoll();
      }
    } catch {
      // 轮询临时错误忽略
    }
  }, 3000);
}

function stopLoginPoll() {
  if (loginPollTimer) {
    clearInterval(loginPollTimer);
    loginPollTimer = null;
  }
}

function closeQRModal() {
  showQRModal.value = false;
  stopLoginPoll();
}

/* ---------- 表格列 ---------- */
const accountColumns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: () => $t('page.collector.accountName'),
    key: 'account_name',
    ellipsis: { tooltip: true }
  },
  {
    title: () => $t('page.collector.douyinId'),
    key: 'douyin_id',
    ellipsis: { tooltip: true }
  },
  {
    title: () => $t('page.collector.loginStatus'),
    key: 'login_status',
    width: 100,
    render(row: Api.Douyin.CollectorAccount) {
      const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
        logged_in: { type: 'success', label: $t('page.collector.loggedIn') },
        expired: { type: 'error', label: $t('page.collector.statusExpired') },
        never: { type: 'warning', label: $t('page.collector.neverLogin') }
      };
      const info = map[row.login_status] || { type: 'warning', label: row.login_status };
      return h(NTag, { type: info.type, size: 'small' }, { default: () => info.label });
    }
  },
  {
    title: () => $t('page.collector.lastLogin'),
    key: 'last_login_at',
    width: 170,
    render(row: Api.Douyin.CollectorAccount) {
      return row.last_login_at || '-';
    }
  },
  {
    title: () => $t('common.action'),
    key: 'actions',
    width: 140,
    render(row: Api.Douyin.CollectorAccount) {
      const btns: ReturnType<typeof h>[] = [];
      if (row.login_status === 'expired') {
        btns.push(
          h(NButton, {
            text: true,
            type: 'warning',
            size: 'tiny',
            onClick: () => handleReLogin(row.id)
          }, { default: () => $t('page.collector.reLogin') })
        );
      }
      btns.push(
        h(NButton, {
          text: true,
          type: 'error',
          size: 'tiny',
          onClick: () => handleDeleteAccount(row.id)
        }, { default: () => $t('page.collector.deleteAccount') })
      );
      return btns;
    }
  }
];

const collectResultColumns = [
  { title: '主播', key: 'anchor_name', width: 100 },
  { title: '直播', key: 'is_live', width: 60, render(row: { is_live: boolean }) { return row.is_live ? h(NTag, { type: 'success', size: 'small' }, { default: () => '直播中' }) : h(NTag, { type: 'default', size: 'small' }, { default: () => '未开播' }); } },
  { title: '指标数', key: 'metrics_count', width: 80 },
  { title: '评论数', key: 'comments_count', width: 80 },
  { title: '画像数', key: 'profiles_count', width: 80 },
  {
    title: '状态',
    key: 'error',
    width: 200,
    render(row: { error: string | null }) {
      return row.error
        ? h(NTag, { type: 'error', size: 'small' }, { default: () => row.error })
        : h(NTag, { type: 'success', size: 'small' }, { default: () => '成功' });
    }
  },
];

const logColumns = [
  { title: () => $t('page.collector.logTime'), key: 'created_at', width: 180 },
  {
    title: () => $t('page.collector.logLevel'),
    key: 'level',
    width: 80,
    render(row: { level: string }) {
      const typeMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
        info: 'info', warn: 'warning', error: 'error'
      };
      return h(NTag, { type: typeMap[row.level] || 'info', size: 'small' }, { default: () => row.level.toUpperCase() });
    }
  },
  { title: () => $t('page.collector.logMessage'), key: 'message' }
];

/* ---------- 生命周期 ---------- */
onMounted(() => {
  loadData();
  loadMonitorStatus();
});

onUnmounted(() => {
  stopLoginPoll();
});
</script>

<template>
  <div>
    <!-- 加载状态 -->
    <div v-if="loading" class="flex justify-center py-40px">
      <NSpin :stroke-width="12" :size="24" />
      <span class="ml-12px text-gray-400">{{ $t('page.collector.loading') }}</span>
    </div>

    <NSpace v-else vertical :size="16">
      <!-- 采集器状态 -->
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:cloud-upload" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.collector.statusTitle') }}</span>
          </NSpace>
        </template>
        <NSpace align="center" :size="24">
          <NTag
            :type="collectorStatus?.connected ? 'success' : 'error'"
            round
            size="large"
          >
            {{ collectorStatus?.connected ? $t('page.collector.connected') : $t('page.collector.disconnected') }}
          </NTag>
          <span class="text-13px text-gray-500">
            {{ $t('page.collector.activeTasks') }}：{{ collectorStatus?.active_task_count || 0 }}
          </span>
        </NSpace>
      </NCard>

      <!-- 监控控制 -->
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:radar" class="text-22px" />
            <span class="text-16px font-bold">直播监控</span>
          </NSpace>
        </template>
        <NSpace vertical :size="12">
          <NSpace align="center" :size="16">
            <NTag :type="monitorStatus?.running ? 'success' : 'default'" round>
              {{ monitorStatus?.running ? '运行中' : '已停止' }}
            </NTag>
            <span class="text-13px text-gray-500">
              活跃场次：{{ monitorStatus?.active_session_count || 0 }}
            </span>
            <span v-if="monitorStatus?.mock_mode" class="text-13px text-warning">
              🧪 Mock 模式
            </span>
          </NSpace>
          <NSpace :size="12">
            <NButton
              size="small"
              :type="monitorStatus?.running ? 'warning' : 'primary'"
              :loading="monitorLoading"
              @click="monitorStatus?.running ? handleStopMonitor() : handleStartMonitor()"
            >
              {{ monitorStatus?.running ? '停止监控' : '启动监控' }}
            </NButton>
            <NButton
              v-if="monitorStatus?.mock_mode"
              size="small"
              type="success"
              @click="handleTriggerLive"
            >
              模拟开播
            </NButton>
            <NButton
              v-if="monitorStatus?.mock_mode"
              size="small"
              type="error"
              @click="handleTriggerEnd"
            >
              模拟下播
            </NButton>
          </NSpace>
        </NSpace>
      </NCard>

      <!-- 一键采集 -->
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:cloud-download" class="text-22px" />
            <span class="text-16px font-bold">一键采集</span>
          </NSpace>
        </template>
        <NSpace vertical :size="12">
          <p class="text-13px text-gray-500">
            使用已登录的账号 Cookie，自动采集所有主播房间的直播大屏数据。
          </p>
          <NSpace :size="12">
            <NButton
              type="primary"
              :loading="collectAllLoading"
              :disabled="collectAllLoading"
              @click="handleCollectAll"
            >
              <template #icon>
                <SvgIcon icon="mdi:sync" />
              </template>
              {{ collectAllLoading ? '采集中...' : '一键采集全部' }}
            </NButton>
          </NSpace>

          <!-- 采集结果 -->
          <NCard v-if="collectAllResult" size="small" :bordered="true" class="mt-8px">
            <NSpace vertical :size="8">
              <NSpace align="center">
                <span class="text-14px font-bold">采集结果</span>
                <NTag :type="collectAllResult.collected_rooms > 0 ? 'success' : 'warning'" size="small">
                  {{ collectAllResult.collected_rooms }}/{{ collectAllResult.total_rooms }} 个房间成功
                </NTag>
                <span v-if="collectAllResult.message" class="text-13px text-gray-500">
                  {{ collectAllResult.message }}
                </span>
              </NSpace>
              <div class="text-13px text-gray-500">
                历史场次同步 {{ collectAllResult.history_synced_count || 0 }} 场；
                企业主播 {{ collectAllResult.enterprise_anchor_count || 0 }} 个；
                主播映射 {{ collectAllResult.anchor_profile_synced_count || 0 }} 条；
                本次补详情 {{ collectAllResult.history_detail_synced_count || 0 }}/{{ collectAllResult.history_detail_checked_count || 0 }} 场；
                剩余待补 {{ collectAllResult.history_detail_remaining_count || 0 }} 场；
                单次最多补 {{ collectAllResult.history_detail_batch_size || 0 }} 场
              </div>
              <NDataTable
                v-if="collectAllResult.results && collectAllResult.results.length > 0"
                :columns="collectResultColumns"
                :data="collectAllResult.results"
                :bordered="false"
                :single-line="false"
                size="small"
              />
            </NSpace>
          </NCard>
        </NSpace>
      </NCard>

      <!-- 账号列表 -->
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace justify="space-between" align="center">
            <span class="text-15px font-bold">{{ $t('page.collector.accountList') }}</span>
            <NButton type="primary" size="small" @click="handleStartLogin">
              <template #icon>
                <SvgIcon icon="mdi:qrcode-scan" />
              </template>
              {{ $t('page.collector.scanLogin') }}
            </NButton>
          </NSpace>
        </template>
        <NDataTable
          :columns="accountColumns"
          :data="accounts"
          :bordered="false"
          :single-line="false"
          size="small"
          :empty-text="$t('page.collector.noAccount')"
        />
      </NCard>

      <!-- 采集日志 -->
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <span class="text-15px font-bold">{{ $t('page.collector.logTitle') }}</span>
        </template>
        <NDataTable
          :columns="logColumns"
          :data="logs"
          :bordered="false"
          :single-line="false"
          size="small"
        />
      </NCard>
    </NSpace>

    <!-- 扫码登录弹窗 -->
    <NModal v-model:show="showQRModal" :mask-closable="false" preset="card" style="width: 400px">
      <template #header>
        {{ $t('page.collector.scanLogin') }}
      </template>

      <div class="flex flex-col items-center py-20px">
        <!-- QR 码图片 -->
        <div v-if="qrImage" class="w-240px h-240px bg-white rounded-8px p-8px mb-16px shadow">
          <img :src="`data:image/png;base64,${qrImage}`" class="w-full h-full" alt="QR Code" />
        </div>
        <div v-else class="w-240px h-240px flex items-center justify-center bg-gray-50 dark:bg-dark-300 rounded-8px mb-16px">
          <NSpin :size="24" />
        </div>

        <!-- 状态提示 -->
        <p class="text-14px mb-8px text-center" :class="{
          'text-green-500': loginStatus === 'success',
          'text-red-500': loginStatus === 'failed' || loginStatus === 'timeout',
          'text-gray-500': loginStatus === 'pending' || loginStatus === 'scanning'
        }">
          {{ loginMessage || $t('page.collector.scanQrCode') }}
        </p>

        <!-- 失败/超时提示 -->
        <div v-if="loginStatus === 'failed' || loginStatus === 'timeout'" class="mt-8px">
          <NButton type="primary" size="small" @click="handleStartLogin">
            {{ $t('page.collector.scanLogin') }}
          </NButton>
        </div>
      </div>

      <template #footer>
        <NSpace justify="center">
          <NButton @click="closeQRModal">{{ $t('common.cancel') }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped></style>
