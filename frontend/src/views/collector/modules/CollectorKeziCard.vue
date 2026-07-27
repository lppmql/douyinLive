<script setup lang="ts">
import { NAlert, NButton, NCard, NGi, NGrid, NStatistic, NTag } from 'naive-ui';
import { formatFullTime } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorKeziCard' });

defineProps<{
  status: Api.Douyin.LeadSyncStatus | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (event: 'sync'): void;
}>();

function statusType(status?: string): 'default' | 'warning' | 'success' | 'error' {
  if (status === 'failed') return 'error';
  if (status === 'running') return 'warning';
  if (status === 'completed') return 'success';
  return 'default';
}

function statusLabel(status: Api.Douyin.LeadSyncStatus | null): string {
  if (!status?.configured) return '等待配置密钥';
  if (status.status === 'running') return '同步中';
  if (status.status === 'failed') return '上次失败';
  if (status.status === 'completed') return '同步正常';
  return '等待首次同步';
}
</script>

<template>
  <NCard :bordered="false" class="card-wrapper">
    <template #header>
      <div class="flex items-center gap-9px">
        <SvgIcon icon="mdi:account-arrow-down-outline" class="text-22px text-primary" />
        <span>抖音站内私信客资</span>
      </div>
    </template>
    <template #header-extra>
      <NTag :type="statusType(status?.status)" round :bordered="false">
        {{ statusLabel(status) }}
      </NTag>
    </template>

    <NAlert v-if="status && !status.configured" type="warning" :bordered="false" class="mb-14px">
      请在项目根目录 .env 配置 KEZI_API_KEY。密钥只由后端读取，不会发送到浏览器。
    </NAlert>
    <NAlert v-else-if="status?.last_error" type="error" :bordered="false" class="mb-14px">
      {{ status.last_error }}
    </NAlert>

    <NGrid cols="2 s:4" responsive="screen" :x-gap="12" :y-gap="12">
      <NGi><NStatistic label="累计同步" :value="status?.synced_count || 0" /></NGi>
      <NGi><NStatistic label="待归属" :value="status?.pending_count || 0" /></NGi>
      <NGi><NStatistic label="跳过重复" :value="status?.duplicate_count || 0" /></NGi>
      <NGi><NStatistic label="同步游标" :value="status?.last_external_id || 0" /></NGi>
    </NGrid>

    <div class="mt-14px flex flex-wrap items-center justify-between gap-12px border-t border-gray-100 pt-12px dark:border-white/8">
      <span class="text-12px text-gray-500">
        最后同步：{{ formatFullTime(status?.last_synced_at || null) }}；
        每 {{ status?.interval_seconds || 60 }} 秒自动检查新增客资
      </span>
      <NButton
        size="small"
        type="primary"
        :loading="loading"
        :disabled="!status?.configured || status?.status === 'running'"
        @click="emit('sync')"
      >
        <template #icon><SvgIcon icon="mdi:sync" /></template>
        立即同步
      </NButton>
    </div>
  </NCard>
</template>
