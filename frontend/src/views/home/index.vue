<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import BusinessPageHeader from '@/components/business/page-header.vue';
import { fetchCollectorStatus, fetchCollectorTasks, fetchMonitorStatus } from '@/service/api/douyin';

defineOptions({ name: 'Home' });

const router = useRouter();
const loading = ref(false);
const collectorStatus = ref<Api.Douyin.CollectorStatus | null>(null);
const monitorStatus = ref<Api.Douyin.MonitorStatus | null>(null);
const tasks = ref<Api.Douyin.CollectorTask[]>([]);

const runningTaskCount = computed(() => tasks.value.filter(task => task.status === 'running').length);
const failedTaskCount = computed(() => tasks.value.filter(task => task.status === 'failed').length);

const quickActions = [
  {
    title: '刷新数据采集',
    description: '同步全部主播、直播场次、评论与画像',
    icon: 'mdi:database-sync-outline',
    route: 'collector'
  },
  {
    title: '直播场次',
    description: '查询全部场次并查看详细经营数据',
    icon: 'mdi:video-outline',
    route: 'live-sessions'
  },
  {
    title: '话术转写',
    description: '管理 ASR 任务和查看话术时间轴',
    icon: 'mdi:text-box-outline',
    route: 'transcripts'
  },
  { title: 'AI 分析', description: '生成评分、问题诊断和优化建议', icon: 'mdi:chart-box-outline', route: 'analysis' }
] as const;

async function loadWorkspace() {
  loading.value = true;
  const [collector, monitor, taskList] = await Promise.allSettled([
    fetchCollectorStatus(),
    fetchMonitorStatus(),
    fetchCollectorTasks()
  ]);
  if (collector.status === 'fulfilled' && collector.value.data) collectorStatus.value = collector.value.data;
  if (monitor.status === 'fulfilled' && monitor.value.data) monitorStatus.value = monitor.value.data;
  if (taskList.status === 'fulfilled' && taskList.value.data) tasks.value = taskList.value.data;
  loading.value = false;
}

onMounted(loadWorkspace);
</script>

<template>
  <NSpace vertical :size="16">
    <BusinessPageHeader
      title="欢迎回来，今天从真实数据开始"
      description="先确认采集账号和运行任务，再进入场次、话术与分析页面。所有数量都来自当前数据库。"
      icon="mdi:view-dashboard-outline"
      eyebrow="直播经营工作台"
      :status="failedTaskCount ? `${failedTaskCount} 个历史失败任务` : '系统状态已汇总'"
      :status-type="failedTaskCount ? 'error' : 'success'"
    >
      <template #actions>
        <NButton type="primary" :loading="loading" @click="loadWorkspace">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新工作台
        </NButton>
      </template>
      <div class="flex flex-wrap items-center gap-x-18px gap-y-6px text-12px text-gray-500">
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-1-circle-outline" />
          扫码并检查账号
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-2-circle-outline" />
          刷新或实时采集
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-3-circle-outline" />
          核对场次详情
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-4-circle-outline" />
          转写与 AI 分析
        </span>
      </div>
    </BusinessPageHeader>

    <NGrid cols="1 s:2 l:4" responsive="screen" :x-gap="16" :y-gap="16">
      <NGi>
        <NCard
          :bordered="false"
          class="card-wrapper h-full cursor-pointer"
          size="small"
          @click="router.push({ name: 'collector' })"
        >
          <NStatistic label="采集服务" :value="collectorStatus?.connected ? '正常' : '异常'" />
          <NTag class="mt-12px" :type="collectorStatus?.connected ? 'success' : 'error'" round size="small">
            {{ collectorStatus?.connected ? '服务连接正常' : '等待采集账号' }}
          </NTag>
        </NCard>
      </NGi>
      <NGi>
        <NCard
          :bordered="false"
          class="card-wrapper h-full cursor-pointer"
          size="small"
          @click="router.push({ name: 'collector' })"
        >
          <NStatistic
            label="可用采集账号"
            :value="collectorStatus?.default_account?.login_status === 'logged_in' ? 1 : 0"
          >
            <template #suffix>个</template>
          </NStatistic>
          <div class="mt-12px text-12px text-gray-500">Cookie 与浏览器指纹已持久化</div>
        </NCard>
      </NGi>
      <NGi>
        <NCard
          :bordered="false"
          class="card-wrapper h-full cursor-pointer"
          size="small"
          @click="router.push({ name: 'collector' })"
        >
          <NStatistic label="实时监控" :value="monitorStatus?.active_session_count || 0">
            <template #suffix>场</template>
          </NStatistic>
          <NTag class="mt-12px" :type="monitorStatus?.running ? 'success' : 'default'" round size="small">
            {{ monitorStatus?.running ? '监控运行中' : '监控已停止' }}
          </NTag>
        </NCard>
      </NGi>
      <NGi>
        <NCard
          :bordered="false"
          class="card-wrapper h-full cursor-pointer"
          size="small"
          @click="router.push({ name: 'collector' })"
        >
          <NStatistic label="运行任务" :value="runningTaskCount">
            <template #suffix>个</template>
          </NStatistic>
          <div class="mt-12px text-12px" :class="failedTaskCount ? 'text-error' : 'text-gray-500'">
            历史失败 {{ failedTaskCount }} 个
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NCard :bordered="false" class="card-wrapper" title="常用功能">
      <NGrid cols="1 s:2 l:4" responsive="screen" :x-gap="12" :y-gap="12">
        <NGi v-for="item in quickActions" :key="item.route">
          <button
            type="button"
            class="h-full w-full flex items-start gap-12px rounded-10px border border-gray-200 bg-transparent p-14px text-left transition hover:border-primary hover:bg-primary-50 dark:border-white/10 dark:hover:bg-primary-900/15"
            @click="router.push({ name: item.route })"
          >
            <div class="size-40px flex-center shrink-0 rounded-10px bg-primary-100 text-primary dark:bg-primary-900/30">
              <SvgIcon :icon="item.icon" class="text-21px" />
            </div>
            <div class="min-w-0">
              <div class="font-600">{{ item.title }}</div>
              <div class="mt-4px text-12px leading-18px text-gray-500">{{ item.description }}</div>
            </div>
          </button>
        </NGi>
      </NGrid>
    </NCard>
  </NSpace>
</template>
