<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { fetchProfileEnrichmentStatus, startSessionProfileEnrichment } from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';

defineOptions({ name: 'LiveConversionOverview' });
const props = defineProps<{
  sessionId: number;
  summary: Api.Douyin.ConversionSummary;
  hooks: Api.Douyin.HookEvent[];
  coverage: Api.Douyin.SessionDataCoverage;
}>();
const emit = defineEmits<{ refresh: [] }>();
const message = useMessage();
const enrichment = ref<Api.Douyin.CommentProfileEnrichmentStatus | null>(null);
const starting = ref(false);
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollFailures = 0;
const currentScope = computed(() => `session:${props.sessionId}`);
const enrichmentRunning = computed(() =>
  Boolean(
    enrichment.value?.scope === currentScope.value &&
    ['starting', 'running'].includes(enrichment.value.status)
  )
);

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(pollStatus, 2000);
}

async function pollStatus() {
  try {
    enrichment.value = unwrapServiceData(await fetchProfileEnrichmentStatus(), '未获取到资料补全状态');
    pollFailures = 0;
    if (enrichmentRunning.value) {
      schedulePoll();
    } else if (enrichment.value.scope === currentScope.value && enrichment.value.status === 'completed') {
      emit('refresh');
    }
  } catch {
    pollFailures += 1;
    if (pollFailures <= 3) {
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = setTimeout(pollStatus, 2000 * pollFailures);
    } else {
      enrichment.value = null;
    }
  }
}

async function startEnrichment() {
  if (starting.value) return;
  starting.value = true;
  try {
    enrichment.value = unwrapServiceData(
      await startSessionProfileEnrichment(props.sessionId),
      '后端没有返回资料补全任务状态'
    );
    message.success(enrichment.value.message || '评论用户资料补全已启动');
    schedulePoll();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '评论用户资料补全启动失败');
  } finally {
    starting.value = false;
  }
}

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer);
});
onMounted(pollStatus);
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="钩子与客资转化">
    <NAlert type="info" :show-icon="true" class="mb-16px">
      只有同主播60秒内同时出现抖音号和手机号/微信号才确认留资；抖音号只用于归属评论用户和直播场次。
    </NAlert>
    <NAlert v-if="coverage.analysis_truncated" type="warning" :show-icon="true" class="mb-16px">
      本场共采集 {{ coverage.comment_count }} 条评论；为保证页面性能，用户分析使用最近
      {{ coverage.analysis_comment_count }} 条样本，较早评论仍保留在数据库中。
    </NAlert>
    <NGrid :x-gap="12" :y-gap="12" cols="2 s:4 l:8" responsive="screen">
      <NGi><NStatistic label="下钩子次数" :value="summary.hook_count" /></NGi>
      <NGi><NStatistic label="有效钩子" :value="summary.effective_hook_count" /></NGi>
      <NGi><NStatistic label="强钩子" :value="summary.strong_hook_count || 0" /></NGi>
      <NGi><NStatistic label="待补完整" :value="summary.incomplete_hook_count || 0" /></NGi>
      <NGi><NStatistic label="本场客资" :value="summary.session_lead_count" /></NGi>
      <NGi><NStatistic label="时间窗关联客资" :value="summary.hook_window_lead_count" /></NGi>
      <NGi><NStatistic label="确认留资用户" :value="summary.exact_matched_user_count" /></NGi>
      <NGi><NStatistic :label="coverage.analysis_truncated ? '样本评论用户' : '评论用户'" :value="summary.comment_user_count" /></NGi>
    </NGrid>
    <NAlert type="success" :show-icon="true" class="mt-16px">
      {{ hooks.length ? `已将 ${hooks.length} 个钩子或铺垫节点合并到上方“统一时间轴”，可按“转化钩子”筛选并点击回看。` : '真实话术中暂未识别到钩子或钩子铺垫。' }}
    </NAlert>
    <NDivider title-placement="left">用户身份采集覆盖</NDivider>
    <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
      <div class="text-12px text-gray-500">
        使用独立资料 Cookie 与固定指纹低速补全，不占用企业后台采集账号。
      </div>
      <NButton
        size="small"
        type="primary"
        secondary
        :loading="starting || enrichmentRunning"
        @click="startEnrichment"
      >
        补全本场用户资料
      </NButton>
    </div>
    <NProgress
      v-if="enrichment && enrichment.scope === currentScope && enrichment.total > 0"
      class="mb-14px"
      type="line"
      :percentage="Math.round((enrichment.completed * 100) / enrichment.total)"
      :status="enrichment.status === 'failed' || enrichment.status === 'blocked' ? 'error' : 'default'"
      indicator-placement="inside"
      processing
    />
    <NGrid :x-gap="16" :y-gap="10" cols="1 s:2" responsive="screen">
      <NGi>
        <div class="mb-6px flex justify-between text-12px"><span>头像</span><span>{{ coverage.avatar_user_count }}/{{ coverage.comment_user_count }}</span></div>
        <NProgress type="line" :percentage="coverage.avatar_coverage_percent" :height="8" />
      </NGi>
      <NGi>
        <div class="mb-6px flex justify-between text-12px"><span>公开抖音号</span><span>{{ coverage.douyin_id_user_count }}/{{ coverage.comment_user_count }}</span></div>
        <NProgress type="line" :percentage="coverage.douyin_id_coverage_percent" :height="8" />
      </NGi>
    </NGrid>
    <div class="mt-10px text-12px text-gray-500">优先展示自定义抖音号，无自定义号时展示平台数字短号；不使用 sec_uid 冒充抖音号。</div>
  </NCard>
</template>
