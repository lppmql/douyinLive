<script setup lang="ts">
defineOptions({ name: 'ReviewActions' });
defineProps<{ actions: Api.Douyin.ReviewAction[]; updatingId: number | null }>();
const emit = defineEmits<{
  create: [];
  update: [action: Api.Douyin.ReviewAction, status: Api.Douyin.ReviewAction['status']];
}>();

function statusType(status: Api.Douyin.ReviewAction['status']) {
  if (status === 'verified') return 'success';
  if (status === 'completed') return 'info';
  if (status === 'in_progress') return 'warning';
  return 'default';
}
function statusLabel(status: Api.Douyin.ReviewAction['status']) {
  return { pending: '待开始', in_progress: '进行中', completed: '待验证', verified: '已验证' }[status];
}
function nextStatus(status: Api.Douyin.ReviewAction['status']): Api.Douyin.ReviewAction['status'] | null {
  return { pending: 'in_progress', in_progress: 'completed', completed: 'verified', verified: null }[status] as
    | Api.Douyin.ReviewAction['status']
    | null;
}
</script>

<template>
  <div>
    <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
      <div>
        <div class="text-15px font-700">复盘整改闭环</div>
        <div class="mt-3px text-12px text-gray-400">发现问题后明确负责人，并在下一场直播验证是否改善</div>
      </div>
      <NButton type="primary" secondary @click="emit('create')">新建整改任务</NButton>
    </div>
    <NEmpty v-if="!actions.length" description="暂无整改任务，可从复盘发现一键创建" class="py-50px" />
    <NGrid v-else :x-gap="12" :y-gap="12" cols="1 m:2 xl:3" responsive="screen">
      <NGi v-for="item in actions" :key="item.id">
        <NCard size="small" class="h-full" :bordered="true">
          <template #header>
            <div class="flex items-center gap-8px">
              <NTag size="small" :type="statusType(item.status)" :bordered="false">{{ statusLabel(item.status) }}</NTag>
              <NTag v-if="item.priority === 'high'" size="small" type="error">高优先级</NTag>
              <NTag v-else size="small">{{ item.priority === 'medium' ? '中优先级' : '低优先级' }}</NTag>
            </div>
          </template>
          <div class="text-14px font-700">{{ item.title }}</div>
          <div class="mt-7px min-h-42px text-12px leading-20px text-gray-500">{{ item.description || '暂无补充说明' }}</div>
          <NDescriptions :column="1" size="small" class="mt-10px">
            <NDescriptionsItem label="负责人">{{ item.owner_name || '待分配' }}</NDescriptionsItem>
            <NDescriptionsItem label="截止时间">{{ item.due_at ? item.due_at.slice(0, 16).replace('T', ' ') : '未设置' }}</NDescriptionsItem>
            <NDescriptionsItem v-if="item.verification_note" label="验证结果">{{ item.verification_note }}</NDescriptionsItem>
          </NDescriptions>
          <div v-if="nextStatus(item.status)" class="mt-12px flex justify-end">
            <NButton
              size="small"
              type="primary"
              :loading="updatingId === item.id"
              @click="emit('update', item, nextStatus(item.status)!)"
            >
              {{ item.status === 'completed' ? '确认已验证' : '推进状态' }}
            </NButton>
          </div>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>
