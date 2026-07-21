<!--
  实时监控卡片 — 从 collector/index.vue 拆分
  显示监控状态、启停按钮、Mock 模式控制
-->
<script setup lang="ts">
import { NCard, NButton, NTag, NBadge, NSpace, NAlert } from 'naive-ui';

defineOptions({ name: 'CollectorMonitorCard' });

defineProps<{
  /** 监控器运行状态 */
  monitorStatus: Api.Douyin.MonitorStatus | null;
  /** 监控操作加载中 */
  monitorLoading: boolean;
}>();

const emit = defineEmits<{
  /** 启动监控 */
  (e: 'start'): void;
  /** 停止监控 */
  (e: 'stop'): void;
  /** Mock 模式：模拟开播 */
  (e: 'triggerLive'): void;
  /** Mock 模式：模拟下播 */
  (e: 'triggerEnd'): void;
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper h-full" title="实时监控">
    <template #header-extra>
      <NSpace :size="8">
        <NTag v-if="monitorStatus?.paused_for_collection" type="warning" round size="small">
          刷新采集接管中
        </NTag>
        <NTag v-if="monitorStatus?.mock_mode" type="warning" round size="small">Mock 模式</NTag>
      </NSpace>
    </template>
    <div class="flex flex-col gap-16px">
      <NAlert type="info" :bordered="false" show-icon>
        适合长期开启：周期检查主播是否开播，开播后持续采集直播间指标和评论；刷新采集运行时会自动协调重复任务。
      </NAlert>
      <div class="flex items-center justify-between gap-12px rounded-8px bg-gray-100 p-12px dark:bg-white/5">
        <div>
          <div class="font-600">
            {{
              monitorStatus?.paused_for_collection
                ? '监控已开启，当前由刷新采集接管'
                : monitorStatus?.running
                  ? '正在监听开播状态'
                  : '监控服务未启动'
            }}
          </div>
          <div class="mt-4px text-12px text-gray-500">
            活跃场次 {{ monitorStatus?.active_session_count || 0 }} 场
          </div>
          <div v-if="monitorStatus?.last_error" class="mt-4px text-12px text-error">
            最近错误：{{ monitorStatus.last_error }}
          </div>
        </div>
        <NBadge :type="monitorStatus?.running ? 'success' : 'default'" dot>
          <span class="text-12px ml-4px">{{ monitorStatus?.running ? '运行中' : '已停止' }}</span>
        </NBadge>
      </div>
      <NButton
        block
        :type="monitorStatus?.running ? 'warning' : 'primary'"
        :loading="monitorLoading"
        @click="monitorStatus?.running ? emit('stop') : emit('start')"
      >
        <template #icon>
          <SvgIcon :icon="monitorStatus?.running ? 'mdi:stop-circle-outline' : 'mdi:play-circle-outline'" />
        </template>
        {{ monitorStatus?.running ? '停止直播监控' : '启动直播监控' }}
      </NButton>
      <NSpace v-if="monitorStatus?.mock_mode" :wrap="false">
        <NButton class="flex-1" type="success" secondary @click="emit('triggerLive')">模拟开播</NButton>
        <NButton class="flex-1" type="error" secondary @click="emit('triggerEnd')">模拟下播</NButton>
      </NSpace>
    </div>
  </NCard>
</template>
