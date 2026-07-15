<script setup lang="ts">
import { computed, ref } from 'vue';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ReviewFindings' });
const props = defineProps<{
  findings: Api.Douyin.ReviewFinding[];
  alerts: Api.Douyin.ReviewLiveAlert[];
  generating: boolean;
}>();
const emit = defineEmits<{
  generate: [];
  createAction: [finding: Api.Douyin.ReviewFinding];
  updateStatus: [finding: Api.Douyin.ReviewFinding, status: Api.Douyin.ReviewFinding['status']];
}>();
const reviewStore = useReviewStore();
const severity = ref<'all' | Api.Douyin.ReviewFinding['severity']>('all');
const category = ref<string | null>(null);

const categoryOptions = computed(() =>
  [...new Set(props.findings.map(item => item.category))].map(item => ({ label: item, value: item }))
);
const visibleFindings = computed(() =>
  props.findings.filter(
    item =>
      item.status !== 'dismissed' &&
      (severity.value === 'all' || item.severity === severity.value) &&
      (!category.value || item.category === category.value)
  )
);
function severityType(value: Api.Douyin.ReviewFinding['severity']) {
  if (value === 'critical') return 'error';
  if (value === 'warning') return 'warning';
  return 'info';
}
function formatSecond(value: number | null) {
  if (value === null) return '场次级';
  const minutes = Math.floor(value / 60);
  return `${String(minutes).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="mb-12px flex flex-wrap items-center justify-between gap-8px">
      <div>
        <div class="text-15px font-700">证据化复盘发现</div>
        <div class="mt-3px text-12px text-gray-400">只展示真实指标、评论或话术能够支撑的结论</div>
      </div>
      <NButton size="small" type="primary" :loading="generating" @click="emit('generate')">重新生成复盘</NButton>
    </div>

    <NSpace v-if="alerts.length" vertical :size="8" class="mb-12px">
      <NAlert
        v-for="item in alerts"
        :key="item.key"
        :type="item.severity === 'critical' ? 'error' : item.severity === 'warning' ? 'warning' : 'info'"
        :title="item.title"
        :bordered="false"
        show-icon
        class="cursor-pointer"
        @click="item.start_seconds !== null && reviewStore.seekTo(item.start_seconds)"
      >
        {{ item.description }}
      </NAlert>
    </NSpace>

    <div class="mb-10px grid grid-cols-2 gap-8px">
      <NSelect
        v-model:value="severity"
        size="small"
        :options="[
          { label: '全部等级', value: 'all' },
          { label: '重点复核', value: 'critical' },
          { label: '机会/风险', value: 'warning' },
          { label: '一般观察', value: 'info' }
        ]"
      />
      <NSelect v-model:value="category" size="small" clearable placeholder="全部分类" :options="categoryOptions" />
    </div>

    <NEmpty v-if="!visibleFindings.length" description="尚未生成结构化复盘，点击上方按钮开始" class="py-60px" />
    <div v-else class="finding-list min-h-0 flex-1 space-y-9px overflow-auto pr-4px">
      <div
        v-for="item in visibleFindings"
        :key="item.id"
        class="finding-card cursor-pointer rounded-10px border border-gray-200/70 p-11px dark:border-gray-700"
        @click="item.start_seconds !== null && reviewStore.seekTo(item.start_seconds, item.id)"
      >
        <div class="flex items-start justify-between gap-8px">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-6px">
              <NTag size="tiny" :type="severityType(item.severity)" :bordered="false">{{ item.category }}</NTag>
              <span class="text-12px text-gray-400">{{ formatSecond(item.start_seconds) }}</span>
              <span class="text-11px text-gray-400">可信度 {{ Math.round(item.confidence * 100) }}%</span>
            </div>
            <div class="mt-7px text-14px font-700">{{ item.title }}</div>
          </div>
          <NDropdown
            trigger="click"
            :options="[
              { label: '确认问题', key: 'confirmed' },
              { label: '标记已解决', key: 'resolved' },
              { label: '忽略本条', key: 'dismissed' }
            ]"
            @select="value => emit('updateStatus', item, value)"
          >
            <NButton text size="tiny" @click.stop><SvgIcon icon="mdi:dots-horizontal" /></NButton>
          </NDropdown>
        </div>
        <div v-if="item.evidence_text" class="evidence-box mt-8px rounded-7px px-9px py-7px text-12px leading-19px">
          {{ item.evidence_text }}
        </div>
        <div v-if="item.description" class="mt-7px text-12px leading-19px text-gray-500">{{ item.description }}</div>
        <div class="mt-9px flex justify-end">
          <NButton size="tiny" secondary type="primary" @click.stop="emit('createAction', item)">创建整改任务</NButton>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.finding-list {
  max-height: 690px;
}
.finding-card {
  background: rgba(128, 128, 128, 0.025);
  transition: 0.2s ease;
}
.finding-card:hover {
  border-color: rgba(32, 128, 240, 0.5);
  transform: translateY(-1px);
}
.evidence-box {
  border-left: 3px solid rgba(32, 128, 240, 0.7);
  background: rgba(32, 128, 240, 0.07);
}
</style>
