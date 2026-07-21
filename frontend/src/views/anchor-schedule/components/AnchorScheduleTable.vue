<script setup lang="ts">
/**
 * 班次明细表格
 *
 * 展示排班数据表格，支持：
 * - 按主播筛选（通过 selectedAnchor 高亮标签）
 * - 横向滚动（最小宽度 1560px）
 * - 最大高度 560px 内滚动
 * - 斑马纹 + 小尺寸行
 */
import { NTag } from 'naive-ui';

defineOptions({ name: 'AnchorScheduleTable' });

defineProps<{
  /** 表格列定义（由适配器 createColumns 生成） */
  columns: NaiveUI.TableColumn<Api.Douyin.AnchorScheduleRow>[];
  /** 筛选后的行数据 */
  visibleRows: Api.Douyin.AnchorScheduleRow[];
  /** 是否加载中 */
  loading: boolean;
  /** 日期标签（用于表头标题） */
  selectedDateLabel: string;
  /** 当前选中的主播名（用于筛选标签展示） */
  selectedAnchor: string | null;
  /** 范围是否包含今天（影响刷新提示文案） */
  includesToday: boolean;
}>();

defineEmits<{
  /** 清除主播筛选 */
  clearAnchorFilter: [];
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper">
    <template #header>
      <div class="flex flex-wrap items-center gap-10px">
        <span class="text-16px font-700">{{ selectedDateLabel }} 班次明细</span>
        <NTag v-if="selectedAnchor" round closable @close="$emit('clearAnchorFilter')">
          {{ selectedAnchor }}
        </NTag>
      </div>
    </template>
    <template #header-extra>
      <span class="text-12px text-gray-400">
        {{ includesToday ? '范围包含今天，每 60 秒静默刷新' : '历史范围按需刷新' }}
      </span>
    </template>
    <div class="business-table-shell">
      <NDataTable
        :columns="columns"
        :data="visibleRows"
        :loading="loading"
        :row-key="row => `${row.schedule_date}-${row.id}`"
        :scroll-x="1560"
        :max-height="560"
        size="small"
        striped
      />
    </div>
  </NCard>
</template>
