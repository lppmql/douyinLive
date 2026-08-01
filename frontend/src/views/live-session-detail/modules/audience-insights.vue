<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';
import { getCommentUserAvatarUrl } from '@/service/api/douyin';

defineOptions({ name: 'AudienceConversionInsights' });
const props = defineProps<{ sessionId: number; users: Api.Douyin.AudienceUserInsight[] }>();
const message = useMessage();
const filter = ref<'all' | 'lead' | 'high' | 'unconverted'>('all');
const page = ref(1);
const pageSize = 12;
const filtered = computed(() =>
  props.users.filter(user => {
    if (filter.value === 'lead') return user.has_lead;
    if (filter.value === 'high') return user.intent_level === 'high';
    if (filter.value === 'unconverted') return !user.has_lead;
    return true;
  })
);
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch([() => props.users, filter], () => (page.value = 1));

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
}
async function copyValue(label: string, value: string | null) {
  if (!value) return;
  await navigator.clipboard.writeText(value);
  message.success(`${label}已复制`);
}
</script>

<template>
  <div>
    <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
      <NRadioGroup v-model:value="filter" size="small">
        <NRadioButton value="all">全部 {{ users.length }}</NRadioButton>
        <NRadioButton value="lead">已留资</NRadioButton>
        <NRadioButton value="high">高意向</NRadioButton>
        <NRadioButton value="unconverted">未留资</NRadioButton>
      </NRadioGroup>
      <span class="text-12px text-gray-500">同主播60秒内“抖音号 + 手机号/微信号”配对成功才算已留资</span>
    </div>
    <NEmpty v-if="!visible.length" description="当前筛选条件下暂无评论用户" class="py-50px" />
    <NGrid v-else :x-gap="14" :y-gap="14" cols="1 m:2 xl:3" responsive="screen">
      <NGi v-for="user in visible" :key="user.identity_key">
        <NCard size="small" class="h-full" :bordered="true">
          <template #header>
            <div class="flex min-w-0 items-center gap-10px">
              <AnchorAvatar
                :size="40"
                :name="user.user_nickname || '匿名用户'"
                :src="user.user_avatar_comment_id ? getCommentUserAvatarUrl(sessionId, user.user_avatar_comment_id) : ''"
              />
              <div class="min-w-0 flex-1">
                <div class="truncate font-600">{{ user.user_nickname || '匿名用户' }}</div>
                <NButton
                  v-if="user.user_douyin_id"
                  text
                  size="tiny"
                  class="max-w-full text-11px text-gray-400"
                  @click.stop="copyValue('抖音号', user.user_douyin_id)"
                >
                  <span class="truncate">
                    {{ user.douyin_id_type === 'short_id' ? '数字短号' : '抖音号' }} {{ user.user_douyin_id }} · 点击复制
                  </span>
                </NButton>
                <div v-else class="truncate text-11px text-gray-400">抖音号等待补全</div>
              </div>
              <NTag :type="user.has_lead ? 'success' : 'default'" :bordered="false" round>
                {{ user.has_lead ? '已留资' : '未留资' }}
              </NTag>
            </div>
          </template>
          <NSpace vertical :size="10">
            <div v-if="user.has_lead && user.lead_contacts.length" class="rounded-8px bg-success-50 p-10px dark:bg-dark">
              <div class="mb-6px text-12px font-600 text-success">已留资联系方式</div>
              <div v-for="contact in user.lead_contacts" :key="`${contact.type}-${contact.value}`" class="flex flex-wrap items-center justify-between gap-8px py-3px text-12px">
                <span>{{ contact.type === 'phone' ? '手机号' : '微信号' }}：{{ contact.value }}</span>
                <NButton text size="tiny" type="primary" @click.stop="copyValue(contact.type === 'phone' ? '手机号' : '微信号', contact.value)">
                  复制
                </NButton>
              </div>
            </div>
            <div class="flex flex-wrap gap-6px">
              <NTag :type="user.intent_level === 'high' ? 'error' : user.intent_level === 'medium' ? 'warning' : 'default'" size="small" :bordered="false">
                {{ user.intent_level === 'high' ? '高意向' : user.intent_level === 'medium' ? '中意向' : '待识别' }}
              </NTag>
              <NTag v-for="topic in user.intent_topics" :key="topic" size="small" type="info" :bordered="false">{{ topic }}</NTag>
              <NTag size="small" :type="user.host_responded ? 'success' : 'warning'" :bordered="false">
                {{ user.host_responded ? '主播有同主题承接' : '未检测到主播承接' }}
              </NTag>
              <NTag size="small" :type="user.hook_action_detected ? 'success' : 'default'" :bordered="false">
                {{ user.hook_action_detected ? '附近有钩子动作' : '附近无钩子动作' }}
              </NTag>
            </div>
            <NCollapse>
              <NCollapseItem :title="`${user.comment_count} 条真实评论`">
                <div v-for="comment in user.comments" :key="comment.id" class="mb-8px rounded-8px bg-gray-50 p-9px dark:bg-dark">
                  <div class="text-11px text-gray-400">{{ formatTime(comment.comment_time) }}</div>
                  <div class="mt-3px break-words text-13px">{{ comment.content }}</div>
                </div>
              </NCollapseItem>
            </NCollapse>
            <NAlert v-if="user.host_evidence" type="success" :show-icon="false">
              主播同主题原话：{{ user.host_evidence }}
            </NAlert>
            <div class="rounded-8px bg-primary-50 p-10px text-13px leading-21px dark:bg-dark">
              <div class="mb-3px font-600">转化建议</div>
              {{ user.recommendation }}
            </div>
            <div v-if="user.has_lead" class="text-11px text-gray-400">
              同主播1分钟配对 · {{ user.lead_match_method === 'short_id_exact' ? '数字短号归属' : '自定义抖音号归属' }}
              · 完成时间 {{ formatTime(user.lead_time) }}
            </div>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>
    <div v-if="filtered.length > pageSize" class="mt-16px flex justify-end">
      <NPagination v-model:page="page" :page-size="pageSize" :item-count="filtered.length" show-quick-jumper />
    </div>
  </div>
</template>
