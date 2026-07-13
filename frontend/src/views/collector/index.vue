<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue';
import { NButton, NSpace, NTag, useDialog, useMessage } from 'naive-ui';
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

const loggedInAccountCount = computed(() => accounts.value.filter(item => item.login_status === 'logged_in').length);
const errorLogCount = computed(() => logs.value.filter(item => item.level === 'error').length);
const hasAvailableAccount = computed(() => loggedInAccountCount.value > 0);

const getAccountRowKey = (row: Api.Douyin.CollectorAccount) => row.id;
const getLogRowKey = (row: Api.Douyin.CollectorLog) => row.id;
const getCollectResultRowKey = (row: Api.Douyin.CollectRoomResult) => row.room_id;

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
  } catch {
    message.error('启动监控失败');
  } finally {
    monitorLoading.value = false;
  }
}

async function handleStopMonitor() {
  monitorLoading.value = true;
  try {
    const res = await stopMonitor();
    if (res.data?.success) message.success(res.data.message);
    await loadMonitorStatus();
  } catch {
    message.error('停止监控失败');
  } finally {
    monitorLoading.value = false;
  }
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
    await loadData();
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
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
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
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
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
  qrImage.value = '';
  loginTaskId.value = null;
  loginStatus.value = 'idle';
  loginMessage.value = '';
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
          h(
            NButton,
            {
              text: true,
              type: 'warning',
              size: 'tiny',
              onClick: () => handleReLogin(row.id)
            },
            { default: () => $t('page.collector.reLogin') }
          )
        );
      }
      btns.push(
        h(
          NButton,
          {
            text: true,
            type: 'error',
            size: 'tiny',
            onClick: () => handleDeleteAccount(row.id)
          },
          { default: () => $t('page.collector.deleteAccount') }
        )
      );
      return h(NSpace, { size: 12, wrap: false }, { default: () => btns });
    }
  }
];

const collectResultColumns = [
  { title: '主播', key: 'anchor_name', minWidth: 140, ellipsis: { tooltip: true } },
  {
    title: '直播',
    key: 'is_live',
    width: 60,
    render(row: { is_live: boolean }) {
      return row.is_live
        ? h(NTag, { type: 'success', size: 'small' }, { default: () => '直播中' })
        : h(NTag, { type: 'default', size: 'small' }, { default: () => '未开播' });
    }
  },
  { title: '指标数', key: 'metrics_count', width: 80 },
  { title: '评论数', key: 'comments_count', width: 80 },
  { title: '画像数', key: 'profiles_count', width: 80 },
  {
    title: '状态',
    key: 'error',
    minWidth: 160,
    render(row: { error: string | null }) {
      return row.error
        ? h(NTag, { type: 'error', size: 'small' }, { default: () => row.error })
        : h(NTag, { type: 'success', size: 'small' }, { default: () => '成功' });
    }
  }
];

const logColumns = [
  { title: () => $t('page.collector.logTime'), key: 'created_at', width: 180 },
  {
    title: () => $t('page.collector.logLevel'),
    key: 'level',
    width: 80,
    render(row: { level: string }) {
      const typeMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
        info: 'info',
        warn: 'warning',
        error: 'error'
      };
      return h(NTag, { type: typeMap[row.level] || 'info', size: 'small' }, { default: () => row.level.toUpperCase() });
    }
  },
  { title: () => $t('page.collector.logMessage'), key: 'message', minWidth: 420, ellipsis: { tooltip: true } }
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
  <div class="min-h-full flex-col gap-16px overflow-auto">
    <NSpin :show="loading">
      <NSpace vertical :size="16">
        <NGrid cols="1 s:2 l:4" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">采集服务</div>
                  <div class="mt-8px text-20px font-600">
                    {{ collectorStatus?.connected ? '连接正常' : '连接异常' }}
                  </div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-primary-100 text-primary dark:bg-primary-900/30">
                  <SvgIcon icon="mdi:database-sync-outline" class="text-24px" />
                </div>
              </div>
              <NTag class="mt-16px" :type="collectorStatus?.connected ? 'success' : 'error'" round size="small">
                {{ collectorStatus?.connected ? $t('page.collector.connected') : $t('page.collector.disconnected') }}
              </NTag>
            </NCard>
          </NGi>
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">可用账号</div>
                  <div class="mt-8px text-20px font-600">{{ loggedInAccountCount }} / {{ accounts.length }}</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-success-100 text-success dark:bg-success-900/30">
                  <SvgIcon icon="mdi:account-check-outline" class="text-24px" />
                </div>
              </div>
              <div class="mt-16px text-12px text-gray-500">已保存 Cookie 与浏览器指纹</div>
            </NCard>
          </NGi>
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">直播监控</div>
                  <div class="mt-8px text-20px font-600">{{ monitorStatus?.active_session_count || 0 }} 场</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-warning-100 text-warning dark:bg-warning-900/30">
                  <SvgIcon icon="mdi:radar" class="text-24px" />
                </div>
              </div>
              <NTag class="mt-16px" :type="monitorStatus?.running ? 'success' : 'default'" round size="small">
                {{ monitorStatus?.running ? '监控运行中' : '监控已停止' }}
              </NTag>
            </NCard>
          </NGi>
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">当前任务</div>
                  <div class="mt-8px text-20px font-600">{{ collectorStatus?.active_task_count || 0 }} 个</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-error-100 text-error dark:bg-error-900/30">
                  <SvgIcon icon="mdi:progress-clock" class="text-24px" />
                </div>
              </div>
              <div class="mt-16px text-12px text-gray-500">近 50 条日志中 {{ errorLogCount }} 条异常</div>
            </NCard>
          </NGi>
        </NGrid>

        <NGrid cols="1 l:3" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:2">
            <NCard :bordered="false" class="card-wrapper h-full" title="全量数据采集">
              <template #header-extra>
                <NTag v-if="collectAllLoading" type="warning" round size="small">任务执行中</NTag>
                <NTag v-else-if="hasAvailableAccount" type="success" round size="small">账号已就绪</NTag>
                <NTag v-else type="error" round size="small">请先扫码登录</NTag>
              </template>
              <div class="flex flex-col gap-16px">
                <NAlert type="info" :show-icon="true" :bordered="false">
                  自动发现账号下全部主播，依次同步直播场次、主播资料、指标、评论和观众画像。采集期间请勿删除当前账号。
                </NAlert>
                <div class="flex flex-wrap items-center gap-12px">
                  <NButton
                    type="primary"
                    size="large"
                    :loading="collectAllLoading"
                    :disabled="!hasAvailableAccount"
                    @click="handleCollectAll"
                  >
                    <template #icon><SvgIcon icon="mdi:database-arrow-down-outline" /></template>
                    {{ collectAllLoading ? '正在采集全部数据' : '开始全量采集' }}
                  </NButton>
                  <span class="text-12px text-gray-500">采集完成后自动刷新账号状态与最近日志</span>
                </div>

                <template v-if="collectAllResult">
                  <NDivider class="!my-0" />
                  <div class="flex flex-wrap items-center gap-8px">
                    <span class="font-600">最近一次采集结果</span>
                    <NTag :type="collectAllResult.collected_rooms > 0 ? 'success' : 'warning'" round size="small">
                      {{ collectAllResult.collected_rooms }}/{{ collectAllResult.total_rooms }} 个房间成功
                    </NTag>
                    <span v-if="collectAllResult.message" class="text-12px text-gray-500">
                      {{ collectAllResult.message }}
                    </span>
                  </div>
                  <NGrid cols="2 s:3 l:6" responsive="screen" :x-gap="12" :y-gap="12">
                    <NGi><NStatistic label="企业主播" :value="collectAllResult.enterprise_anchor_count || 0" /></NGi>
                    <NGi>
                      <NStatistic label="发现场次" :value="collectAllResult.enterprise_session_discovered_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="新增场次" :value="collectAllResult.enterprise_session_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="主播映射" :value="collectAllResult.anchor_profile_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="本次补详情" :value="collectAllResult.history_detail_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="剩余待补" :value="collectAllResult.history_detail_remaining_count || 0" />
                    </NGi>
                  </NGrid>
                  <NDataTable
                    v-if="collectAllResult.results?.length"
                    :columns="collectResultColumns"
                    :data="collectAllResult.results"
                    :row-key="getCollectResultRowKey"
                    :scroll-x="720"
                    :bordered="false"
                    size="small"
                  />
                </template>
              </div>
            </NCard>
          </NGi>

          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" title="实时监控">
              <template #header-extra>
                <NTag v-if="monitorStatus?.mock_mode" type="warning" round size="small">Mock 模式</NTag>
              </template>
              <div class="flex flex-col gap-16px">
                <div class="flex items-center justify-between gap-12px rounded-8px bg-gray-100 p-12px dark:bg-white/5">
                  <div>
                    <div class="font-600">{{ monitorStatus?.running ? '正在监听开播状态' : '监控服务未启动' }}</div>
                    <div class="mt-4px text-12px text-gray-500">
                      活跃场次 {{ monitorStatus?.active_session_count || 0 }} 场
                    </div>
                  </div>
                  <NBadge :type="monitorStatus?.running ? 'success' : 'default'" dot />
                </div>
                <NButton
                  block
                  :type="monitorStatus?.running ? 'warning' : 'primary'"
                  :loading="monitorLoading"
                  @click="monitorStatus?.running ? handleStopMonitor() : handleStartMonitor()"
                >
                  <template #icon>
                    <SvgIcon :icon="monitorStatus?.running ? 'mdi:stop-circle-outline' : 'mdi:play-circle-outline'" />
                  </template>
                  {{ monitorStatus?.running ? '停止直播监控' : '启动直播监控' }}
                </NButton>
                <NSpace v-if="monitorStatus?.mock_mode" :wrap="false">
                  <NButton class="flex-1" type="success" secondary @click="handleTriggerLive">模拟开播</NButton>
                  <NButton class="flex-1" type="error" secondary @click="handleTriggerEnd">模拟下播</NButton>
                </NSpace>
              </div>
            </NCard>
          </NGi>
        </NGrid>

        <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.accountList')">
          <template #header-extra>
            <NSpace>
              <NButton size="small" :loading="loading" @click="loadData">
                <template #icon><SvgIcon icon="mdi:refresh" /></template>
                {{ $t('common.refresh') }}
              </NButton>
              <NButton type="primary" size="small" @click="handleStartLogin">
                <template #icon><SvgIcon icon="mdi:qrcode-scan" /></template>
                {{ $t('page.collector.scanLogin') }}
              </NButton>
            </NSpace>
          </template>
          <NDataTable
            :loading="loading"
            :columns="accountColumns"
            :data="accounts"
            :row-key="getAccountRowKey"
            :scroll-x="800"
            :bordered="false"
            size="small"
            :empty-text="$t('page.collector.noAccount')"
          />
        </NCard>

        <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.logTitle')">
          <template #header-extra>
            <NButton size="small" :loading="loading" @click="loadData">
              <template #icon><SvgIcon icon="mdi:refresh" /></template>
              {{ $t('common.refresh') }}
            </NButton>
          </template>
          <NDataTable
            :loading="loading"
            :columns="logColumns"
            :data="logs"
            :row-key="getLogRowKey"
            :scroll-x="720"
            :bordered="false"
            size="small"
          />
        </NCard>
      </NSpace>
    </NSpin>

    <!-- 扫码登录弹窗 -->
    <NModal
      v-model:show="showQRModal"
      :mask-closable="false"
      preset="card"
      class="w-420px max-w-[calc(100vw-32px)]"
      @after-leave="closeQRModal"
    >
      <template #header>
        {{ $t('page.collector.scanLogin') }}
      </template>

      <div class="flex flex-col items-center py-12px">
        <NSteps class="mb-20px" size="small" :current="loginStatus === 'pending' ? 1 : 2" status="process">
          <NStep title="生成二维码" />
          <NStep title="抖音扫码确认" />
          <NStep title="保存登录状态" />
        </NSteps>
        <div v-if="qrImage" class="mb-16px size-240px rounded-12px bg-white p-10px shadow-sm ring-1 ring-gray-200">
          <img :src="`data:image/png;base64,${qrImage}`" class="size-full" alt="抖音扫码登录二维码" />
        </div>
        <div v-else class="mb-16px size-240px flex-center rounded-12px bg-gray-100 dark:bg-white/5">
          <NSpin :size="24" />
        </div>
        <NAlert
          class="w-full"
          :type="loginStatus === 'failed' || loginStatus === 'timeout' ? 'error' : 'info'"
          :show-icon="true"
        >
          {{ loginMessage || $t('page.collector.scanQrCode') }}
        </NAlert>
      </div>

      <template #footer>
        <NSpace justify="end">
          <NButton @click="closeQRModal">{{ $t('common.cancel') }}</NButton>
          <NButton
            v-if="loginStatus === 'failed' || loginStatus === 'timeout'"
            type="primary"
            @click="handleStartLogin"
          >
            重新生成二维码
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped></style>
