<script setup lang="ts">
import { computed } from 'vue';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ScriptAssetsPanel' });
const props = defineProps<{
  assets: Api.Douyin.ScriptAsset[];
  coverage: Api.Douyin.DomainCoverageItem[];
  findings: Api.Douyin.ReviewFinding[];
  updatingId: number | null;
}>();
const emit = defineEmits<{ updateAsset: [asset: Api.Douyin.ScriptAsset, status: Api.Douyin.ScriptAsset['status']] }>();
const reviewStore = useReviewStore();
const complianceFindings = computed(() =>
  props.findings.filter(item => item.category === '合规' && item.status !== 'dismissed')
);
</script>

<template>
  <NSpace vertical :size="18">
    <div>
      <div class="text-15px font-700">零食店避坑知识覆盖</div>
      <div class="mt-3px text-12px text-gray-400">从真实ASR话术判断本场讲到了哪些内容，不用标题猜测</div>
      <NGrid :x-gap="10" :y-gap="10" cols="2 s:4 l:8" responsive="screen" class="mt-12px">
        <NGi v-for="item in coverage" :key="item.category">
          <button
            type="button"
            class="w-full rounded-9px border p-10px text-left"
            :class="
              item.covered
                ? 'border-success-200 bg-success-50 dark:bg-success-900/15'
                : 'border-gray-200 dark:border-gray-700'
            "
            @click="item.first_seconds !== null && reviewStore.seekTo(item.first_seconds)"
          >
            <div class="flex items-center gap-8px text-12px font-700">
              <SvgIcon
                :icon="item.covered ? 'mdi:check-circle-outline' : 'mdi:circle-outline'"
                :class="item.covered ? 'text-success' : 'text-gray-400'"
              />
              {{ item.category }}
            </div>
            <div class="mt-5px text-11px text-gray-400">
              {{ item.covered ? `${item.segment_count} 个片段` : '本场未识别' }}
            </div>
          </button>
        </NGi>
      </NGrid>
    </div>

    <NDivider class="!my-0" />

    <div>
      <div class="mb-10px flex items-center justify-between gap-10px">
        <div>
          <div class="text-15px font-700">优秀话术资产</div>
          <div class="mt-3px text-12px text-gray-400">在复盘时间轴点击“收录话术”，保留真实来源和时间</div>
        </div>
        <NTag type="info" round :bordered="false">{{ assets.length }} 条</NTag>
      </div>
      <NEmpty v-if="!assets.length" description="尚未收录本场话术" class="py-36px" />
      <NList v-else bordered>
        <NListItem v-for="item in assets" :key="item.id">
          <NThing :title="item.title" :description="item.performance_note || '尚未补充效果说明'">
            <template #header-extra>
              <NTag size="small" :type="item.status === 'approved' ? 'success' : 'default'">
                {{ item.status === 'approved' ? '已入选' : item.status === 'archived' ? '已归档' : '候选' }}
              </NTag>
            </template>
            <template #description>
              <div class="mt-6px line-clamp-2 text-12px leading-19px text-gray-500">{{ item.content }}</div>
            </template>
            <template #footer>
              <div class="mt-8px flex items-center justify-between gap-8px text-11px text-gray-400">
                <button type="button" @click="reviewStore.seekTo(item.start_seconds || 0)">
                  {{ item.category }} · 跳到原话
                </button>
                <NButton
                  v-if="item.status === 'candidate'"
                  size="tiny"
                  secondary
                  type="success"
                  :loading="updatingId === item.id"
                  @click="emit('updateAsset', item, 'approved')"
                >
                  通过复核
                </NButton>
              </div>
            </template>
          </NThing>
        </NListItem>
      </NList>
    </div>

    <NDivider class="!my-0" />

    <div>
      <div class="text-15px font-700">合规风险筛查</div>
      <div class="mt-3px text-12px text-gray-400">命中结果只用于人工复核，不直接判定违规</div>
      <NEmpty v-if="!complianceFindings.length" description="本场真实话术暂未命中已启用规则" class="py-36px" />
      <NSpace v-else vertical :size="9" class="mt-11px">
        <NAlert
          v-for="item in complianceFindings"
          :key="item.id"
          :type="item.severity === 'critical' ? 'error' : 'warning'"
          :title="item.title"
          show-icon
          class="cursor-pointer"
          @click="item.start_seconds !== null && reviewStore.seekTo(item.start_seconds, item.id)"
        >
          <div>{{ item.evidence_text }}</div>
          <div class="mt-5px text-12px opacity-80">{{ item.description }}</div>
        </NAlert>
      </NSpace>
    </div>
  </NSpace>
</template>
