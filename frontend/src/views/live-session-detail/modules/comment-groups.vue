<script setup lang="ts">
import { computed, ref, watch } from 'vue';

defineOptions({ name: 'LiveCommentGroups' });
const props = defineProps<{ comments: Api.Douyin.LiveComment[] }>();
const page = ref(1);
const pageSize = 12;

const groups = computed(() => {
  const map = new Map<string, { user: string; comments: Api.Douyin.LiveComment[] }>();
  props.comments.forEach(comment => {
    const user = comment.user_nickname?.trim() || '匿名用户';
    const identity = comment.user_sec_uid || user;
    const group = map.get(identity) || { user, comments: [] };
    group.comments.push(comment);
    map.set(identity, group);
  });
  return [...map.entries()].map(([identity, group]) => ({ identity, ...group })).sort((a, b) => b.comments.length - a.comments.length);
});
const visibleGroups = computed(() => groups.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch(() => props.comments, () => { page.value = 1; });
function formatTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'; }
</script>

<template>
  <div>
    <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
      <div class="text-13px text-gray-500">共 {{ groups.length }} 位用户，{{ comments.length }} 条评论</div>
      <NTag type="info" round :bordered="false">按评论用户聚合</NTag>
    </div>
    <NEmpty v-if="!groups.length" description="本场暂无已采集评论" class="py-60px" />
    <NGrid v-else :x-gap="14" :y-gap="14" cols="1 m:2 xl:3" responsive="screen">
      <NGi v-for="group in visibleGroups" :key="group.identity">
        <NCard size="small" class="comment-card h-full" :bordered="true">
          <template #header>
            <div class="flex min-w-0 items-center gap-10px"><NAvatar round :size="34">{{ group.user.slice(0, 1) }}</NAvatar><div class="min-w-0"><div class="truncate font-600">{{ group.user }}</div><div class="text-12px text-gray-400">{{ group.comments.length }} 条评论</div></div></div>
          </template>
          <NSpace vertical :size="10">
            <div v-for="comment in group.comments" :key="comment.id" class="comment-bubble rounded-8px p-10px">
              <div class="mb-4px text-12px text-gray-400">{{ formatTime(comment.comment_time) }}</div>
              <div class="break-words text-14px leading-22px">{{ comment.comment_content || '-' }}</div>
            </div>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>
    <div v-if="groups.length > pageSize" class="mt-16px flex justify-end"><NPagination v-model:page="page" :page-size="pageSize" :item-count="groups.length" show-quick-jumper /></div>
  </div>
</template>

<style scoped>
.comment-card { transition: border-color .2s ease, box-shadow .2s ease; }
.comment-card:hover { border-color: rgba(32, 128, 240, .45); box-shadow: 0 8px 24px rgba(31, 34, 37, .07); }
.comment-bubble { background: rgba(128, 128, 128, .08); }
</style>
