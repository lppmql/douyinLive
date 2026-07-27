<script setup lang="ts">
import { NButton, NTag, NTooltip } from 'naive-ui';
import { formatFullTime } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorLeadSyncCard' });

defineProps<{
  status: Api.Douyin.LeadSyncStatus | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (event: 'sync'): void;
}>();

function statusType(status: Api.Douyin.LeadSyncStatus | null): 'default' | 'info' | 'warning' | 'success' | 'error' {
  if (!status?.configured) return 'default';
  if (status.status === 'failed') return 'error';
  if (status.status === 'running') return 'warning';
  if (status.status === 'completed') return 'success';
  return 'info';
}

function statusLabel(status: Api.Douyin.LeadSyncStatus | null): string {
  if (!status?.configured) return '等待配置';
  if (status.status === 'running') return '后台处理中';
  if (status.status === 'failed') return '等待恢复';
  if (status.status === 'completed') return '后台自动';
  return '等待首次同步';
}

function intervalLabel(seconds?: number): string {
  const safeSeconds = seconds || 60;
  if (safeSeconds < 60) return `每 ${safeSeconds} 秒检查`;
  return `每 ${Math.round(safeSeconds / 60)} 分钟检查`;
}

function summaryText(status: Api.Douyin.LeadSyncStatus | null): string {
  if (!status?.configured) return '请在项目根目录 .env 配置 KEZI_API_KEY，密钥不会发送到浏览器';
  if (status.last_error) return status.last_error;
  if (status.last_synced_at) return `最近同步 ${formatFullTime(status.last_synced_at)}`;
  return '正在监听新的抖音站内私信客资';
}
</script>

<template>
  <div class="lead-sync-module" :class="{ 'lead-sync-module--active': status?.configured }">
    <div class="flex items-start justify-between gap-10px">
      <div class="min-w-0 flex items-start gap-10px">
        <div class="lead-sync-module__icon">
          <SvgIcon icon="mdi:account-sync-outline" class="text-20px" />
        </div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-7px">
            <span class="font-600">客资同步</span>
            <NTag size="tiny" :bordered="false" :type="statusType(status)">
              {{ statusLabel(status) }}
            </NTag>
          </div>
          <div class="mt-4px text-12px leading-18px text-gray-500">
            <span class="lead-sync-flow">抖音私信 → 客资库</span>
            增量写入并匹配真实直播场次
          </div>
        </div>
      </div>

      <NTooltip trigger="hover">
        <template #trigger>
          <span>
            <NButton
              circle
              secondary
              size="small"
              :loading="loading || status?.status === 'running'"
              :disabled="!status?.configured || status?.status === 'running'"
              aria-label="立即同步客资"
              @click="emit('sync')"
            >
              <template #icon><SvgIcon icon="mdi:sync" /></template>
            </NButton>
          </span>
        </template>
        {{ status?.configured ? '立即检查并同步新增客资' : '请先在根目录 .env 配置 KEZI_API_KEY' }}
      </NTooltip>
    </div>

    <div class="mt-13px flex flex-wrap items-center gap-x-12px gap-y-5px border-t border-gray-100 pt-10px text-12px dark:border-white/8">
      <span class="text-gray-400">{{ intervalLabel(status?.interval_seconds) }}</span>
      <span class="text-primary">累计 {{ status?.synced_count || 0 }}</span>
      <span v-if="status?.pending_count" class="text-orange-500">待归属 {{ status.pending_count }}</span>
      <span v-if="status?.duplicate_count" class="text-gray-400">跳过重复 {{ status.duplicate_count }}</span>
      <span class="text-gray-400">游标 {{ status?.last_external_id || 0 }}</span>
    </div>

    <div
      class="mt-5px truncate text-11px"
      :class="status?.last_error ? 'text-error' : 'text-gray-400'"
      :title="summaryText(status)"
    >
      {{ summaryText(status) }}
    </div>
  </div>
</template>

<style scoped>
.lead-sync-module {
  --lead-sync-accent: #7c3aed;

  display: flex;
  height: 100%;
  min-height: 144px;
  flex-direction: column;
  padding: 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  background: var(--n-color);
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.lead-sync-module--active {
  border-color: color-mix(in srgb, var(--lead-sync-accent) 48%, transparent);
  box-shadow:
    inset 3px 0 0 var(--lead-sync-accent),
    0 8px 24px rgb(15 23 42 / 5%);
}

.lead-sync-module__icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 10px;
  color: var(--lead-sync-accent);
  background: color-mix(in srgb, var(--lead-sync-accent) 11%, transparent);
}

.lead-sync-flow {
  margin-right: 5px;
  color: var(--lead-sync-accent);
  font-weight: 600;
}

@media (max-width: 640px) {
  .lead-sync-module {
    min-height: auto;
  }
}
</style>
