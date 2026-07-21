<script setup lang="ts">
/**
 * 话术内容面板
 *
 * 主内容区：分段阅读 / 全文阅读切换 + 搜索 + 分类筛选 + 片段列表。
 * 侧边栏：话术结构（分类进度条）+ 时间导航（虚拟列表）。
 *
 * 所有格式化函数从 helpers 直接导入，无需通过 props 传递。
 */
import { formatTime, getStatusLabel, getStatusType } from '@/utils/transcriptHelpers';
import type { CategoryStat } from '@/adapters/transcript-adapter';

defineOptions({ name: 'TranscriptContentPanel' });

defineProps<{
  /** 是否选中场次 */
  hasSession: boolean;
  /** 是否加载中 */
  loading: boolean;
  /** 当前视图模式 */
  viewMode: 'segments' | 'full';
  /** 搜索关键词 */
  searchKeyword: string;
  /** 分类筛选项 */
  categoryFilter: string | null;
  /** 分类下拉选项 */
  categoryOptions: Array<{ label: string; value: string }>;
  /** 全部片段 */
  segments: Api.Douyin.TranscriptSegment[];
  /** 筛选后片段 */
  filteredSegments: Api.Douyin.TranscriptSegment[];
  /** 可见片段（懒加载） */
  visibleSegments: Api.Douyin.TranscriptSegment[];
  /** 全文文本 */
  fullText: string;
  /** 已转写最大秒数 */
  transcribedSeconds: number;
  /** 分类统计 */
  categoryStats: CategoryStat[];
}>();

defineEmits<{
  'update:searchKeyword': [value: string];
  'update:categoryFilter': [value: string | null];
  'update:viewMode': [value: 'segments' | 'full'];
  /** 加载更多片段 */
  loadMore: [];
  /** 点击时间戳跳转到片段 */
  jumpToSegment: [segment: Api.Douyin.TranscriptSegment];
  /** 复制单个片段文本 */
  copySegment: [text: string];
  /** 点击分类跳转并筛选 */
  filterByCategory: [category: string];
}>();
</script>

<template>
  <NCard title="真实话术内容" :bordered="false" class="card-wrapper">
    <template #header-extra>
      <NRadioGroup :value="viewMode" size="small" @update:value="(val: string) => $emit('update:viewMode', val as 'segments' | 'full')">
        <NRadioButton value="segments">分段阅读</NRadioButton>
        <NRadioButton value="full">全文阅读</NRadioButton>
      </NRadioGroup>
    </template>

    <!-- 未选场次 -->
    <NEmpty v-if="!hasSession" description="请选择一个直播场次" class="py-70px" />

    <NSpin v-else :show="loading">
      <NGrid :x-gap="16" :y-gap="16" cols="1 xl:3" responsive="screen">
        <!-- 左侧：话术内容 -->
        <NGi span="1 xl:2">
          <!-- 分段阅读模式 -->
          <template v-if="viewMode === 'segments'">
            <!-- 搜索 + 分类筛选 -->
            <div class="mb-14px grid gap-10px sm:grid-cols-[minmax(0,1fr)_220px]">
              <NInput
                :value="searchKeyword"
                clearable
                placeholder="搜索真实话术内容"
                @update:value="(val: string) => $emit('update:searchKeyword', val)"
              >
                <template #prefix><SvgIcon icon="mdi:magnify" /></template>
              </NInput>
              <NSelect
                :value="categoryFilter || ''"
                :options="categoryOptions"
                @update:value="(val: string) => $emit('update:categoryFilter', val || null)"
              />
            </div>

            <!-- 筛选结果统计 -->
            <div class="mb-10px flex items-center justify-between text-12px text-gray-500">
              <span>显示 {{ filteredSegments.length }} / {{ segments.length }} 个真实片段</span>
              <span>已覆盖到 {{ formatTime(transcribedSeconds) }}</span>
            </div>

            <!-- 空结果 -->
            <NEmpty v-if="!filteredSegments.length" description="没有符合条件的话术片段" class="py-70px" />

            <!-- 片段列表 -->
            <div v-else class="transcript-list h-620px space-y-10px overflow-y-auto pr-6px lt-sm:h-500px">
              <article
                v-for="item in visibleSegments"
                :id="`transcript-segment-${item.id}`"
                :key="item.id"
                class="segment-card rounded-10px p-13px"
              >
                <div class="flex items-start gap-12px">
                  <!-- 时间戳按钮 -->
                  <button
                    type="button"
                    class="time-button shrink-0 rounded-7px px-8px py-4px font-mono text-12px font-700"
                    @click="$emit('jumpToSegment', item)"
                  >
                    {{ formatTime(item.segment_start) }}
                  </button>

                  <!-- 内容 -->
                  <div class="min-w-0 flex-1">
                    <p class="whitespace-pre-wrap text-14px leading-23px">
                      {{ item.text_content || '该片段没有识别出有效文字' }}
                    </p>
                    <div class="mt-8px flex flex-wrap items-center gap-8px">
                      <NTag size="tiny" :bordered="false">{{ item.segment_type || '未分类' }}</NTag>
                      <NTag size="tiny" :type="getStatusType(item.asr_status)" :bordered="false">
                        {{ getStatusLabel(item.asr_status) }}
                      </NTag>
                      <span class="text-11px text-gray-400">
                        {{ Math.max(0, item.segment_end - item.segment_start).toFixed(1) }} 秒
                      </span>
                      <span v-if="item.ai_score !== null" class="text-11px text-gray-400">
                        AI {{ item.ai_score.toFixed(1) }} 分
                      </span>
                    </div>
                  </div>

                  <!-- 复制按钮 -->
                  <NButton text class="shrink-0" @click="$emit('copySegment', item.text_content)">
                    <SvgIcon icon="mdi:content-copy" />
                  </NButton>
                </div>
              </article>

              <!-- 加载更多 -->
              <div v-if="visibleSegments.length < filteredSegments.length" class="py-6px text-center">
                <NButton secondary @click="$emit('loadMore')">
                  再加载 {{ Math.min(80, filteredSegments.length - visibleSegments.length) }} 段
                </NButton>
              </div>
            </div>
          </template>

          <!-- 全文阅读模式 -->
          <template v-else>
            <NEmpty v-if="!fullText && !segments.length" description="本场尚未生成完整话术" class="py-70px" />
            <NScrollbar v-else class="h-680px lt-sm:h-500px">
              <div class="full-text whitespace-pre-wrap rounded-10px p-18px text-14px leading-26px">
                {{
                  fullText ||
                    segments.map(item => `[${formatTime(item.segment_start)}] ${item.text_content}`).join('\n\n')
                }}
              </div>
            </NScrollbar>
          </template>
        </NGi>

        <!-- 右侧：话术结构 + 时间导航 -->
        <NGi span="1">
          <NSpace vertical :size="16">
            <!-- 话术结构 -->
            <NCard title="本场话术结构" :bordered="false" class="card-wrapper">
              <NEmpty v-if="!categoryStats.length" description="暂无可统计的真实分类" class="py-36px" />
              <div v-else class="space-y-13px">
                <button
                  v-for="item in categoryStats"
                  :key="item.name"
                  type="button"
                  class="w-full text-left"
                  @click="$emit('filterByCategory', item.name)"
                >
                  <div class="mb-5px flex items-center justify-between gap-10px text-12px">
                    <span class="truncate font-600">{{ item.name }}</span>
                    <span class="shrink-0 text-gray-400">{{ item.count }} 段</span>
                  </div>
                  <NProgress :percentage="item.percent" :show-indicator="false" :height="6" />
                </button>
              </div>
            </NCard>

            <!-- 时间导航 -->
            <NCard title="时间导航" :bordered="false" class="card-wrapper">
              <template #header-extra>
                <NTag size="small" :bordered="false">{{ segments.length }} 个节点</NTag>
              </template>
              <NEmpty v-if="!segments.length" description="暂无时间节点" class="py-36px" />
              <NVirtualList v-else :items="segments" :item-size="64" item-resizable class="h-370px pr-5px">
                <template #default="{ item }">
                  <button
                    type="button"
                    class="timeline-link mb-8px w-full flex items-start gap-8px rounded-8px p-8px text-left"
                    @click="$emit('jumpToSegment', item)"
                  >
                    <span class="shrink-0 font-mono text-11px font-700 text-primary">
                      {{ formatTime(item.segment_start) }}
                    </span>
                    <span class="line-clamp-2 text-12px leading-18px text-gray-500">
                      {{ item.text_content || '无有效文字' }}
                    </span>
                  </button>
                </template>
              </NVirtualList>
            </NCard>
          </NSpace>
        </NGi>
      </NGrid>
    </NSpin>
  </NCard>
</template>

<style scoped>
.segment-card,
.full-text {
  border: 1px solid var(--border-color, rgba(128, 128, 128, 0.14));
  background: rgba(128, 128, 128, 0.035);
}

.segment-card {
  scroll-margin-top: 24px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.segment-card:hover {
  border-color: rgba(32, 128, 240, 0.38);
  background: rgba(32, 128, 240, 0.045);
}

.time-button {
  background: rgba(var(--primary-color), 0.1);
  color: rgb(var(--primary-color));
}

.timeline-link:hover {
  background: rgba(32, 128, 240, 0.08);
}
</style>
