<script setup lang="ts">
import { computed } from 'vue';
import {
  NAlert,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NList,
  NListItem,
  NModal,
  NTag,
  NThing
} from 'naive-ui';
import { getCollectorLogDetailEntries } from '../adapters/collector-log-adapter';
import { formatFullTime, getStageLabel } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorLogDetailModal' });

const props = defineProps<{
  visible: boolean;
  log: Api.Douyin.CollectorLog | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const detailEntries = computed(() => getCollectorLogDetailEntries(props.log));

function levelType(level: string): 'info' | 'warning' | 'error' {
  if (level === 'error') return 'error';
  if (level === 'warn') return 'warning';
  return 'info';
}
</script>

<template>
  <NModal
    :show="visible"
    preset="card"
    title="采集日志详情"
    class="w-760px max-w-[calc(100vw-24px)]"
    @update:show="value => emit('update:visible', value)"
  >
    <template v-if="log">
      <NDescriptions :column="2" bordered label-placement="top" size="small">
        <NDescriptionsItem label="日志与任务">日志 #{{ log.id }} · {{ log.task_id ? `任务 #${log.task_id}` : '系统任务' }}</NDescriptionsItem>
        <NDescriptionsItem label="产生时间">{{ formatFullTime(log.created_at) }}</NDescriptionsItem>
        <NDescriptionsItem label="主播">{{ log.anchor_name || '未关联主播' }}</NDescriptionsItem>
        <NDescriptionsItem label="直播场次">
          {{ log.session_title || (log.session_id ? `场次 #${log.session_id}` : '未关联场次') }}
        </NDescriptionsItem>
        <NDescriptionsItem label="房间 ID">{{ log.room_id_str || '-' }}</NDescriptionsItem>
        <NDescriptionsItem label="阶段与级别">
          <div class="flex flex-wrap gap-6px">
            <NTag size="small" :bordered="false">{{ getStageLabel(log.stage) }}</NTag>
            <NTag size="small" :bordered="false" :type="levelType(log.level)">
              {{ log.level === 'error' ? '异常' : log.level === 'warn' ? '警告' : '信息' }}
            </NTag>
          </div>
        </NDescriptionsItem>
      </NDescriptions>

      <NAlert class="mt-14px" :type="levelType(log.level)" :bordered="false" show-icon>
        {{ log.message || '该日志没有附加消息' }}
      </NAlert>

      <div class="mb-8px mt-16px flex items-center justify-between gap-8px">
        <span class="font-600">数据详情</span>
        <span class="text-12px text-gray-400">已自动隐藏 Cookie、Token、指纹和直播流地址</span>
      </div>
      <NList v-if="detailEntries.length" bordered hoverable class="max-h-380px overflow-auto">
        <NListItem v-for="entry in detailEntries" :key="entry.key">
          <NThing :title="entry.label">
            <template #description>
              <span class="break-all text-12px leading-20px text-gray-600 dark:text-gray-300">{{ entry.value }}</span>
            </template>
          </NThing>
        </NListItem>
      </NList>
      <NEmpty v-else class="py-28px" description="这条日志没有额外数据详情" />
    </template>
    <NEmpty v-else class="py-36px" description="未选择日志" />
  </NModal>
</template>
