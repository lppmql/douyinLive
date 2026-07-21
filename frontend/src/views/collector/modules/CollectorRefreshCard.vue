<!--
  刷新数据采集卡片 — 从 collector/index.vue 拆分（最大的子组件）
  包含：步骤指示器、ASR 话术开关、采集按钮、任务进度条、采集结果统计和表格
-->
<script setup lang="ts">
import { h } from 'vue';
import {
  NCard, NGi, NGrid, NButton, NTag, NAlert, NSteps, NStep,
  NSwitch, NTooltip, NProgress, NDivider, NDataTable, NStatistic
} from 'naive-ui';
import { formatFullTime, getStageLabel } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorRefreshCard' });

defineProps<{
  /** 采集操作加载中 */
  collectAllLoading: boolean;
  /** 是否有已登录的可用账号 */
  hasAvailableAccount: boolean;
  /** 当前采集任务（用于展示进度） */
  currentCollectTask: Api.Douyin.CollectorTask | undefined;
  /** ASR 话术服务状态 */
  asrStatus: Api.Douyin.AsrControlStatus | null;
  /** ASR 开关操作加载中 */
  asrControlLoading: boolean;
  /** 采集按钮禁用原因文本 */
  collectDisabledReason: string;
  /** 最近一次采集完整结果 */
  collectAllResult: Api.Douyin.CollectAllResponse | null;
}>();

const emit = defineEmits<{
  /** 触发刷新数据采集 */
  (e: 'collectAll'): void;
  /** 切换 ASR 话术开关 */
  (e: 'toggleAsr', enabled: boolean): void;
}>();

/** 采集结果行 key */
function getCollectResultRowKey(row: Api.Douyin.CollectRoomResult) {
  return row.room_id;
}

/** 采集结果表格列定义（每个房间的采集情况） */
const collectResultColumns = [
  { title: '主播', key: 'anchor_name', minWidth: 140, ellipsis: { tooltip: true } },
  {
    title: '直播',
    key: 'is_live',
    width: 60,
    render(row: Api.Douyin.CollectRoomResult) {
      return row.is_live
        ? h(NTag, { type: 'success', size: 'small' }, { default: () => '直播中' })
        : h(NTag, { type: 'default', size: 'small' }, { default: () => '未开播' });
    }
  },
  { title: '指标数', key: 'metrics_count', width: 80 },
  { title: '评论数', key: 'comments_count', width: 80 },
  { title: '画像数', key: 'profiles_count', width: 80 },
  {
    title: '状态',
    key: 'error',
    minWidth: 160,
    render(row: Api.Douyin.CollectRoomResult) {
      return row.error
        ? h(NTag, { type: 'error', size: 'small' }, { default: () => row.error })
        : h(NTag, { type: 'success', size: 'small' }, { default: () => '成功' });
    }
  }
];

/** 采集进度中的子指标项 */
const progressSubItems = [
  { key: 'collected_session_count', label: '已发现场次' },
  { key: 'new_session_count', label: '新增场次' },
  { key: 'mapped_session_count', label: '主播映射' },
  { key: 'checked_detail_count', label: '已检查详情' },
  { key: 'refreshed_detail_count', label: '已补齐详情' },
  { key: 'failed_detail_count', label: '详情失败' },
  { key: 'remaining_detail_count', label: '剩余待补' }
] as const;
</script>

<template>
  <NCard :bordered="false" class="card-wrapper h-full" title="刷新数据采集">
    <template #header-extra>
      <NTag v-if="collectAllLoading" type="warning" round size="small">任务执行中</NTag>
      <NTag v-else-if="hasAvailableAccount" type="success" round size="small">账号已就绪</NTag>
      <NTag v-else type="error" round size="small">请先扫码登录</NTag>
    </template>

    <div class="flex flex-col gap-16px">
      <!-- 说明提示 -->
      <NAlert type="info" :show-icon="true" :bordered="false">
        重新发现账号下全部主播和直播场次，并补齐每场直播的主播资料、指标、评论和观众画像。可与实时监控同时开启，刷新期间由全量任务接管重复采集，完成后自动恢复监控。
      </NAlert>

      <!-- 步骤指示器 -->
      <NSteps
        size="small"
        :current="currentCollectTask?.status === 'running' ? 2 : currentCollectTask?.status === 'completed' ? 3 : 1"
        status="process"
        responsive="screen"
      >
        <NStep title="账号就绪" description="Cookie 与指纹有效" />
        <NStep title="发现与补齐" description="主播、场次和详情" />
        <NStep title="自动后处理" description="话术、AI复盘与知识库" />
      </NSteps>

      <!-- ASR 话术开关 -->
      <div class="flex flex-wrap items-center justify-between gap-12px rounded-10px bg-gray-100 p-12px dark:bg-white/5">
        <div class="flex items-center gap-12px">
          <div
            class="size-38px flex-center rounded-10px"
            :class="
              asrStatus?.enabled
                ? 'bg-success-100 text-success dark:bg-success-900/30'
                : 'bg-gray-200 text-gray-500 dark:bg-white/10'
            "
          >
            <SvgIcon icon="mdi:waveform" class="text-21px" />
          </div>
          <div>
            <div class="flex items-center gap-8px font-600">
              话术、AI 复盘与知识库
              <NTag :type="asrStatus?.enabled ? 'success' : 'default'" round size="small">
                {{ asrStatus?.enabled ? '已开启' : '已关闭' }}
              </NTag>
            </div>
            <div class="mt-3px text-12px text-gray-500">
              <template v-if="asrStatus?.enabled">
                话术排队 {{ asrStatus.queued_count }} · 话术处理中 {{ asrStatus.processing_count }} ·
                复盘处理中 {{ asrStatus.postprocess_processing_count }} · 已入库
                {{ asrStatus.postprocess_completed_count }}
                <span v-if="!asrStatus.queued_count && !asrStatus.processing_count">
                  · 当前空闲但仍占用模型内存，不使用时建议关闭
                </span>
              </template>
              <template v-else>服务已关闭；开启后按单并发继续完成话术、复盘与知识库队列</template>
            </div>
          </div>
        </div>
        <NSwitch
          :value="Boolean(asrStatus?.enabled)"
          :loading="asrControlLoading"
          @update:value="(val: boolean) => emit('toggleAsr', val)"
        >
          <template #checked>开启</template>
          <template #unchecked>关闭</template>
        </NSwitch>
      </div>

      <!-- 采集按钮 -->
      <div class="flex flex-wrap items-center gap-12px">
        <NTooltip :disabled="!collectDisabledReason">
          <template #trigger>
            <span>
              <NButton
                type="primary"
                size="large"
                :loading="collectAllLoading"
                :disabled="Boolean(collectDisabledReason)"
                @click="emit('collectAll')"
              >
                <template #icon><SvgIcon icon="mdi:database-arrow-down-outline" /></template>
                {{ collectAllLoading ? '正在刷新全部数据' : '刷新数据采集' }}
              </NButton>
            </span>
          </template>
          {{ collectDisabledReason }}
        </NTooltip>
        <span class="text-12px text-gray-500">采集完成后自动刷新账号状态与最近日志</span>
      </div>

      <!-- 当前任务进度（仅当有任务时显示） -->
      <div v-if="currentCollectTask" class="rounded-10px bg-primary-50 p-16px dark:bg-primary-900/15">
        <div class="mb-10px flex flex-wrap items-center justify-between gap-8px">
          <div>
            <div class="font-600">{{ getStageLabel(currentCollectTask.progress_stage) }}</div>
            <div class="mt-4px text-12px text-gray-500">
              {{ currentCollectTask.progress_message || '正在执行采集任务' }}
            </div>
          </div>
          <NTag
            :type="
              currentCollectTask.status === 'completed'
                ? 'success'
                : currentCollectTask.status === 'failed'
                  ? 'error'
                  : 'primary'
            "
            round
          >
            任务 #{{ currentCollectTask.id }} ·
            {{
              currentCollectTask.status === 'completed'
                ? '已完成'
                : currentCollectTask.status === 'failed'
                  ? '失败'
                  : '运行中'
            }}
          </NTag>
        </div>
        <NProgress
          type="line"
          :percentage="currentCollectTask.progress_percent || 0"
          indicator-placement="inside"
          :processing="currentCollectTask.status === 'running'"
        />
        <div class="mt-8px flex justify-between text-12px text-gray-500">
          <span>
            已完成 {{ currentCollectTask.progress_current || 0 }}
            <template v-if="currentCollectTask.progress_total">
              / {{ currentCollectTask.progress_total }}
            </template>
          </span>
          <span>
            {{
              currentCollectTask.status === 'running'
                ? '页面每 5 秒自动更新'
                : formatFullTime(currentCollectTask.completed_at)
            }}
          </span>
        </div>
        <!-- 进度子指标 -->
        <NGrid class="mt-12px" cols="2 s:4 l:8" responsive="screen" :x-gap="10" :y-gap="10">
          <NGi>
            <div class="rounded-8px bg-white/70 px-12px py-10px dark:bg-black/15">
              <div class="text-12px text-gray-500">已采集主播</div>
              <div class="mt-2px text-20px font-600">
                {{ currentCollectTask.collected_anchor_count || 0 }} 位
              </div>
            </div>
          </NGi>
          <NGi
            v-for="item in progressSubItems"
            :key="item.key"
          >
            <div class="rounded-8px bg-white/70 px-10px py-10px dark:bg-black/15">
              <div class="text-12px text-gray-500">{{ item.label }}</div>
              <div class="mt-2px text-18px font-600">
                {{ (currentCollectTask as any)[item.key] || 0 }} 场
              </div>
            </div>
          </NGi>
        </NGrid>
      </div>

      <!-- 最近一次采集结果 -->
      <template v-if="collectAllResult">
        <NDivider class="!my-0" />
        <div class="flex flex-wrap items-center gap-8px">
          <span class="font-600">最近一次采集结果</span>
          <NTag :type="collectAllResult.collected_rooms > 0 ? 'success' : 'warning'" round size="small">
            {{ collectAllResult.collected_rooms }}/{{ collectAllResult.total_rooms }} 个房间成功
          </NTag>
          <NTag :type="collectAllResult.dataease_failed_count ? 'warning' : 'success'" round size="small">
            DataEase 同步 {{ collectAllResult.dataease_synced_count || 0 }} 场
          </NTag>
          <NTag type="info" round size="small">
            话术新增排队 {{ collectAllResult.asr_queued_count || 0 }} 场 · 当前
            {{ collectAllResult.asr_active_count || 0 }}/{{ collectAllResult.asr_queue_capacity || 5 }}
          </NTag>
          <NTag :type="collectAllResult.postprocess_failed_count ? 'warning' : 'success'" round size="small">
            AI复盘入库 {{ collectAllResult.postprocess_completed_count || 0 }} 场 · 待处理
            {{ collectAllResult.postprocess_pending_count || 0 }} 场
          </NTag>
          <span v-if="collectAllResult.message" class="text-12px text-gray-500">
            {{ collectAllResult.message }}
          </span>
        </div>
        <NGrid cols="2 s:4 l:8" responsive="screen" :x-gap="12" :y-gap="12">
          <NGi><NStatistic label="企业主播" :value="collectAllResult.enterprise_anchor_count || 0" /></NGi>
          <NGi>
            <NStatistic label="发现场次" :value="collectAllResult.enterprise_session_discovered_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="新增场次" :value="collectAllResult.enterprise_session_synced_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="主播映射" :value="collectAllResult.anchor_profile_synced_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="已检查详情" :value="collectAllResult.history_detail_checked_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="已补齐详情" :value="collectAllResult.history_detail_synced_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="本次失败" :value="collectAllResult.history_detail_failed_count || 0" />
          </NGi>
          <NGi>
            <NStatistic label="待重试详情" :value="collectAllResult.history_detail_remaining_count || 0" />
          </NGi>
        </NGrid>
        <NDataTable
          v-if="collectAllResult.results?.length"
          :columns="collectResultColumns"
          :data="collectAllResult.results"
          :row-key="getCollectResultRowKey"
          :scroll-x="720"
          :bordered="false"
          size="small"
        />
      </template>
    </div>
  </NCard>
</template>
