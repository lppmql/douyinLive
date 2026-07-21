<!--
  顶部 4 张统计卡片 — 从 collector/index.vue 拆分
  纯展示组件，数据通过 props 传入，点击事件通过 emit 传出
-->
<script setup lang="ts">
import { NCard, NGi, NGrid, NButton, NTag } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'CollectorStatCards' });

defineProps<{
  /** 采集器连接状态 */
  collectorStatus: Api.Douyin.CollectorStatus | null;
  /** 账号总数 */
  accountsLength: number;
  /** 已登录账号数 */
  loggedInCount: number;
  /** 监控器状态 */
  monitorStatus: Api.Douyin.MonitorStatus | null;
  /** 上次成功采集后新增的异常日志数 */
  errorLogCount: number;
  /** 历史全部异常日志数 */
  historicalErrorCount: number;
}>();

const emit = defineEmits<{
  /** 点击可用账号卡片 → 滚动到账号表格 */
  (e: 'openAccounts'): void;
  /** 点击当前任务卡片 → 打开任务抽屉 */
  (e: 'openTasks'): void;
  /** 点击异常提示 → 筛选异常日志 */
  (e: 'openErrors'): void;
}>();
</script>

<template>
  <NGrid cols="1 s:2 l:4" responsive="screen" :x-gap="16" :y-gap="16">
    <!-- 卡片 1：采集服务连接状态 -->
    <NGi>
      <NCard :bordered="false" class="card-wrapper h-full" size="small">
        <div class="flex items-center justify-between gap-12px">
          <div>
            <div class="text-13px text-gray-500">采集服务</div>
            <div class="mt-8px text-20px font-600">
              {{ collectorStatus?.connected ? '连接正常' : '连接异常' }}
            </div>
          </div>
          <div class="size-44px flex-center rounded-12px bg-primary-100 text-primary dark:bg-primary-900/30">
            <SvgIcon icon="mdi:database-sync-outline" class="text-24px" />
          </div>
        </div>
        <NTag class="mt-16px" :type="collectorStatus?.connected ? 'success' : 'error'" round size="small">
          {{ collectorStatus?.connected ? $t('page.collector.connected') : $t('page.collector.disconnected') }}
        </NTag>
      </NCard>
    </NGi>

    <!-- 卡片 2：可用账号（可点击跳转到账号表格） -->
    <NGi>
      <NCard
        :bordered="false"
        class="business-clickable-card card-wrapper h-full"
        size="small"
        role="button"
        tabindex="0"
        @click="emit('openAccounts')"
        @keydown.enter="emit('openAccounts')"
      >
        <div class="flex items-center justify-between gap-12px">
          <div>
            <div class="text-13px text-gray-500">可用账号</div>
            <div class="mt-8px text-20px font-600">{{ loggedInCount }} / {{ accountsLength }}</div>
          </div>
          <div class="size-44px flex-center rounded-12px bg-success-100 text-success dark:bg-success-900/30">
            <SvgIcon icon="mdi:account-check-outline" class="text-24px" />
          </div>
        </div>
        <div class="mt-16px text-12px text-gray-500">已保存 Cookie 与浏览器指纹</div>
      </NCard>
    </NGi>

    <!-- 卡片 3：直播监控场次 -->
    <NGi>
      <NCard :bordered="false" class="card-wrapper h-full" size="small">
        <div class="flex items-center justify-between gap-12px">
          <div>
            <div class="text-13px text-gray-500">直播监控</div>
            <div class="mt-8px text-20px font-600">{{ monitorStatus?.active_session_count || 0 }} 场</div>
          </div>
          <div class="size-44px flex-center rounded-12px bg-warning-100 text-warning dark:bg-warning-900/30">
            <SvgIcon icon="mdi:radar" class="text-24px" />
          </div>
        </div>
        <NTag class="mt-16px" :type="monitorStatus?.running ? 'success' : 'default'" round size="small">
          {{ monitorStatus?.running ? '监控运行中' : '监控已停止' }}
        </NTag>
      </NCard>
    </NGi>

    <!-- 卡片 4：当前任务 + 异常提示（可点击跳转） -->
    <NGi>
      <NCard
        :bordered="false"
        class="business-clickable-card card-wrapper h-full"
        size="small"
        role="button"
        tabindex="0"
        @click="emit('openTasks')"
        @keydown.enter="emit('openTasks')"
      >
        <div class="flex items-center justify-between gap-12px">
          <div>
            <div class="text-13px text-gray-500">当前任务</div>
            <div class="mt-8px text-20px font-600">{{ collectorStatus?.active_task_count || 0 }} 个</div>
          </div>
          <div class="size-44px flex-center rounded-12px bg-error-100 text-error dark:bg-error-900/30">
            <SvgIcon icon="mdi:progress-clock" class="text-24px" />
          </div>
        </div>
        <NButton
          class="mt-12px"
          text
          :type="errorLogCount ? 'error' : 'success'"
          size="tiny"
          @click.stop="emit('openErrors')"
        >
          <template v-if="errorLogCount">成功采集后新增 {{ errorLogCount }} 条异常，点击查看</template>
          <template v-else-if="historicalErrorCount">当前无未恢复异常，点击查看历史</template>
          <template v-else>当前无采集异常</template>
        </NButton>
      </NCard>
    </NGi>
  </NGrid>
</template>
