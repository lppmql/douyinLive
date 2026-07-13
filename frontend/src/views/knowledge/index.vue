<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NTag, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { askKnowledge, fetchKnowledgeItems } from '@/service/api/douyin';

defineOptions({ name: 'Knowledge' });

const message = useMessage();

/* ---------- 知识库列表 ---------- */
const items = ref<Api.Douyin.KnowledgeItem[]>([]);
const loading = ref(false);

async function loadItems() {
  loading.value = true;
  try {
    const res = await fetchKnowledgeItems();
    items.value = res.data || [];
  } catch {
    message.error('知识库加载失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadItems);

/* ---------- 聊天 ---------- */
const question = ref('');
const chatting = ref(false);
const messages = ref<{ role: 'user' | 'ai'; content: string }[]>([]);
const chatEndRef = ref<HTMLElement | null>(null);

async function sendQuestion() {
  const q = question.value.trim();
  if (!q) return;
  messages.value.push({ role: 'user', content: q });
  question.value = '';
  chatting.value = true;
  try {
    const res = await askKnowledge(q) as unknown as { answer: string };
    messages.value.push({ role: 'ai', content: res.answer || '暂无回答' });
  } catch {
    messages.value.push({ role: 'ai', content: '请求失败，请稍后重试' });
  }
  chatting.value = false;
  setTimeout(() => chatEndRef.value?.scrollIntoView({ behavior: 'smooth' }), 100);
}

</script>

<template>
  <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
    <!-- 知识库列表 -->
    <NGi span="2">
      <NCard :bordered="false" class="card-wrapper">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:book-open-variant" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.knowledge.title') }}</span>
          </NSpace>
        </template>
        <NAlert type="info" closable>
          无数据时，可先在场次页面运行 AI 分析后保存到知识库
        </NAlert>
        <NSpin :show="loading">
          <NEmpty v-if="items.length === 0" class="py-40px" description="知识库为空" />
          <NSpace v-else vertical :size="12">
            <NCard v-for="item in items" :key="item.id" size="small">
              <NSpace justify="space-between" align="center">
                <strong>{{ item.title || `知识条目 #${item.id}` }}</strong>
                <NTag size="small" type="info">{{ item.category || '未分类' }}</NTag>
              </NSpace>
              <p class="mt-8px whitespace-pre-wrap text-13px leading-22px text-gray-600">
                {{ item.content || '暂无内容' }}
              </p>
            </NCard>
          </NSpace>
        </NSpin>
      </NCard>
    </NGi>

    <!-- AI 聊天窗 -->
    <NGi span="1">
      <NCard :bordered="false" class="card-wrapper h-full" style="position: sticky; top: 16px">
        <template #header>
          <NSpace>
            <SvgIcon icon="mdi:chat-question" class="text-18px" />
            <span class="text-15px font-bold">AI 助手</span>
          </NSpace>
        </template>

        <!-- 消息列表 -->
        <div ref="chatEndRef" class="h-400px overflow-y-auto mb-12px px-4px">
          <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-40px text-center">
            <SvgIcon icon="mdi:robot-outline" class="text-64px text-gray-300 dark:text-gray-600 mb-16px" />
            <p class="text-14px text-gray-500 mb-8px">{{ $t('page.knowledge.chatPlaceholder') }}</p>
            <p class="text-12px text-gray-400">{{ $t('page.knowledge.chatDesc') }}</p>
          </div>
          <div
            v-for="(msg, i) in messages"
            :key="i"
            class="mb-12px"
            :class="msg.role === 'user' ? 'text-right' : 'text-left'"
          >
            <NTag :type="msg.role === 'user' ? 'primary' : 'success'" size="small" class="mb-4px">
              {{ msg.role === 'user' ? '我' : 'AI' }}
            </NTag>
            <div :class="msg.role === 'user' ? 'rounded-8px p-10px inline-block max-w-90% text-left leading-22px text-13px bg-primary-light text-white' : 'rounded-8px p-10px inline-block max-w-90% text-left leading-22px text-13px bg-gray-100 dark:bg-dark-300'">
              {{ msg.content }}
            </div>
          </div>
        </div>

        <!-- 输入框 -->
        <NSpace>
          <NInput
            v-model:value="question"
            type="text"
            placeholder="输入问题..."
            :disabled="chatting"
            @keyup.enter="sendQuestion"
          />
          <NButton type="primary" :loading="chatting" @click="sendQuestion">发送</NButton>
        </NSpace>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped></style>
