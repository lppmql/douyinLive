<script setup lang="ts">
/**
 * 排班提醒抽屉
 *
 * 右侧滑出抽屉，展示所有排班提醒。
 * 每条提醒显示：主播名、场次编号、提醒消息、日期时间。
 * 点击可跳转到对应场次详情页。
 * 根据严重程度显示不同图标和背景色（error=红色, warning=黄色）。
 */
import dayjs from 'dayjs';
import { formatClock } from '@/utils/anchorScheduleHelpers';

defineOptions({ name: 'AnchorScheduleReminderDrawer' });

defineProps<{
  /** 抽屉是否可见 */
  visible: boolean;
  /** 提醒列表 */
  reminders: Api.Douyin.AnchorScheduleReminder[];
}>();

defineEmits<{
  'update:visible': [value: boolean];
  /** 点击提醒项跳转场次详情 */
  openSession: [sessionId: number | null];
}>();
</script>

<template>
  <NDrawer
    :show="visible"
    width="min(460px, 94vw)"
    placement="right"
    @update:show="(val: boolean) => $emit('update:visible', val)"
  >
    <NDrawerContent title="排班提醒" closable>
      <NEmpty v-if="!reminders.length" description="当前没有已到期异常" />
      <NList v-else hoverable clickable>
        <NListItem
          v-for="(item, index) in reminders"
          :key="`${item.anchor_name}-${item.session_index}-${index}`"
          @click="$emit('openSession', item.session_id)"
        >
          <template #prefix>
            <div
              class="size-36px flex-center rounded-10px"
              :class="item.severity === 'error' ? 'bg-error-50 text-error' : 'bg-warning-50 text-warning'"
            >
              <SvgIcon
                :icon="
                  item.type === 'missing'
                    ? 'mdi:calendar-alert'
                    : item.type === 'invalid'
                      ? 'mdi:close-octagon-outline'
                      : 'mdi:clock-alert-outline'
                "
              />
            </div>
          </template>
          <div class="font-600">
            {{ item.anchor_name }} ·
            {{ item.is_extra ? `加场 ${item.session_index}` : `第 ${item.session_index} 场` }}
          </div>
          <div class="mt-4px text-13px text-gray-500">{{ item.message }}</div>
          <div class="mt-5px text-11px text-gray-400">
            {{ item.is_extra ? '实际开播' : '计划开播' }} {{ dayjs(item.schedule_date).format('MM-DD') }}
            {{ formatClock(item.planned_start_time) }}
          </div>
        </NListItem>
      </NList>
    </NDrawerContent>
  </NDrawer>
</template>
