<script setup lang="ts">
import { ref } from 'vue';
import { useMessage } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({
  name: 'Transcripts'
});

const message = useMessage();

/* ---------- Mock 数据 ---------- */
interface TranscriptSegment {
  id: number;
  timePoint: string;
  content: string;
  duration: number;
  score: number;
  label: string;
  labelType: 'success' | 'warning' | 'info' | 'error';
}

const segments = ref<TranscriptSegment[]>([
  { id: 1, timePoint: '00:00', content: '欢迎各位来到直播间，今天给大家带来几款超值的商品', duration: 15, score: 85, label: '开场', labelType: 'info' },
  { id: 2, timePoint: '00:15', content: '先给大家介绍一下今天的福利机制，下单即送赠品', duration: 20, score: 90, label: '福利介绍', labelType: 'success' },
  { id: 3, timePoint: '00:35', content: '有需要的宝宝可以扣1，我看看有多少人在', duration: 10, score: 75, label: '互动引导', labelType: 'warning' },
  { id: 4, timePoint: '00:45', content: '这款产品的特点是……（详细讲解产品功能）', duration: 60, score: 88, label: '产品讲解', labelType: 'success' },
  { id: 5, timePoint: '01:45', content: '现在下单可以享受限时优惠价，原价199现价只要99', duration: 25, score: 92, label: '促单', labelType: 'success' },
  { id: 6, timePoint: '02:10', content: '大家可以点击下方小黄车查看详情', duration: 8, score: 70, label: '留资引导', labelType: 'warning' },
  { id: 7, timePoint: '02:18', content: '感谢大家的支持，我们继续看下一款产品', duration: 12, score: 80, label: '过渡', labelType: 'info' }
]);

/* ---------- 时间轴数据 ---------- */
const timelineItems = segments.value.map(s => ({
  label: s.timePoint,
  content: s.content.slice(0, 20) + (s.content.length > 20 ? '...' : ''),
  score: s.score
}));

/* ---------- 复制全文 ---------- */
const fullText = segments.value.map(s => `[${s.timePoint}] ${s.content}`).join('\n');

function copyFullText() {
  navigator.clipboard.writeText(fullText).then(() => {
    message.success($t('page.transcripts.copySuccess'));
  }).catch(() => {
    // fallback
    const textarea = document.createElement('textarea');
    textarea.value = fullText;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    message.success($t('page.transcripts.copySuccess'));
  });
}

function getScoreType(score: number): 'success' | 'warning' | 'error' | 'info' {
  if (score >= 85) return 'success';
  if (score >= 70) return 'warning';
  return 'error';
}
</script>

<template>
  <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
    <!-- 分段列表 -->
    <NGi span="2">
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace justify="space-between" align="center">
            <NSpace>
              <SvgIcon icon="mdi:chat-text" class="text-22px" />
              <span class="text-16px font-bold">{{ $t('page.transcripts.title') }}</span>
            </NSpace>
            <NButton type="primary" size="small" @click="copyFullText">
              <template #icon>
                <SvgIcon icon="mdi:content-copy" />
              </template>
              {{ $t('page.transcripts.copyFullText') }}
            </NButton>
          </NSpace>
        </template>

        <NSpace vertical :size="12">
          <div
            v-for="item in segments"
            :key="item.id"
            class="flex items-start gap-16px rounded-8px bg-gray-50 dark:bg-dark-300 p-12px"
          >
            <div class="flex-shrink-0 w-50px text-13px text-gray-500 font-mono">
              {{ item.timePoint }}
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-14px leading-22px mb-6px">{{ item.content }}</p>
              <div class="flex items-center gap-8px">
                <NTag :type="item.labelType" size="tiny">{{ item.label }}</NTag>
                <span class="text-12px text-gray-400">{{ item.duration }}s</span>
              </div>
            </div>
            <div class="flex-shrink-0 text-center w-40px">
              <NTag :type="getScoreType(item.score)" size="small" round>
                {{ item.score }}
              </NTag>
            </div>
          </div>
        </NSpace>
      </NCard>
    </NGi>

    <!-- 时间轴 -->
    <NGi span="1">
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <span class="text-15px font-bold">{{ $t('page.transcripts.timeline') }}</span>
        </template>
        <div v-for="item in timelineItems" :key="item.label" class="mb-16px">
          <div class="flex items-start gap-8px">
            <div class="flex-shrink-0 w-45px text-12px text-gray-400 font-mono">{{ item.label }}</div>
            <div class="flex-1 min-w-0">
              <p class="text-13px">{{ item.content }}</p>
              <div class="mt-2px">
                <NProgress
                  type="line"
                  :percentage="item.score"
                  :height="4"
                  :border-radius="2"
                  indicator-placement="inside"
                />
              </div>
            </div>
          </div>
        </div>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped></style>
