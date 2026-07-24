<script setup lang="ts">
import { h, onMounted, ref } from 'vue';
import { fetchDashboardSummary, fetchDashboardSummaryByAnchor } from '@/service/api/douyin';
import AnchorIdentity from '@/components/business/anchor-identity.vue';

defineOptions({ name: 'Home' });

// ── 日期筛选 ──
type DatePreset = 'today' | 'this_week' | 'last_week' | 'this_month' | 'last_month' | 'custom';
const datePreset = ref<DatePreset>('today');
const customRange = ref<[number, number] | null>(null);

/** 根据预设计算 start_date / end_date（YYYY-MM-DD 字符串） */
function getDateRange(): { start: string; end: string } {
  const today = new Date();
  const fmt = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  switch (datePreset.value) {
    case 'today': {
      const s = fmt(today);
      return { start: s, end: s };
    }
    case 'this_week': {
      const day = today.getDay();
      const monday = new Date(today);
      monday.setDate(today.getDate() - (day === 0 ? 6 : day - 1));
      return { start: fmt(monday), end: fmt(today) };
    }
    case 'last_week': {
      const day = today.getDay();
      const lastMonday = new Date(today);
      lastMonday.setDate(today.getDate() - (day === 0 ? 6 : day - 1) - 7);
      const lastSunday = new Date(lastMonday);
      lastSunday.setDate(lastMonday.getDate() + 6);
      return { start: fmt(lastMonday), end: fmt(lastSunday) };
    }
    case 'this_month': {
      const first = new Date(today.getFullYear(), today.getMonth(), 1);
      return { start: fmt(first), end: fmt(today) };
    }
    case 'last_month': {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const last = new Date(today.getFullYear(), today.getMonth(), 0);
      return { start: fmt(first), end: fmt(last) };
    }
    case 'custom': {
      if (customRange.value && customRange.value[0] && customRange.value[1]) {
        return { start: fmt(new Date(customRange.value[0])), end: fmt(new Date(customRange.value[1])) };
      }
      return { start: fmt(today), end: fmt(today) };
    }
    default:
      return { start: fmt(today), end: fmt(today) };
  }
}

	const presets: Array<{ label: string; key: DatePreset }> = [
  { label: '今天', key: 'today' },
  { label: '本周', key: 'this_week' },
  { label: '上周', key: 'last_week' },
  { label: '本月', key: 'this_month' },
  { label: '上月', key: 'last_month' }
];

function selectPreset(key: DatePreset) {
  datePreset.value = key;
  loadData();
}

function onCustomRangeChange(ts: [number, number] | null) {
  if (ts && ts[0] && ts[1]) {
    customRange.value = ts;
    datePreset.value = 'custom';
    loadData();
  }
}

// ── 数据加载 ──
const loading = ref(false);
const loadError = ref('');
const summary = ref<Api.Douyin.DashboardSummary | null>(null);
const anchorData = ref<Api.Douyin.AnchorSummaryResponse | null>(null);

async function loadData() {
  loading.value = true;
  loadError.value = '';
  const { start, end } = getDateRange();
  try {
    const [summaryRes, anchorRes] = await Promise.all([
      fetchDashboardSummary(start, end),
      fetchDashboardSummaryByAnchor(start, end)
    ]);
    if (summaryRes.data) summary.value = summaryRes.data;
    if (anchorRes.data) anchorData.value = anchorRes.data;
    if (summaryRes.error) loadError.value = `汇总数据加载失败: ${summaryRes.error.message || '未知错误'}`;
    if (anchorRes.error) loadError.value += ` 主播数据加载失败: ${anchorRes.error.message || '未知错误'}`;
  } catch (err) {
    loadError.value = (err as { message?: string }).message || '数据加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

// ── 格式化 ──
function fmtNum(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(n)) return '0';
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString('zh-CN');
}

function fmtMoney(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(n)) return '¥0';
  return '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── 主播表格列定义 ──
const anchorColumns = [
  {
    title: '主播',
    key: 'anchor_name',
    width: 180,
    render(row: Api.Douyin.AnchorSummaryItem) {
      return h(AnchorIdentity, {
        sessionId: row.anchor_avatar_session_id,
        avatarUrl: row.anchor_avatar_url,
        name: row.anchor_name,
        douyinId: row.douyin_id,
        size: 32
      });
    }
  },
  { title: '场次', key: 'session_count', width: 60, align: 'center' as const },
  { title: '观看', key: 'total_viewers', width: 80, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_viewers) },
  { title: '评论', key: 'total_comments', width: 70, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_comments) },
  { title: '私信', key: 'total_private_messages', width: 70, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_private_messages) },
  { title: '线索', key: 'total_leads', width: 70, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_leads) },
  { title: '新增粉丝', key: 'total_new_followers', width: 80, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_new_followers) },
  { title: '互动', key: 'total_interactions', width: 70, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtNum(row.total_interactions) },
  { title: '广告花费', key: 'total_ad_cost', width: 90, align: 'right' as const, render: (row: Api.Douyin.AnchorSummaryItem) => fmtMoney(row.total_ad_cost) }
];
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <!-- 日期筛选 + 刷新 -->
    <div class="flex flex-wrap items-center justify-between gap-12px">
      <div class="flex flex-wrap items-center gap-10px">
        <NButton
          v-for="p in presets"
          :key="p.key"
          size="small"
          :type="datePreset === p.key ? 'primary' : 'default'"
          :secondary="datePreset !== p.key"
          @click="selectPreset(p.key)"
        >
          {{ p.label }}
        </NButton>
        <NDatePicker
          type="daterange"
          :value="customRange"
          clearable
          placeholder="自定义日期范围"
          size="small"
          class="w-210px"
          @update:value="onCustomRangeChange"
        />
      </div>
      <NButton size="small" :loading="loading" @click="loadData">
        <template #icon><SvgIcon icon="mdi:refresh" /></template>
        刷新
      </NButton>
    </div>

    <!-- 错误提示 -->
    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      {{ loadError }}
      <NButton size="small" secondary :loading="loading" @click="loadData">重新加载</NButton>
    </NAlert>

    <NSpin :show="loading && !summary">
      <!-- 总体指标卡片 -->
      <NGrid v-if="summary" cols="2 s:4" responsive="screen" :x-gap="14" :y-gap="14">
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="总场次" :value="summary.session_count">
              <template #suffix>场</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              采集完成率 {{ summary.detail_completion_rate }}%
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="总观看" :value="fmtNum(summary.total_viewers)">
              <template #suffix>人</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              {{ summary.anchor_count }} 位主播 · {{ summary.live_session_count }} 场直播中
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="总评论" :value="fmtNum(summary.total_comments)">
              <template #suffix>条</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              高意向 {{ fmtNum(summary.high_intent_comment_count) }} 条
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="总私信 / 线索" :value="fmtNum(summary.total_private_messages)">
              <template #suffix>人</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              线索 {{ fmtNum(summary.total_leads) }} 条
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="广告总花费" :value="fmtMoney(summary.total_ad_cost)" />
            <div class="mt-6px text-11px text-gray-400">
              抖音推广消耗
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="平均线索成本" :value="fmtMoney(summary.average_lead_cost)" />
            <div class="mt-6px text-11px text-gray-400">
              广告花费 ÷ 线索数
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="待办复盘" :value="summary.open_review_action_count">
              <template #suffix>个</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              待处理或进行中
            </div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="card-wrapper">
            <NStatistic label="活跃主播" :value="summary.anchor_count">
              <template #suffix>位</template>
            </NStatistic>
            <div class="mt-6px text-11px text-gray-400">
              有真实场次记录
            </div>
          </NCard>
        </NGi>
      </NGrid>

      <!-- 空数据提示 -->
      <NEmpty
        v-else-if="!loading"
        description="该日期范围内暂无直播数据
通过数据采集页扫码登录后自动同步留资数据"
        class="py-40px"
      />

      <!-- 主播数据明细表 -->
      <NCard
        v-if="anchorData && anchorData.anchors.length"
        :bordered="false"
        size="small"
        class="card-wrapper"
        title="主播数据明细"
      >
        <template #header-extra>
          <NTag size="small" type="info" :bordered="false">{{ anchorData.anchors.length }} 位主播</NTag>
        </template>
        <NDataTable
          :columns="anchorColumns"
          :data="anchorData.anchors"
          :bordered="false"
          :single-line="false"
          size="small"
          striped
        />
      </NCard>
    </NSpin>
  </NSpace>
</template>
