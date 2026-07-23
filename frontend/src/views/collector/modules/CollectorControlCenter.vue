<script setup lang="ts">
import { NButton, NCard, NGi, NGrid, NSpace, NSwitch, NTag, NTooltip } from 'naive-ui';
import CollectorResourceOverview from './CollectorResourceOverview.vue';

defineOptions({ name: 'CollectorControlCenter' });

defineProps<{
  modules: Api.Douyin.CollectorModuleStatus[];
  activeTaskCount: number;
  queuedTaskCount: number;
  loadingKeys: Record<string, boolean>;
  hasAvailableAccount: boolean;
  refreshing: boolean;
  resourceUsage: Api.Douyin.ComputerResourceUsage | null;
}>();

const emit = defineEmits<{
  (e: 'toggle', module: Api.Douyin.CollectorModuleStatus, enabled: boolean): void;
  (e: 'run', module: Api.Douyin.CollectorModuleStatus): void;
  (e: 'openTasks'): void;
  (e: 'refresh'): void;
}>();

const moduleMeta: Record<
  Api.Douyin.CollectorModuleKey,
  { icon: string; description: string; accent: string }
> = {
  data_refresh: {
    icon: 'mdi:database-refresh-outline',
    description: '手动检查全部主播与全部场次，优先补齐缺失的真实数据',
    accent: '#2563eb'
  },
  monitor: {
    icon: 'mdi:access-point',
    description: '持续发现开播并采集指标、评论、画像与流地址',
    accent: '#059669'
  },
  asr: {
    icon: 'mdi:waveform',
    description: '持续监听最新场次，下播后优先低并发转写',
    accent: '#d97706'
  },
  ai_review: {
    icon: 'mdi:creation-outline',
    description: '持续从最新话术生成评分与复盘证据',
    accent: '#dc2626'
  },
  knowledge: {
    icon: 'mdi:book-open-page-variant-outline',
    description: '场次、评论、指标、画像、话术与手动复盘变化后自动入库',
    accent: '#0891b2'
  },
  dataease: {
    icon: 'mdi:chart-box-outline',
    description: '发现直播数据变化后自动增量同步到 DataEase 只读宽表',
    accent: '#4f46e5'
  }
};

function statusType(status: string): 'default' | 'info' | 'warning' | 'success' | 'error' {
  if (['running', 'processing'].includes(status)) return 'warning';
  if (['pending', 'queued'].includes(status)) return 'info';
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'error';
  return 'default';
}

function statusLabel(module: Api.Douyin.CollectorModuleStatus): string {
  if (module.mode === 'action') {
    if (module.processing_count) return '补齐刷新中';
    if (module.pending_count) return '等待接管浏览器';
    if (module.status === 'failed') return '上次失败';
    if (module.status === 'completed') return '上次已完成';
    return '按需执行';
  }
  if (module.mode === 'automatic') {
    return module.processing_count ? '后台处理中' : '后台自动';
  }
  if (!module.enabled) return '已彻底关闭';
  if (module.status === 'failed') return '等待恢复';
  if (module.processing_count) return '正在处理';
  if (module.status === 'pending') return '持续运行 · 排队中';
  return '持续运行';
}

function switchDisabled(module: Api.Douyin.CollectorModuleStatus): boolean {
  return module.mode !== 'service';
}

function switchHint(module: Api.Douyin.CollectorModuleStatus): string {
  if (module.mode === 'automatic') return '后台基础服务会自动处理新数据，无需手动开关';
  return module.enabled
    ? '关闭后不再创建新批次，当前任务安全停止，并释放该模块专属资源'
    : '开启后长期运行，优先处理正在直播和最新场次';
}

function intervalLabel(seconds: number): string {
  if (!seconds) return '按需检查';
  if (seconds < 60) return `每 ${seconds} 秒检查`;
  return `每 ${Math.round(seconds / 60)} 分钟检查`;
}

</script>

<template>
  <NCard :bordered="false" class="card-wrapper collector-control-card">
    <template #header>
      <div class="flex flex-wrap items-start justify-between gap-12px">
        <div>
          <div class="flex items-center gap-9px text-16px font-700">
            <SvgIcon icon="mdi:tune-variant" class="text-22px text-primary" />
            数据处理控制中心
          </div>
          <div class="mt-4px text-12px leading-20px text-gray-500">
            补齐刷新按需执行；直播监控与 ASR 可随时关闭；知识库和 DataEase 在后台自动增量同步。
          </div>
        </div>
        <NSpace align="center" wrap>
          <NTag :type="activeTaskCount ? 'warning' : 'success'" round :bordered="false">
            {{ activeTaskCount ? `${activeTaskCount} 个活跃任务` : '处理队列空闲' }}
          </NTag>
          <NButton size="small" secondary @click="emit('openTasks')">
            <template #icon><SvgIcon icon="mdi:format-list-checks" /></template>
            任务队列
            <span v-if="queuedTaskCount">（{{ queuedTaskCount }}）</span>
          </NButton>
          <NButton size="small" :loading="refreshing" @click="emit('refresh')">
            <template #icon><SvgIcon icon="mdi:refresh" /></template>
            刷新状态
          </NButton>
        </NSpace>
      </div>
    </template>

    <CollectorResourceOverview :usage="resourceUsage" />

    <NGrid cols="1 s:2 m:3 l:3" responsive="screen" :x-gap="12" :y-gap="12" item-responsive>
      <NGi v-for="module in modules" :key="module.key">
        <div
          class="collector-module"
          :class="{ 'collector-module--active': module.enabled }"
          :style="{ '--collector-accent': moduleMeta[module.key].accent }"
        >
          <div class="flex items-start justify-between gap-12px">
            <div class="min-w-0 flex items-start gap-10px">
              <div class="collector-module__icon">
                <SvgIcon :icon="moduleMeta[module.key].icon" class="text-20px" />
              </div>
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-7px">
                  <span class="font-600">{{ module.label }}</span>
                  <NTag size="tiny" :bordered="false" :type="statusType(module.status)">
                    {{ statusLabel(module) }}
                  </NTag>
                </div>
                <div class="mt-4px text-12px leading-18px text-gray-500">
                  {{ moduleMeta[module.key].description }}
                </div>
              </div>
            </div>
            <NTooltip v-if="module.mode === 'service'" trigger="hover">
              <template #trigger>
                <span>
                  <NSwitch
                    :value="module.enabled"
                    :loading="Boolean(loadingKeys[module.key])"
                    :disabled="switchDisabled(module)"
                    :aria-label="`${module.label}开关`"
                    @update:value="value => emit('toggle', module, value)"
                  />
                </span>
              </template>
              {{ switchHint(module) }}
            </NTooltip>
            <NTooltip v-else-if="module.mode === 'action'" trigger="hover">
              <template #trigger>
                <span>
                  <NButton
                    type="primary"
                    size="small"
                    :loading="Boolean(loadingKeys[module.key]) || Boolean(module.processing_count)"
                    :disabled="!hasAvailableAccount || Boolean(module.pending_count) || Boolean(module.processing_count)"
                    @click="emit('run', module)"
                  >
                    <template #icon><SvgIcon icon="mdi:database-sync-outline" /></template>
                    补齐刷新
                  </NButton>
                </span>
              </template>
              {{ hasAvailableAccount ? '刷新优先接管浏览器，完成后自动恢复实时监控' : '请先扫码登录可用采集账号' }}
            </NTooltip>
            <NTag v-else type="success" size="small" :bordered="false" round>
              <template #icon><SvgIcon icon="mdi:sync-circle" /></template>
              后台自动
            </NTag>
          </div>

          <div class="mt-13px flex flex-wrap items-center gap-x-14px gap-y-5px border-t border-gray-100 pt-10px text-12px dark:border-white/8">
            <span class="text-gray-400">{{ intervalLabel(module.interval_seconds) }}</span>
            <span v-if="module.pending_count" class="text-primary">待处理 {{ module.pending_count }}</span>
            <span v-if="module.processing_count" class="text-orange-500">处理中 {{ module.processing_count }}</span>
            <span v-if="module.failed_count" class="text-error">历史失败 {{ module.failed_count }}</span>
            <span v-if="!module.pending_count && !module.processing_count && !module.failed_count" class="text-gray-400">
              {{ module.mode === 'automatic' ? '自动监听数据变化' : module.enabled ? '正在监听新数据' : '不占用专属处理资源' }}
            </span>
          </div>
          <div class="mt-5px truncate text-11px text-gray-400" :title="module.summary">{{ module.summary }}</div>
        </div>
      </NGi>
    </NGrid>
  </NCard>
</template>

<style scoped>
.collector-control-card {
  overflow: hidden;
}

.collector-module {
  height: 100%;
  min-height: 144px;
  padding: 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  background: var(--n-color);
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
  display: flex;
  flex-direction: column;
}

.collector-module--active {
  border-color: color-mix(in srgb, var(--collector-accent) 48%, transparent);
  box-shadow: inset 3px 0 0 var(--collector-accent), 0 8px 24px rgb(15 23 42 / 5%);
}

.collector-module__icon {
  width: 36px;
  height: 36px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 10px;
  color: var(--collector-accent);
  background: color-mix(in srgb, var(--collector-accent) 11%, transparent);
}

@media (max-width: 640px) {
  .collector-module {
    min-height: auto;
  }
}
</style>
