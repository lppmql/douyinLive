<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

defineOptions({ name: 'BusinessAppHelp' });

const route = useRoute();
const router = useRouter();
const visible = ref(false);

const workflow = [
  {
    title: '准备采集账号',
    description: '扫码登录并检查 Cookie 与浏览器指纹是否有效。',
    route: 'collector',
    icon: 'mdi:qrcode-scan'
  },
  {
    title: '刷新真实数据',
    description: '同步全部主播、直播场次、评论、画像和分钟指标。',
    route: 'collector',
    icon: 'mdi:database-sync-outline'
  },
  {
    title: '核对直播场次',
    description: '按主播或完整度筛选，进入详情检查评论和趋势。',
    route: 'live-sessions',
    icon: 'mdi:video-check-outline'
  },
  {
    title: '生成经营结论',
    description: '转写话术后执行 AI 分析，再同步到知识库。',
    route: 'transcripts',
    icon: 'mdi:chart-box-outline'
  }
] as const;

const currentHint = computed(() => {
  const hints: Record<string, string> = {
    home: '先看异常与运行任务，再决定进入采集或场次页面。',
    dashboard: '先核对场次详情完整率，再查看 DataEase 可视化。',
    collector: '首次使用先扫码并检查存活，再启动刷新采集或实时监控。',
    'live-sessions': '优先筛选“详情待补”，补齐后再进行分析。',
    transcripts: '先选择场次；没有音频或 m3u8 时无法生成真实话术。',
    analysis: '先选择已有话术的场次，避免分析结果缺少上下文。',
    knowledge: '先同步最近场次，再根据真实评论和话术进行检索。',
    'user-management': '仅管理员可维护用户；停用比删除更容易恢复。'
  };

  return hints[String(route.name)] || '从数据采集开始，按真实数据链路逐步操作。';
});

async function goTo(name: string) {
  visible.value = false;
  await router.push({ name });
}
</script>

<template>
  <NTooltip trigger="hover">
    <template #trigger>
      <ButtonIcon aria-label="新手帮助" @click="visible = true">
        <SvgIcon icon="mdi:help-circle-outline" />
      </ButtonIcon>
    </template>
    新手帮助
  </NTooltip>

  <NDrawer v-model:show="visible" width="min(440px, 94vw)" placement="right">
    <NDrawerContent title="新手帮助" closable>
      <NAlert type="info" :bordered="false" show-icon class="mb-18px">
        <template #header>当前页面怎么用</template>
        {{ currentHint }}
      </NAlert>

      <div class="mb-10px text-15px font-700">推荐操作顺序</div>
      <div class="flex flex-col gap-10px">
        <button
          v-for="(item, index) in workflow"
          :key="`${item.route}-${index}`"
          type="button"
          class="guide-step business-focus-ring business-active-press w-full flex items-start gap-12px rounded-10px border border-gray-200 bg-transparent p-12px text-left dark:border-white/10"
          @click="goTo(item.route)"
        >
          <div class="size-38px flex-center shrink-0 rounded-10px bg-primary-100 text-primary dark:bg-primary-900/30">
            <SvgIcon :icon="item.icon" class="text-20px" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-8px">
              <NTag round size="tiny" :bordered="false" type="primary">{{ index + 1 }}</NTag>
              <span class="font-600">{{ item.title }}</span>
            </div>
            <div class="mt-4px text-12px leading-19px text-gray-500">{{ item.description }}</div>
          </div>
          <SvgIcon icon="mdi:chevron-right" class="mt-8px shrink-0 text-18px text-gray-400" />
        </button>
      </div>

      <NDivider />
      <NAlert type="warning" :bordered="false" show-icon>
        页面中的数量均来自真实数据库。发现大量 0 值时，应先到“数据采集”查看详情待补数和失败日志，而不是直接做 AI 分析。
      </NAlert>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.guide-step {
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    transform 0.2s ease;
}

.guide-step:hover {
  border-color: rgb(var(--primary-color));
  background: rgba(var(--primary-color), 0.06);
  transform: translateX(2px);
}
</style>
