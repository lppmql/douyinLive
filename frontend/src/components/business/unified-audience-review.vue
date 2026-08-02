<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { overrideAudienceAnalysis } from '@/service/api/douyin';
import { getCommentUserAvatarUrl } from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';

defineOptions({ name: 'UnifiedAudienceReview' });
const props = defineProps<{ review: Api.Douyin.UnifiedAiReview | null; sessionId?: number }>();
const emit = defineEmits<{ updated: [review: Api.Douyin.UnifiedAiReview] }>();
const message = useMessage();
const displayReview = ref(props.review);
const updatingId = ref<number | null>(null);
watch(() => props.review, value => (displayReview.value = value));

const summary = computed(() => displayReview.value?.summary || {});
const stageLabels: Record<string, string> = {
  preparing: '准备开店', selecting_location: '正在选址', comparing_brand: '比较品牌', opened_store: '已开店',
  suspected_paid: '疑似已交钱', unknown: '阶段未知'
};
const interactionLabels: Record<string, string> = {
  normal_inquiry: '正常咨询', high_intent: '高意向咨询', rational_question: '理性质疑', malicious: '恶意攻击',
  casual: '普通互动', information_insufficient: '信息不足'
};
const precisionLabels: Record<string, string> = {
  precision_new_lead: '精准新客', nurture: '可继续培育', existing_store: '存量开店用户', in_follow_up: '已进入跟进',
  existing_customer: '已成交客户', non_target: '非目标需求', industry_peer: '同行', malicious: '恶意用户',
  information_insufficient: '信息不足'
};
const responseLabels: Record<string, string> = {
  excellent: '优秀承接', effective: '有效回应', average: '回应一般', irrelevant: '答非所问', no_response: '未回应', unknown: '待判断'
};

async function copyValue(label: string, value: string) {
  await navigator.clipboard.writeText(value);
  message.success(`${label}已复制`);
}

async function applyOverride(user: Api.Douyin.UnifiedAiUserAnalysis, action: string) {
  if (!props.sessionId) return;
  const values =
    action === 'precision'
      ? { precision_status: 'precision_new_lead' as const, is_precision_lead: true }
      : action === 'opened'
        ? { business_stage: 'opened_store' as const, precision_status: 'existing_store' as const, is_precision_lead: false }
        : action === 'rational'
          ? { interaction_type: 'rational_question' as const }
          : action === 'malicious'
            ? { interaction_type: 'malicious' as const, precision_status: 'malicious' as const, is_precision_lead: false }
            : { clear: true };
  updatingId.value = user.id;
  try {
    const updatedReview = unwrapServiceData(
      await overrideAudienceAnalysis(props.sessionId, user.id, values),
      '人工确认结果为空'
    );
    displayReview.value = updatedReview;
    emit('updated', updatedReview);
    message.success(action === 'clear' ? '已恢复AI结果' : '人工结论已保存');
  } catch (error) {
    message.error((error as { message?: string }).message || '人工确认失败');
  } finally {
    updatingId.value = null;
  }
}
</script>

<template>
  <NEmpty v-if="!displayReview" description="尚未生成统一 AI 复盘" class="py-44px" />
  <NAlert v-else-if="displayReview.status !== 'completed'" :type="displayReview.status === 'failed' ? 'error' : 'warning'" show-icon>
    统一 AI 复盘状态：{{ displayReview.status }}{{ displayReview.error_message ? ` · ${displayReview.error_message}` : '' }}
  </NAlert>
  <NSpace v-else vertical :size="14">
    <NGrid cols="2 s:3 l:6" responsive="screen" :x-gap="10" :y-gap="10">
      <NGi><NStatistic label="精准新客" :value="summary.precision_new_lead_count || 0" /></NGi>
      <NGi><NStatistic label="精准未留资" :value="summary.precision_unconverted_count || 0" /></NGi>
      <NGi><NStatistic label="已开店" :value="summary.opened_store_count || 0" /></NGi>
      <NGi><NStatistic label="疑似联系过" :value="summary.suspected_contacted_count || 0" /></NGi>
      <NGi><NStatistic label="理性质疑" :value="summary.rational_question_count || 0" /></NGi>
      <NGi><NStatistic label="错失机会" :value="summary.missed_opportunity_count || 0" /></NGi>
    </NGrid>
    <NAlert type="info" :show-icon="false">
      {{ summary.summary || '分析已完成。' }}
      <div class="mt-4px text-11px opacity-70">业务事实优先于 AI；“已交钱/联系过拓展”在无业务接口证据时只标记为疑似。</div>
    </NAlert>
    <NGrid cols="1 l:3" responsive="screen" :x-gap="12" :y-gap="12">
      <NGi>
        <NCard size="small" title="做得好">
          <ul class="m-0 pl-18px"><li v-for="item in summary.strengths || []" :key="item" class="mb-5px">{{ item }}</li></ul>
        </NCard>
      </NGi>
      <NGi>
        <NCard size="small" title="主要问题">
          <ul class="m-0 pl-18px"><li v-for="item in summary.problems || []" :key="item" class="mb-5px">{{ item }}</li></ul>
        </NCard>
      </NGi>
      <NGi>
        <NCard size="small" title="下一场行动">
          <ul class="m-0 pl-18px"><li v-for="item in summary.next_actions || []" :key="item" class="mb-5px">{{ item }}</li></ul>
        </NCard>
      </NGi>
    </NGrid>
    <NCollapse>
      <NCollapseItem v-for="user in displayReview.users" :key="user.identity_key">
        <template #header>
          <div class="flex min-w-0 flex-wrap items-center gap-8px py-3px">
            <AnchorAvatar
              :src="user.user_avatar_comment_id && sessionId ? getCommentUserAvatarUrl(sessionId, user.user_avatar_comment_id) : ''"
              :name="user.user_nickname || '匿名用户'"
              :size="30"
            />
            <span class="font-600">{{ user.user_nickname || '匿名用户' }}</span>
            <NButton
              v-if="user.user_douyin_id"
              text
              type="primary"
              size="tiny"
              @click.stop="copyValue('抖音号', user.user_douyin_id)"
            >
              {{ user.douyin_id_type === 'short_id' ? '数字短号' : '抖音号' }} {{ user.user_douyin_id }} · 复制
            </NButton>
            <NTag :type="user.has_lead ? 'success' : 'default'" size="small" :bordered="false" round>
              {{ user.has_lead ? '已留资' : '未留资' }}
            </NTag>
          </div>
        </template>
        <div v-if="user.has_lead && user.lead_contacts.length" class="mb-10px rounded-8px bg-success-50 p-10px dark:bg-dark">
          <div class="mb-5px text-12px font-600 text-success">已留资联系方式</div>
          <div v-for="contact in user.lead_contacts" :key="`${contact.type}-${contact.value}`" class="flex items-center gap-8px text-12px">
            <span>{{ contact.type === 'phone' ? '手机号' : '微信号' }}：{{ contact.value }}</span>
            <NButton text type="primary" size="tiny" @click="copyValue(contact.type === 'phone' ? '手机号' : '微信号', contact.value)">复制</NButton>
          </div>
        </div>
        <div class="flex flex-wrap gap-6px">
          <NTag :type="user.is_precision_lead ? 'success' : 'default'">{{ precisionLabels[user.precision_status] }}</NTag>
          <NTag type="info">{{ stageLabels[user.business_stage] }}</NTag>
          <NTag :type="user.interaction_type === 'malicious' ? 'error' : user.interaction_type === 'rational_question' ? 'warning' : 'default'">
            {{ interactionLabels[user.interaction_type] }}
          </NTag>
          <NTag :type="user.missed_opportunity ? 'error' : 'success'">{{ responseLabels[user.host_response_status] }}</NTag>
          <NTag v-if="user.host_response_score !== null">回应 {{ user.host_response_score }} 分</NTag>
          <NTag>置信度 {{ Math.round(user.confidence * 100) }}%</NTag>
          <NTag v-if="user.manual_confirmed" type="success">人工已确认</NTag>
          <NDropdown
            v-if="sessionId"
            trigger="click"
            :options="[
              { label: '确认为精准新客', key: 'precision' },
              { label: '确认为已开店', key: 'opened' },
              { label: '确认为理性质疑', key: 'rational' },
              { label: '确认为恶意用户', key: 'malicious' },
              { label: '清除人工结论', key: 'clear' }
            ]"
            @select="key => applyOverride(user, String(key))"
          >
            <NButton size="tiny" :loading="updatingId === user.id">人工确认</NButton>
          </NDropdown>
        </div>
        <NAlert v-if="user.exclusion_reason" type="warning" :show-icon="false" class="mt-10px">排除原因：{{ user.exclusion_reason }}</NAlert>
        <div class="mt-10px rounded-8px bg-primary-50 p-10px dark:bg-dark">
          <div class="font-600">改进建议</div><div class="mt-4px">{{ user.recommendation }}</div>
          <template v-if="user.suggested_reply"><div class="mt-8px font-600">建议话术</div><div class="mt-4px">{{ user.suggested_reply }}</div></template>
        </div>
        <div v-if="user.evidence.length" class="mt-10px text-12px text-gray-500">
          <div v-for="item in user.evidence" :key="`${item.evidence_id}-${item.conclusion}`">
            {{ item.evidence_id }} · {{ item.conclusion }}：{{ item.reason }}
            <div v-if="item.text" class="ml-12px text-gray-400">原文：{{ item.text }}</div>
          </div>
        </div>
      </NCollapseItem>
    </NCollapse>
  </NSpace>
</template>
