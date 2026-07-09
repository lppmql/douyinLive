<script setup lang="ts">
import { ref, h } from 'vue';
import { NTag } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({
  name: 'Knowledge'
});

/* ---------- Mock 数据 ---------- */
interface KnowledgeItem {
  id: number;
  title: string;
  category: string;
  categoryType: 'success' | 'warning' | 'info' | 'primary';
  summary: string;
  source: string;
  time: string;
}

const knowledgeItems = ref<KnowledgeItem[]>([
  { id: 1, title: '高转化开场话术模板', category: $t('page.knowledge.transcript'), categoryType: 'success', summary: '通过互动式开场提升留存率的5种话术模板', source: '2026-07-08 场次A', time: '2026-07-08' },
  { id: 2, title: '留资引导最佳实践', category: $t('page.knowledge.transcript'), categoryType: 'success', summary: '分析12场高留资直播间的共性话术模式', source: 'AI 分析', time: '2026-07-09' },
  { id: 3, title: '互动率下降原因分析', category: $t('page.knowledge.analysis'), categoryType: 'info', summary: '对比低互动场次发现：缺少提问式引导是主要原因', source: 'AI 分析', time: '2026-07-07' },
  { id: 4, title: '商品展示环节优化方案', category: $t('page.knowledge.suggestion'), categoryType: 'warning', summary: '建议在商品展示时配合限时优惠话术，提升转化率', source: 'AI 分析', time: '2026-07-06' },
  { id: 5, title: '主播话术评分Top10', category: $t('page.knowledge.analysis'), categoryType: 'info', summary: '综合评分最高的10段话术及其场景分析', source: '系统', time: '2026-07-05' },
  { id: 6, title: '流量低谷期应对策略', category: $t('page.knowledge.suggestion'), categoryType: 'warning', summary: '在线人数下降时应采取的3种互动策略', source: 'AI 分析', time: '2026-07-04' }
]);

const activeTab = ref('all');

const filteredItems = ref(knowledgeItems.value);

function onTabChange(name: string | number) {
  const tabName = name as string;
  if (tabName === 'all') {
    filteredItems.value = knowledgeItems.value;
  } else {
    filteredItems.value = knowledgeItems.value.filter(item => {
      if (tabName === 'transcript') return item.category === $t('page.knowledge.transcript');
      if (tabName === 'analysis') return item.category === $t('page.knowledge.analysis');
      if (tabName === 'suggestion') return item.category === $t('page.knowledge.suggestion');
      return true;
    });
  }
}

/* ---------- 表格列 ---------- */
const columns = [
  { title: () => $t('page.knowledge.itemTitle'), key: 'title' },
  {
    title: () => $t('page.knowledge.category'),
    key: 'category',
    width: 100,
    render(row: KnowledgeItem) {
      return h(NTag, { type: row.categoryType, size: 'small' }, { default: () => row.category });
    }
  },
  { title: () => $t('page.knowledge.summary'), key: 'summary', ellipsis: { tooltip: true } },
  { title: () => $t('page.knowledge.source'), key: 'source', width: 120 },
  { title: () => $t('page.knowledge.time'), key: 'time', width: 100 }
];
</script>

<template>
  <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
    <NGi span="2">
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:book-open-variant" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.knowledge.title') }}</span>
          </NSpace>
        </template>

        <NTabs :value="activeTab" type="line" animated @update:value="onTabChange">
          <NTabPane name="all" :tab="$t('page.knowledge.all')" />
          <NTabPane name="transcript" :tab="$t('page.knowledge.transcript')" />
          <NTabPane name="analysis" :tab="$t('page.knowledge.analysis')" />
          <NTabPane name="suggestion" :tab="$t('page.knowledge.suggestion')" />
        </NTabs>

        <NDataTable
          :columns="columns"
          :data="filteredItems"
          :bordered="false"
          :single-line="false"
          size="small"
          striped
        />
      </NCard>
    </NGi>

    <!-- 聊天窗占位 -->
    <NGi span="1">
      <NCard :bordered="false" class="card-wrapper" style="position: sticky; top: 16px">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:chat-question" class="text-18px" />
            <span class="text-15px font-bold">AI 助手</span>
          </NSpace>
        </template>
        <div class="flex flex-col items-center justify-center py-40px text-center">
          <SvgIcon icon="mdi:robot-outline" class="text-64px text-gray-300 dark:text-gray-600 mb-16px" />
          <p class="text-14px text-gray-500 mb-8px">{{ $t('page.knowledge.chatPlaceholder') }}</p>
          <p class="text-12px text-gray-400">{{ $t('page.knowledge.chatDesc') }}</p>
        </div>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped></style>
